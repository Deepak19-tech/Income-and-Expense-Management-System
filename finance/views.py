from decimal import Decimal, InvalidOperation
import json
import math
from django.utils.safestring import mark_safe

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import AccountForm, BillReminderForm, BudgetForm, CategoryForm, ExchangeRateForm, ExpenseForm, GoalForm, IncomeForm, InterestCalculatorForm, OnboardingForm, ProfileForm, RecurringTransactionForm, RegistrationForm, RestoreBackupForm, ShareForm, TagForm, TransferForm
from .models import Account, AccountTransfer, AuditLog, BillReminder, Budget, Category, ExchangeRate, Expense, ImportBatch, Income, Notification, RecurringTransaction, SavingsGoal, SharedAccess, TransactionTag, User
from .validators import validate_com_email
from io import BytesIO
from django.http import HttpResponse
import datetime
import csv


def _predict_next_month_expense(user, months_to_use=6):
    expense_rows = list(
        Expense.objects.filter(user=user)
        .values('date')
        .annotate(total=Sum('amount'))
        .order_by('date')
    )
    income_rows = list(
        Income.objects.filter(user=user)
        .values('date')
        .annotate(total=Sum('amount'))
        .order_by('date')
    )

    if not expense_rows and not income_rows:
        return {
            'predicted_amount': Decimal('0'),
            'model_type': 'average',
            'message': 'Add a few months of expense data to start forecasting.',
        }

    expense_by_month = {
        row['date'].strftime('%Y-%m'): Decimal(str(row['total']))
        for row in expense_rows
    }
    income_by_month = {
        row['date'].strftime('%Y-%m'): Decimal(str(row['total']))
        for row in income_rows
    }

    dates = [row['date'] for row in expense_rows] + [row['date'] for row in income_rows]
    if not dates:
        return {
            'predicted_amount': Decimal('0'),
            'model_type': 'average',
            'message': 'Add a few months of transaction data to start forecasting.',
        }

    start_date = min(dates).replace(day=1)
    end_date = max(dates).replace(day=1)
    month_series = []
    current = start_date
    while current <= end_date:
        month_key = current.strftime('%Y-%m')
        month_series.append({
            'month': month_key,
            'expense': expense_by_month.get(month_key, Decimal('0')),
            'income': income_by_month.get(month_key, Decimal('0')),
        })
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    if len(month_series) > months_to_use:
        month_series = month_series[-months_to_use:]

    if len(month_series) < 2:
        recent_expense = sum(item['expense'] for item in month_series) / len(month_series) if month_series else Decimal('0')
        return {
            'predicted_amount': recent_expense,
            'model_type': 'average',
            'message': 'Not enough history yet, so the forecast uses the recent average.',
        }

    training_rows = []
    for index, month in enumerate(month_series):
        prev_expense = month_series[index - 1]['expense'] if index > 0 else Decimal('0')
        feature_vector = [
            Decimal(index + 1),
            month['income'],
            prev_expense,
        ]
        training_rows.append((feature_vector, month['expense']))

    feature_means = [sum(float(row[0][i]) for row in training_rows) / len(training_rows) for i in range(3)]
    feature_stds = []
    for i in range(3):
        variance = sum((float(row[0][i]) - feature_means[i]) ** 2 for row in training_rows) / len(training_rows)
        feature_stds.append(math.sqrt(variance) or 1.0)

    normalized_rows = []
    for features, target in training_rows:
        normalized_features = []
        for index, value in enumerate(features):
            std = feature_stds[index]
            normalized_features.append(float((float(value) - feature_means[index]) / std) if std != 0 else 0.0)
        normalized_rows.append((normalized_features, float(target)))

    weights = [0.0, 0.0, 0.0]
    bias = 0.0
    learning_rate = 0.01
    for _ in range(3000):
        predictions = []
        errors = []
        for features, target in normalized_rows:
            prediction = bias + sum(weight * value for weight, value in zip(weights, features))
            predictions.append(prediction)
            errors.append(prediction - target)

        if not errors:
            break

        gradient_weights = [0.0, 0.0, 0.0]
        gradient_bias = 0.0
        for features, error in zip((row[0] for row in normalized_rows), errors):
            for idx, value in enumerate(features):
                gradient_weights[idx] += error * value
            gradient_bias += error

        sample_count = max(len(normalized_rows), 1)
        gradient_weights = [value / sample_count for value in gradient_weights]
        gradient_bias /= sample_count
        weights = [weight - learning_rate * gradient for weight, gradient in zip(weights, gradient_weights)]
        bias -= learning_rate * gradient_bias

    latest_month = month_series[-1]
    latest_features = [
        float(len(month_series)),
        float(latest_month['income']),
        float(latest_month['expense']),
    ]
    normalized_latest = []
    for index, value in enumerate(latest_features):
        std = feature_stds[index]
        normalized_latest.append(float((value - feature_means[index]) / std) if std != 0 else 0.0)

    predicted_value = bias + sum(weight * value for weight, value in zip(weights, normalized_latest))
    predicted_amount = Decimal(str(max(predicted_value, 0)))

    return {
        'predicted_amount': predicted_amount,
        'model_type': 'multivariate_linear_regression',
        'message': 'Forecast based on month trend, income, and past spending.',
    }


@login_required
def quick_transaction(request):
    if request.method != 'POST':
        return redirect('dashboard')

    tx_type = request.POST.get('tx_type')
    category_id = request.POST.get('category')
    amount = request.POST.get('amount')
    currency = request.POST.get('currency', '').strip()
    date_value = request.POST.get('date', '').strip()
    description = request.POST.get('description', '')
    payment_method = request.POST.get('payment_method', '')

    try:
        category = Category.objects.get(pk=category_id, user=request.user)
    except (Category.DoesNotExist, ValueError, TypeError):
        messages.error(request, 'Invalid category selected.')
        return redirect('dashboard')

    if tx_type not in ('income', 'expense') or category.type != tx_type:
        messages.error(request, 'Select a category that matches the transaction type.')
        return redirect('dashboard')

    try:
        amount = Decimal(amount)
    except (InvalidOperation, TypeError):
        messages.error(request, 'Enter a valid transaction amount.')
        return redirect('dashboard')
    if amount <= 0:
        messages.error(request, 'Transaction amount must be greater than zero.')
        return redirect('dashboard')

    allowed_currencies = {code for code, _ in Income.CURRENCY_CHOICES}
    if currency not in allowed_currencies:
        messages.error(request, 'Select a valid currency.')
        return redirect('dashboard')
    try:
        transaction_date = datetime.date.fromisoformat(date_value)
    except ValueError:
        messages.error(request, 'Enter a valid transaction date.')
        return redirect('dashboard')

    if tx_type == 'income':
        income = Income(user=request.user, category=category, amount=amount, currency=currency, date=transaction_date, description=description)
        income.save()
        messages.success(request, 'Income added.')
    elif tx_type == 'expense':
        expense = Expense(user=request.user, category=category, amount=amount, currency=currency, date=transaction_date, description=description, payment_method=payment_method)
        expense.save()
        messages.success(request, 'Expense added.')
    else:
        messages.error(request, 'Invalid transaction type.')

    return redirect('dashboard')


def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            user = authenticate(request, username=form.cleaned_data['username'], password=form.cleaned_data['password1'])
            if user is not None:
                login(request, user)
                messages.success(request, 'Welcome! Your account has been created.')
                return redirect('welcome' if not user.onboarding_complete else 'dashboard')
    else:
        form = RegistrationForm()
    return render(request, 'finance/register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        identifier = request.POST.get('username', '').strip()
        password = request.POST.get('password')
        username = identifier
        if '@' in identifier:
            try:
                validate_com_email(identifier.lower())
                user = User.objects.filter(email__iexact=identifier).first()
                username = user.username if user else ''
            except ValidationError:
                username = ''
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('welcome' if not user.onboarding_complete else 'dashboard')
        messages.error(request, 'Invalid username or password.')
    return render(request, 'finance/login.html')


@login_required
def welcome(request):
    if request.user.onboarding_complete:
        return redirect('dashboard')
    if request.method == 'POST':
        form = OnboardingForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            user.onboarding_complete = True
            user.save()
            messages.success(request, 'Your workspace is ready. Welcome to HisabKitab!')
            return redirect('dashboard')
    else:
        form = OnboardingForm(instance=request.user, initial={'full_name': request.user.full_name})
    return render(request, 'finance/welcome.html', {'form': form})


@login_required
def skip_welcome(request):
    if request.method == 'POST':
        User.objects.filter(pk=request.user.pk).update(onboarding_complete=True)
    return redirect('dashboard')


@login_required
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def mark_notifications_read(request):
    if request.method == 'POST':
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect(request.POST.get('next') or 'dashboard')


def _get_display_currency_symbol(recent_transactions, income_qs, expense_qs):
    for transaction in recent_transactions:
        if hasattr(transaction, 'currency_symbol'):
            return transaction.currency_symbol
    first_income = income_qs.first()
    if first_income is not None:
        return first_income.currency_symbol
    first_expense = expense_qs.first()
    if first_expense is not None:
        return first_expense.currency_symbol
    return '$'


def _budget_metrics(limit, spent):
    """Apply the monthly threshold rule consistently across budget views."""
    remaining = limit - spent
    over_amount = max(Decimal('0'), -remaining)
    if limit == 0:
        status = 'over' if spent > 0 else 'safe'
        percent = 100 if spent > 0 else 0
        used_percent = None
    else:
        used_percent = (spent / limit * 100).quantize(Decimal('0.1'))
        # A progress bar cannot be wider than its container, but the displayed
        # percentage below it still shows overspending (for example, 125%).
        percent = min(100, int(used_percent))
        if spent > limit:
            status = 'over'
        elif spent == limit:
            status = 'limit'
        elif spent >= limit * Decimal('0.8'):
            status = 'warning'
        else:
            status = 'safe'
    return {
        'limit': limit,
        'spent': spent,
        'remaining': remaining,
        'over_amount': over_amount,
        'percent': percent,
        'used_percent': used_percent,
        'status': status,
    }


def _convert_amount(user, amount, source_currency, target_currency, date):
    if source_currency == target_currency:
        return amount
    rate = ExchangeRate.objects.filter(
        user=user, base_currency=source_currency, quote_currency=target_currency,
        effective_date__lte=date,
    ).order_by('-effective_date').first()
    return amount * rate.rate if rate else None


def _create_budget_notifications(user, budget_summary):
    for budget in budget_summary:
        status = budget['status']
        if status == 'safe':
            continue
        labels = {'warning': 'Budget warning', 'limit': 'Budget limit reached', 'over': 'Budget exceeded'}
        Notification.objects.get_or_create(
            user=user,
            dedupe_key=f"budget:{budget['category_name']}:{status}:{timezone.localdate():%Y-%m}",
            defaults={
                'title': labels[status],
                'message': f"{budget['category_name']} is {budget['used_percent'] or 100}% used.",
                'level': 'danger' if status == 'over' else 'warning',
                'link': '/budgets/',
            },
        )


def _create_due_notifications(user, today):
    for bill in BillReminder.objects.filter(user=user, is_paid=False, due_date__lte=today + datetime.timedelta(days=7)):
        Notification.objects.get_or_create(
            user=user, dedupe_key=f'bill:{bill.pk}:{bill.due_date}',
            defaults={'title': 'Bill due soon', 'message': f'{bill.title} is due on {bill.due_date:%b %d}.', 'level': 'warning', 'link': '/tools/'},
        )
    for recurring in RecurringTransaction.objects.filter(user=user, is_active=True, next_due_date__lte=today + datetime.timedelta(days=7)):
        Notification.objects.get_or_create(
            user=user, dedupe_key=f'recurring:{recurring.pk}:{recurring.next_due_date}',
            defaults={'title': 'Recurring transaction due', 'message': f'{recurring.description or recurring.category.name} is due on {recurring.next_due_date:%b %d}.', 'level': 'info', 'link': '/tools/'},
        )


def _dashboard_insights(user, today, income_qs, expense_qs, budget_summary, all_time_income, all_time_expense):
    """Return explainable, rule-based recommendations from the user's history."""
    current_month_start = today.replace(day=1)
    history_end = current_month_start
    history_start = (history_end - datetime.timedelta(days=1)).replace(day=1)
    for _ in range(2):
        history_start = (history_start - datetime.timedelta(days=1)).replace(day=1)

    current_by_category = {
        row['category_id']: row['total']
        for row in expense_qs.filter(date__gte=current_month_start)
        .values('category_id')
        .annotate(total=Sum('amount'))
    }
    history_by_category = list(
        expense_qs.filter(date__gte=history_start, date__lt=history_end)
        .values('category_id', 'category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )

    recommendations = []
    unusual_spending = []
    for row in history_by_category:
        monthly_average = row['total'] / Decimal('3')
        if monthly_average <= 0:
            continue
        recommendations.append({
            'category_name': row['category__name'],
            'average': monthly_average.quantize(Decimal('0.01')),
            'suggested_limit': (monthly_average * Decimal('1.10')).quantize(Decimal('0.01')),
        })
        current_spending = current_by_category.get(row['category_id'], Decimal('0'))
        if current_spending > monthly_average * Decimal('1.5'):
            unusual_spending.append({
                'category_name': row['category__name'],
                'current_spending': current_spending,
                'average': monthly_average.quantize(Decimal('0.01')),
            })

    current_income = income_qs.filter(date__gte=current_month_start).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    current_expense = expense_qs.filter(date__gte=current_month_start).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    savings_rate = ((current_income - current_expense) / current_income) if current_income else Decimal('0')
    savings_points = 25 if savings_rate >= Decimal('0.20') else 15 if savings_rate >= 0 else 0
    expense_ratio = (current_expense / current_income) if current_income else Decimal('1')
    spending_points = 25 if expense_ratio <= Decimal('0.70') else 15 if expense_ratio <= Decimal('0.90') else 5 if expense_ratio <= 1 else 0
    over_budget_count = sum(item['status'] == 'over' for item in budget_summary)
    budget_points = 20 if not budget_summary else int(20 * (len(budget_summary) - over_budget_count) / len(budget_summary))
    overspending_points = 15 if over_budget_count == 0 else 0
    all_time_surplus = all_time_income - all_time_expense
    buffer_points = 15 if current_expense and all_time_surplus >= current_expense * 3 else 8 if all_time_surplus > 0 else 0
    health_score = savings_points + spending_points + budget_points + overspending_points + buffer_points
    health_label = 'Excellent' if health_score >= 80 else 'Good' if health_score >= 60 else 'Needs attention'

    return {
        'budget_recommendations': recommendations[:5],
        'unusual_spending': unusual_spending[:5],
        'financial_health': {'score': health_score, 'label': health_label},
    }


@login_required
def dashboard(request):
    if not request.user.onboarding_complete:
        return redirect('welcome')
    today = timezone.now().date()
    income_qs = Income.objects.filter(user=request.user)
    expense_qs = Expense.objects.filter(user=request.user)

    current_month_income = income_qs.filter(date__year=today.year, date__month=today.month).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    current_month_expense = expense_qs.filter(date__year=today.year, date__month=today.month).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    all_time_income = income_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    all_time_expense = expense_qs.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    savings_this_month = current_month_income - current_month_expense

    recent_transactions = list(income_qs.order_by('-date')[:5]) + list(expense_qs.order_by('-date')[:5])
    recent_transactions.sort(key=lambda item: item.date, reverse=True)
    for transaction in recent_transactions:
        transaction.model_name = 'Income' if isinstance(transaction, Income) else 'Expense'

    current_currency_symbol = _get_display_currency_symbol(recent_transactions, income_qs, expense_qs)
    expense_breakdown = expense_qs.values('category__name').annotate(total=Sum('amount')).order_by('-total')[:5]
    budgets = Budget.objects.filter(user=request.user, start_date__lte=today, end_date__gte=today).select_related('category')
    budget_summary = []
    budget_alerts = 0
    for budget in budgets:
        spent = expense_qs.filter(category=budget.category, date__gte=budget.start_date, date__lte=budget.end_date).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        metrics = _budget_metrics(budget.amount_limit, spent)
        if metrics['status'] != 'safe':
            budget_alerts += 1
        budget_summary.append({
            'category_name': budget.category.name,
            **metrics,
        })
    _create_budget_notifications(request.user, budget_summary)
    converted_income = Decimal('0')
    converted_expense = Decimal('0')
    conversion_complete = True
    for item in income_qs.filter(date__year=today.year, date__month=today.month):
        converted = _convert_amount(request.user, item.amount, item.currency, request.user.reporting_currency, item.date)
        if converted is None:
            conversion_complete = False
        else:
            converted_income += converted
    for item in expense_qs.filter(date__year=today.year, date__month=today.month):
        converted = _convert_amount(request.user, item.amount, item.currency, request.user.reporting_currency, item.date)
        if converted is None:
            conversion_complete = False
        else:
            converted_expense += converted
    # Prepare actual and projected cash-flow series for the dashboard.
    def _get_last_n_months(n=6):
        labels = []
        today = timezone.now().date()
        year = today.year
        month = today.month
        for i in range(n-1, -1, -1):
            m = month - i
            y = year
            while m <= 0:
                m += 12
                y -= 1
            labels.append(f"{y}-{m:02d}")
        return labels

    months = _get_last_n_months(6)
    income_series = []
    expense_series = []
    for m in months:
        y, mo = map(int, m.split('-'))
        inc_total = income_qs.filter(date__year=y, date__month=mo).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        exp_total = expense_qs.filter(date__year=y, date__month=mo).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        income_series.append(float(inc_total))
        expense_series.append(float(exp_total))

    recent_income_average = sum(income_series[-3:]) / 3
    recent_expense_average = sum(expense_series[-3:]) / 3
    projected_months = []
    for offset in range(1, 4):
        projected_month = today.month + offset
        projected_year = today.year + (projected_month - 1) // 12
        projected_month = ((projected_month - 1) % 12) + 1
        projected_months.append(f"{projected_year}-{projected_month:02d}")
    forecast_income = [None] * len(income_series) + [round(recent_income_average, 2)] * 3
    forecast_expense = [None] * len(expense_series) + [round(recent_expense_average, 2)] * 3
    months += projected_months

    category_labels = [item['category__name'] for item in expense_breakdown]
    category_values = [float(item['total']) for item in expense_breakdown]

    # JSON for embedding in JS
    months_json = mark_safe(json.dumps(months))
    income_json = mark_safe(json.dumps(income_series))
    expense_json = mark_safe(json.dumps(expense_series))
    forecast_income_json = mark_safe(json.dumps(forecast_income))
    forecast_expense_json = mark_safe(json.dumps(forecast_expense))
    category_labels_json = mark_safe(json.dumps(category_labels))
    category_values_json = mark_safe(json.dumps(category_values))
    insights = _dashboard_insights(
        request.user, today, income_qs, expense_qs, budget_summary,
        all_time_income, all_time_expense,
    )
    return render(
        request,
        'finance/dashboard.html',
        {
            'current_month_income': current_month_income,
            'current_month_expense': current_month_expense,
            'all_time_income': all_time_income,
            'all_time_expense': all_time_expense,
            'recent_transactions': recent_transactions[:8],
            'expense_breakdown': expense_breakdown,
            'budgets': budgets,
            'net_balance': current_month_income - current_month_expense,
            'savings_this_month': savings_this_month,
            'reporting_currency': request.user.reporting_currency,
            'converted_current_income': converted_income.quantize(Decimal('0.01')),
            'converted_current_expense': converted_expense.quantize(Decimal('0.01')),
            'conversion_complete': conversion_complete,
            'budget_alerts': budget_alerts,
            'budget_summary': budget_summary,
            'categories': Category.objects.filter(user=request.user),
            'quick_currency_choices': Income.CURRENCY_CHOICES,
            'quick_transaction_date': today,
            'quick_default_currency': request.user.reporting_currency if request.user.reporting_currency in {code for code, _ in Income.CURRENCY_CHOICES} else 'USD',
            'current_currency_symbol': current_currency_symbol,
            'chart_months': months_json,
            'chart_income': income_json,
            'chart_expense': expense_json,
            'chart_forecast_income': forecast_income_json,
            'chart_forecast_expense': forecast_expense_json,
            'chart_cat_labels': category_labels_json,
            'chart_cat_values': category_values_json,
            **insights,
        },
    )


@login_required
def category_list(request):
    categories = Category.objects.filter(user=request.user)
    if request.method == 'POST':
        form = CategoryForm(request.POST, user=request.user)
        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            messages.success(request, 'Category created successfully.')
            return redirect('categories')
    else:
        form = CategoryForm(user=request.user)
    return render(request, 'finance/categories.html', {'categories': categories, 'form': form})


@login_required
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk, user=request.user)
    if Income.objects.filter(category=category).exists() or Expense.objects.filter(category=category).exists():
        messages.error(request, 'Cannot delete a category that has transactions.')
    else:
        category.delete()
        messages.success(request, 'Category deleted.')
    return redirect('categories')


@login_required
def income_list(request):
    incomes = Income.objects.filter(user=request.user).select_related('category')
    if request.GET.get('start_date'):
        incomes = incomes.filter(date__gte=request.GET['start_date'])
    if request.GET.get('end_date'):
        incomes = incomes.filter(date__lte=request.GET['end_date'])
    if request.GET.get('category'):
        incomes = incomes.filter(category_id=request.GET['category'])
    return render(request, 'finance/income_list.html', {'incomes': incomes, 'categories': Category.objects.filter(user=request.user, type='income')})


@login_required
def income_create(request):
    if request.method == 'POST':
        form = IncomeForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            income = form.save(commit=False)
            income.user = request.user
            income.save()
            messages.success(request, 'Income added successfully.')
            return redirect('income_list')
    else:
        form = IncomeForm(user=request.user)
    return render(request, 'finance/income_form.html', {'form': form, 'mode': 'Create'})


@login_required
def income_update(request, pk):
    income = get_object_or_404(Income, pk=pk, user=request.user)
    if request.method == 'POST':
        form = IncomeForm(request.POST, request.FILES, instance=income, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Income updated successfully.')
            return redirect('income_list')
    else:
        form = IncomeForm(instance=income, user=request.user)
    return render(request, 'finance/income_form.html', {'form': form, 'mode': 'Edit'})


@login_required
def income_delete(request, pk):
    income = get_object_or_404(Income, pk=pk, user=request.user)
    income.delete()
    messages.success(request, 'Income deleted.')
    return redirect('income_list')


@login_required
def expense_list(request):
    expenses = Expense.objects.filter(user=request.user).select_related('category')
    if request.GET.get('start_date'):
        expenses = expenses.filter(date__gte=request.GET['start_date'])
    if request.GET.get('end_date'):
        expenses = expenses.filter(date__lte=request.GET['end_date'])
    if request.GET.get('category'):
        expenses = expenses.filter(category_id=request.GET['category'])
    if request.GET.get('payment_method'):
        expenses = expenses.filter(payment_method=request.GET['payment_method'])
    if request.GET.get('q'):
        expenses = expenses.filter(description__icontains=request.GET['q'])
    return render(request, 'finance/expense_list.html', {'expenses': expenses, 'categories': Category.objects.filter(user=request.user, type='expense')})


@login_required
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user
            expense.save()
            messages.success(request, 'Expense added successfully.')
            return redirect('expense_list')
    else:
        form = ExpenseForm(user=request.user)
    return render(request, 'finance/expense_form.html', {'form': form, 'mode': 'Create'})


@login_required
def expense_update(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES, instance=expense, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense updated successfully.')
            return redirect('expense_list')
    else:
        form = ExpenseForm(instance=expense, user=request.user)
    return render(request, 'finance/expense_form.html', {'form': form, 'mode': 'Edit'})


@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    expense.delete()
    messages.success(request, 'Expense deleted.')
    return redirect('expense_list')


@login_required
def reports(request):
    incomes = Income.objects.filter(user=request.user)
    expenses = Expense.objects.filter(user=request.user)
    if request.GET.get('start_date'):
        incomes = incomes.filter(date__gte=request.GET['start_date'])
        expenses = expenses.filter(date__gte=request.GET['start_date'])
    if request.GET.get('end_date'):
        incomes = incomes.filter(date__lte=request.GET['end_date'])
        expenses = expenses.filter(date__lte=request.GET['end_date'])
    if request.GET.get('category'):
        incomes = incomes.filter(category_id=request.GET['category'])
        expenses = expenses.filter(category_id=request.GET['category'])
    if request.GET.get('type'):
        if request.GET['type'] == 'income':
            expenses = Expense.objects.none()
        elif request.GET['type'] == 'expense':
            incomes = Income.objects.none()
    income_total = incomes.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    expense_total = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    current_currency_symbol = _get_display_currency_symbol([], incomes, expenses)
    expense_prediction = _predict_next_month_expense(request.user)
    return render(request, 'finance/reports.html', {
        'income_total': income_total,
        'expense_total': expense_total,
        'categories': Category.objects.filter(user=request.user),
        'incomes': incomes,
        'expenses': expenses,
        'current_currency_symbol': current_currency_symbol,
        'expense_prediction': expense_prediction,
    })

@login_required
def export_transactions(request):
    """Export transactions as Excel or PDF.

    GET params:
    - period: '1','3','6','12' months or 'all'
    - category: category id or empty
    - format: 'excel' or 'pdf'
    If start_date/end_date provided, they override period (YYYY-MM-DD).
    """
    period = request.GET.get('period', '1')
    fmt = request.GET.get('format', 'excel')
    cat = request.GET.get('category')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    today = datetime.date.today()
    if start_date and end_date:
        try:
            start = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
            end = datetime.datetime.strptime(end_date, '%Y-%m-%d').date()
        except Exception:
            return HttpResponse('Invalid date format', status=400)
    else:
        if period == 'all':
            start = None
            end = today
        else:
            try:
                months = int(period)
            except Exception:
                months = 1
            # compute month-accurate start
            y = today.year
            m = today.month - months + 1
            while m <= 0:
                m += 12
                y -= 1
            start = datetime.date(y, m, 1)
            end = today

    incomes = Income.objects.filter(user=request.user)
    expenses = Expense.objects.filter(user=request.user)
    if start:
        incomes = incomes.filter(date__gte=start)
        expenses = expenses.filter(date__gte=start)
    if end:
        incomes = incomes.filter(date__lte=end)
        expenses = expenses.filter(date__lte=end)
    if cat:
        incomes = incomes.filter(category_id=cat)
        expenses = expenses.filter(category_id=cat)

    # Build rows
    rows = []
    for inc in incomes.order_by('date'):
        rows.append(['Income', inc.date.isoformat(), inc.category.name, str(inc.amount), inc.currency, inc.description or '', ''])
    for exp in expenses.order_by('date'):
        rows.append(['Expense', exp.date.isoformat(), exp.category.name, str(exp.amount), exp.currency, exp.description or '', exp.payment_method or ''])

    # If no data
    if not rows:
        return HttpResponse('No transactions for the selected filters.', status=404)

    if fmt == 'excel':
        # generate Excel using openpyxl if available
        try:
            from openpyxl import Workbook
        except Exception:
            return HttpResponse('openpyxl is required for Excel export. Install with pip install openpyxl', status=500)
        wb = Workbook()
        ws = wb.active
        ws.title = 'Transactions'
        headers = ['Type', 'Date', 'Category', 'Amount', 'Currency', 'Description', 'Payment Method']
        ws.append(headers)
        for r in rows:
            ws.append(r)
        bio = BytesIO()
        wb.save(bio)
        bio.seek(0)
        filename = f'transactions_{start.isoformat() if start else "all"}_{end.isoformat()}.xlsx'
        resp = HttpResponse(bio.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp
    else:
        # PDF via reportlab
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet
        except Exception:
            return HttpResponse('reportlab is required for PDF export. Install with pip install reportlab', status=500)
        bio = BytesIO()
        doc = SimpleDocTemplate(bio, pagesize=letter)
        styles = getSampleStyleSheet()
        elems = []
        title = Paragraph('Transaction Report', styles['Heading2'])
        elems.append(title)
        elems.append(Paragraph(f'Period: {start.isoformat() if start else "All"} to {end.isoformat()}', styles['Normal']))
        elems.append(Spacer(1, 12))
        data = [['Type', 'Date', 'Category', 'Amount', 'Currency', 'Description', 'Payment Method']] + rows
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#d3d3d3')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        elems.append(table)
        doc.build(elems)
        bio.seek(0)
        filename = f'transactions_{start.isoformat() if start else "all"}_{end.isoformat()}.pdf'
        resp = HttpResponse(bio.read(), content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp


@login_required
def profile_view(request):
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            password = form.cleaned_data.get('password')
            if password:
                user.set_password(password)
            user.save()
            messages.success(request, 'Profile updated.')
            return redirect('profile')
    else:
        form = ProfileForm(instance=request.user)
    return render(request, 'finance/profile.html', {'form': form, 'transaction_count': Income.objects.filter(user=request.user).count() + Expense.objects.filter(user=request.user).count()})


@login_required
def budgets(request):
    budgets = Budget.objects.filter(user=request.user).select_related('category').order_by('-start_date', 'category__name')
    if request.method == 'POST':
        form = BudgetForm(request.POST, user=request.user)
        if form.is_valid():
            _, created = Budget.objects.update_or_create(
                user=request.user,
                category=form.cleaned_data['category'],
                start_date=form.cleaned_data['start_date'],
                end_date=form.cleaned_data['end_date'],
                defaults={'amount_limit': form.cleaned_data['amount_limit']},
            )
            messages.success(request, 'Budget created.' if created else 'Budget limit updated.')
            return redirect('budgets')
    else:
        today = timezone.localdate()
        form = BudgetForm(user=request.user, initial={'start_date': today, 'end_date': today.replace(day=28) + datetime.timedelta(days=4) - datetime.timedelta(days=(today.replace(day=28) + datetime.timedelta(days=4)).day)})

    budget_rows = [
        {'budget': budget, **_budget_metrics(
            budget.amount_limit,
            Expense.objects.filter(user=request.user, category=budget.category, date__gte=budget.start_date, date__lte=budget.end_date).aggregate(total=Sum('amount'))['total'] or Decimal('0'),
        )}
        for budget in budgets
    ]

    # The threshold report is intentionally independent from budget limits.
    # It totals every expense in the selected reporting period per category.
    today = timezone.localdate()
    threshold_start_date = today.replace(day=1)
    threshold_end_date = today
    threshold = Decimal('10000')
    threshold_value = request.GET.get('threshold', '').strip()
    if threshold_value:
        try:
            threshold = Decimal(threshold_value)
            if threshold < 0:
                raise InvalidOperation
        except InvalidOperation:
            messages.error(request, 'Enter a valid non-negative spending threshold.')
            threshold = Decimal('10000')

    start_value = request.GET.get('threshold_start_date', '').strip()
    end_value = request.GET.get('threshold_end_date', '').strip()
    try:
        if start_value:
            threshold_start_date = datetime.date.fromisoformat(start_value)
        if end_value:
            threshold_end_date = datetime.date.fromisoformat(end_value)
        if threshold_end_date < threshold_start_date:
            raise ValueError
    except ValueError:
        messages.error(request, 'Choose a valid threshold reporting date range.')
        threshold_start_date = today.replace(day=1)
        threshold_end_date = today

    expense_categories_over_threshold = (
        Expense.objects.filter(
            user=request.user,
            date__gte=threshold_start_date,
            date__lte=threshold_end_date,
        )
        .values('category__name', 'currency')
        .annotate(total_spent=Sum('amount'), transaction_count=Count('id'))
        .filter(total_spent__gt=threshold)
        .order_by('-total_spent', 'category__name', 'currency')
    )

    current_currency_symbol = _get_display_currency_symbol([], Income.objects.filter(user=request.user), Expense.objects.filter(user=request.user))
    return render(request, 'finance/budgets.html', {
        'budget_rows': budget_rows,
        'form': form,
        'current_currency_symbol': current_currency_symbol,
        'expense_threshold': threshold,
        'expense_threshold_start_date': threshold_start_date,
        'expense_threshold_end_date': threshold_end_date,
        'expense_categories_over_threshold': expense_categories_over_threshold,
    })


@login_required
def budget_update(request, pk):
    """Edit a budget owned by the signed-in user."""
    budget = get_object_or_404(Budget, pk=pk, user=request.user)
    if request.method == 'POST':
        form = BudgetForm(request.POST, instance=budget, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Budget updated.')
            return redirect('budgets')
    else:
        form = BudgetForm(instance=budget, user=request.user)
    return render(request, 'finance/budget_form.html', {'form': form, 'budget': budget})


@login_required
def budget_delete(request, pk):
    """Delete a budget owned by the signed-in user; deletion must be explicit."""
    budget = get_object_or_404(Budget, pk=pk, user=request.user)
    if request.method != 'POST':
        return redirect('budgets')
    budget.delete()
    messages.success(request, 'Budget deleted.')
    return redirect('budgets')


@login_required
def financial_tools(request):
    """A practical command centre for accounts, goals, automations, reminders and sharing."""
    forms = {
        'account_form': AccountForm(user=request.user), 'transfer_form': TransferForm(user=request.user),
        'goal_form': GoalForm(user=request.user), 'recurring_form': RecurringTransactionForm(user=request.user),
        'reminder_form': BillReminderForm(user=request.user), 'tag_form': TagForm(user=request.user), 'share_form': ShareForm(),
        'exchange_rate_form': ExchangeRateForm(), 'restore_form': RestoreBackupForm(), 'interest_form': InterestCalculatorForm(),
    }
    interest_result = None
    if request.method == 'POST':
        action = request.POST.get('action')
        form_key = {'account':'account_form', 'transfer':'transfer_form', 'goal':'goal_form', 'recurring':'recurring_form', 'reminder':'reminder_form', 'tag':'tag_form', 'share':'share_form', 'exchange_rate':'exchange_rate_form'}.get(action)
        if form_key:
            form_class = type(forms[form_key])
            kwargs = {'user': request.user} if action in ('account', 'transfer', 'goal', 'recurring', 'reminder', 'tag') else {}
            form = form_class(request.POST, **kwargs)
            forms[form_key] = form
            if form.is_valid():
                if action == 'share':
                    member = form.cleaned_data['member_username']
                    if member == request.user:
                        form.add_error('member_username', 'You cannot share finance data with yourself.')
                    else:
                        SharedAccess.objects.update_or_create(owner=request.user, member=member, defaults={'can_edit': form.cleaned_data['can_edit']})
                        messages.success(request, 'Collaborator access saved.')
                        return redirect('financial_tools')
                else:
                    item = form.save(commit=False); item.user = request.user; item.save()
                    messages.success(request, f'{action.title()} saved.')
                    return redirect('financial_tools')
        elif action == 'interest':
            form = InterestCalculatorForm(request.POST)
            forms['interest_form'] = form
            if form.is_valid():
                principal = form.cleaned_data['principal']
                rate = form.cleaned_data['annual_rate'] / Decimal('100')
                years = form.cleaned_data['years']
                compounds_per_year = int(form.cleaned_data['compounds_per_year'])
                ending_balance = principal * (Decimal('1') + rate / compounds_per_year) ** (compounds_per_year * years)
                ending_balance = ending_balance.quantize(Decimal('0.01'))
                interest_earned = (ending_balance - principal).quantize(Decimal('0.01'))
                interest_result = {'ending_balance': ending_balance, 'interest_earned': interest_earned}
        elif action == 'restore':
            form = RestoreBackupForm(request.POST, request.FILES)
            forms['restore_form'] = form
            if form.is_valid():
                try:
                    payload = json.load(form.cleaned_data['backup_file'])
                    if payload.get('format') != 'hisabkitab-backup-v2':
                        raise ValueError
                    with transaction.atomic():
                        for row in payload.get('categories', []):
                            Category.objects.get_or_create(user=request.user, name=row['name'], type=row['type'])
                        for row in payload.get('accounts', []):
                            Account.objects.get_or_create(user=request.user, name=row['name'], defaults=row)
                        restored = 0
                        for key, model, category_type in (('income', Income, 'income'), ('expenses', Expense, 'expense')):
                            for row in payload.get(key, []):
                                row = row.copy()
                                category_name = row.pop('category', f'Restored {category_type.title()}')
                                category, _ = Category.objects.get_or_create(user=request.user, name=category_name, type=category_type)
                                defaults = {field: row[field] for field in ('amount', 'currency', 'date', 'description', 'payment_method') if field in row}
                                if model is Expense:
                                    defaults.setdefault('payment_method', '')
                                _, created = model.objects.get_or_create(user=request.user, category=category, **defaults)
                                restored += int(created)
                        for row in payload.get('goals', []):
                            SavingsGoal.objects.update_or_create(user=request.user, name=row['name'], defaults=row)
                    messages.success(request, f'Restored {restored} transaction(s). Existing records were kept.')
                    return redirect('financial_tools')
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    form.add_error('backup_file', 'This is not a valid HisabKitab backup file.')
        elif action == 'import':
            source_file = request.FILES.get('file')
            if not source_file or not source_file.name.lower().endswith('.csv'):
                messages.error(request, 'Please upload a CSV file.')
            else:
                decoded = source_file.read().decode('utf-8-sig').splitlines()
                rows, created = csv.DictReader(decoded), 0
                for row in rows:
                    try:
                        tx_type = (row.get('Type') or row.get('type') or 'expense').lower()
                        date = datetime.date.fromisoformat(row.get('Date') or row.get('date'))
                        amount = Decimal(row.get('Amount') or row.get('amount'))
                        category_name = row.get('Category') or row.get('category') or 'Imported'
                        category, _ = Category.objects.get_or_create(user=request.user, name=category_name, type='income' if tx_type == 'income' else 'expense')
                        defaults = {'user':request.user, 'category':category, 'amount':amount, 'currency':row.get('Currency') or row.get('currency') or 'USD', 'date':date, 'description':row.get('Description') or row.get('description') or 'Imported transaction'}
                        if tx_type == 'income': Income.objects.create(**defaults)
                        else: Expense.objects.create(**defaults, payment_method=row.get('Payment Method') or row.get('payment_method') or '')
                        created += 1
                    except (ValueError, TypeError, KeyError):
                        continue
                source_file.seek(0); ImportBatch.objects.create(user=request.user, source_file=source_file, imported_count=created)
                messages.success(request, f'Imported {created} transaction(s).')
                return redirect('financial_tools')
    today = timezone.localdate()
    _create_due_notifications(request.user, today)
    due_reminders = BillReminder.objects.filter(user=request.user, is_paid=False, due_date__lte=today + datetime.timedelta(days=7)).order_by('due_date')
    goal_data = []
    for goal in SavingsGoal.objects.filter(user=request.user):
        goal_data.append((goal, min(100, int(goal.current_amount * 100 / goal.target_amount)) if goal.target_amount else 0))
    return render(request, 'finance/financial_tools.html', {**forms, 'interest_result': interest_result, 'accounts':Account.objects.filter(user=request.user), 'transfers':AccountTransfer.objects.filter(user=request.user)[:5], 'goals':goal_data, 'recurring':RecurringTransaction.objects.filter(user=request.user), 'reminders':due_reminders, 'tags':TransactionTag.objects.filter(user=request.user), 'shares':SharedAccess.objects.filter(owner=request.user).select_related('member'), 'imports':ImportBatch.objects.filter(user=request.user)[:5], 'exchange_rates':ExchangeRate.objects.filter(user=request.user)[:8], 'audit_logs':AuditLog.objects.filter(user=request.user)[:8]})


@login_required
def run_recurring(request):
    today, created = timezone.localdate(), 0
    for recurring in RecurringTransaction.objects.filter(user=request.user, is_active=True, next_due_date__lte=today):
        model = Income if recurring.type == 'income' else Expense
        values = {'user':request.user, 'category':recurring.category, 'account':recurring.account, 'amount':recurring.amount, 'currency':recurring.currency, 'date':recurring.next_due_date, 'description':recurring.description}
        if model == Expense: values['payment_method'] = 'Bank Transfer'
        model.objects.create(**values); created += 1
        days = {'weekly':7, 'monthly':30, 'yearly':365}[recurring.frequency]
        recurring.next_due_date += datetime.timedelta(days=days); recurring.save(update_fields=['next_due_date'])
    messages.success(request, f'Posted {created} recurring transaction(s).')
    return redirect('financial_tools')


@login_required
def backup_data(request):
    data = {'format': 'hisabkitab-backup-v2', 'exported_at': timezone.now().isoformat(), 'categories': list(Category.objects.filter(user=request.user).values('name','type')), 'accounts': list(Account.objects.filter(user=request.user).values('name','type','opening_balance','currency')), 'income': list(Income.objects.filter(user=request.user).values('amount','currency','date','description','category__name')), 'expenses': list(Expense.objects.filter(user=request.user).values('amount','currency','date','description','payment_method','category__name')), 'goals': list(SavingsGoal.objects.filter(user=request.user).values('name','target_amount','current_amount','target_date'))}
    for key in ('income', 'expenses'):
        for row in data[key]:
            row['category'] = row.pop('category__name')
    response = HttpResponse(json.dumps(data, default=str, indent=2), content_type='application/json')
    response['Content-Disposition'] = 'attachment; filename="hisabkitab-backup.json"'
    return response
