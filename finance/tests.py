from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import BudgetForm, ExpenseForm, IncomeForm, ProfileForm, RegistrationForm
from .models import Account, AuditLog, Budget, Category, Expense, ExchangeRate, Income, Notification, TransactionTag


def month_date(offset=0, day=1):
    current_month = timezone.localdate().replace(day=1)
    month_index = current_month.year * 12 + current_month.month - 1 + offset
    year, month = divmod(month_index, 12)
    return date(year, month + 1, day)


class FinanceAuthTests(TestCase):
    def test_register_user_and_login(self):
        response = self.client.post(
            reverse('register'),
            {
                'full_name': 'Test User',
                'email': 'test@example.com',
                'phone_number': '+9779812345678',
                'username': 'testuser',
                'password1': 'StrongPass123!',
                'password2': 'StrongPass123!',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(username='testuser').exists())

        response = self.client.post(
            reverse('login'),
            {'username': 'testuser', 'password': 'StrongPass123!'},
        )
        self.assertRedirects(response, reverse('welcome'))
        response = self.client.post(reverse('welcome'), {'full_name': 'Test User'})
        self.assertRedirects(response, reverse('dashboard'))

    def test_registration_requires_com_email_letter_leading_username_and_unique_phone(self):
        user_model = get_user_model()
        user_model.objects.create_user(username='existing', email='existing@example.com', phone_number='+15551234567', password='StrongPass123!')

        form = RegistrationForm(data={
            'full_name': 'Test User', 'email': 'test@example.org', 'phone_number': '+15551234567',
            'username': '1testuser', 'password1': 'StrongPass123!', 'password2': 'StrongPass123!',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)
        self.assertIn('username', form.errors)
        self.assertIn('phone_number', form.errors)

    def test_email_validation_rejects_malformed_or_non_com_addresses(self):
        base_data = {
            'full_name': 'Test User', 'phone_number': '+15551112222', 'username': 'emailuser',
            'password1': 'StrongPass123!', 'password2': 'StrongPass123!',
        }
        for email in ('user@example.org', 'user@-example.com', 'user..name@example.com', 'user@example..com'):
            form = RegistrationForm(data={**base_data, 'email': email})
            self.assertFalse(form.is_valid(), email)
            self.assertIn('email', form.errors)

    def test_login_accepts_registered_com_email(self):
        user_model = get_user_model()
        user_model.objects.create_user(username='emailowner', email='owner@example.com', password='StrongPass123!')
        response = self.client.post(reverse('login'), {'username': 'OWNER@EXAMPLE.COM', 'password': 'StrongPass123!'})
        self.assertRedirects(response, reverse('welcome'))
        response = self.client.post(reverse('skip_welcome'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_profile_rejects_another_users_email_phone_or_numeric_username(self):
        user_model = get_user_model()
        current = user_model.objects.create_user(username='current', email='current@example.com', phone_number='+15550000001', password='StrongPass123!')
        user_model.objects.create_user(username='other', email='other@example.com', phone_number='+15550000002', password='StrongPass123!')
        form = ProfileForm(data={
            'full_name': 'Current User', 'username': '1current', 'email': 'other@example.com',
            'phone_number': '+15550000002', 'password': '',
        }, instance=current)
        self.assertFalse(form.is_valid())
        self.assertIn('username', form.errors)
        self.assertIn('email', form.errors)
        self.assertIn('phone_number', form.errors)


class FinanceCrudTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='owner',
            email='owner@example.com',
            password='StrongPass123!',
            full_name='Owner',
            onboarding_complete=True,
        )
        self.category = Category.objects.create(user=self.user, name='Salary', type='income')
        self.client.force_login(self.user)

    def test_dashboard_exposes_savings_and_budget_insights(self):
        income_category = Category.objects.create(user=self.user, name='Freelance', type='income')
        expense_category = Category.objects.create(user=self.user, name='Groceries', type='expense')
        Income.objects.create(user=self.user, category=income_category, amount='1200.00', currency='USD', date=month_date(day=1), description='Freelance payment')
        Expense.objects.create(user=self.user, category=expense_category, amount='350.00', currency='USD', date=month_date(day=2), description='Groceries')
        Category.objects.create(user=self.user, name='Rent', type='expense')

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['savings_this_month'], 850.00)
        self.assertEqual(response.context['budget_alerts'], 0)
        self.assertIn('budget_summary', response.context)
        self.assertIn('financial_health', response.context)
        self.assertIn('budget_recommendations', response.context)
        self.assertIn('unusual_spending', response.context)

    def test_quick_transaction_has_currency_date_defaults_and_validates_input(self):
        income_category = Category.objects.create(user=self.user, name='Quick salary', type='income')
        page = self.client.get(reverse('dashboard'))
        self.assertContains(page, 'US Dollar')
        self.assertContains(page, 'id="quick_date"')

        invalid = self.client.post(reverse('quick_transaction'), {
            'tx_type': 'income', 'category': income_category.id, 'amount': '100', 'currency': 'BAD', 'date': 'not-a-date',
        }, follow=True)
        self.assertContains(invalid, 'Select a valid currency.')
        self.assertFalse(Income.objects.filter(user=self.user, category=income_category).exists())

        response = self.client.post(reverse('quick_transaction'), {
            'tx_type': 'income', 'category': income_category.id, 'amount': '100', 'currency': 'USD', 'date': '2026-08-27', 'description': 'Quick entry',
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(Income.objects.filter(user=self.user, category=income_category, description='Quick entry').exists())

    def test_dashboard_flags_unusual_spending_and_suggests_budget(self):
        expense_category = Category.objects.create(user=self.user, name='Food', type='expense')
        for offset in (-3, -2, -1):
            Expense.objects.create(user=self.user, category=expense_category, amount='100.00', currency='USD', date=month_date(offset, 10))
        Expense.objects.create(user=self.user, category=expense_category, amount='200.00', currency='USD', date=month_date(day=10))

        response = self.client.get(reverse('dashboard'))

        recommendation = response.context['budget_recommendations'][0]
        alert = response.context['unusual_spending'][0]
        self.assertEqual(recommendation['suggested_limit'], 110.00)
        self.assertEqual(alert['category_name'], 'Food')
        self.assertEqual(alert['current_spending'], 200.00)

    def test_budget_monitoring_uses_its_own_month_and_flags_overspending(self):
        expense_category = Category.objects.create(user=self.user, name='Food', type='expense')
        Budget.objects.create(user=self.user, category=expense_category, start_date=month_date(day=1), end_date=month_date(day=28), amount_limit='100.00')
        Expense.objects.create(user=self.user, category=expense_category, amount='125.00', currency='USD', date=month_date(day=2))
        Expense.objects.create(user=self.user, category=expense_category, amount='500.00', currency='USD', date=month_date(-1, 2))

        response = self.client.get(reverse('budgets'))
        row = response.context['budget_rows'][0]
        self.assertEqual(row['spent'], 125.00)
        self.assertEqual(row['remaining'], -25.00)
        self.assertEqual(row['over_amount'], 25.00)
        self.assertEqual(row['used_percent'], 125.0)
        self.assertEqual(row['percent'], 100)
        self.assertEqual(row['status'], 'over')

    def test_budget_must_be_non_negative_and_use_an_expense_category(self):
        income_category = Category.objects.create(user=self.user, name='Bonus', type='income')
        form = BudgetForm(data={'category': income_category.id, 'start_date': '2026-08-01', 'end_date': '2026-08-31', 'amount_limit': '-1.00'}, user=self.user)
        self.assertFalse(form.is_valid())
        self.assertIn('category', form.errors)
        self.assertIn('amount_limit', form.errors)

    def test_budget_category_is_an_ordered_expense_only_dropdown(self):
        Category.objects.create(user=self.user, name='Zebra', type='expense')
        Category.objects.create(user=self.user, name='Auto', type='expense')
        income_category = Category.objects.create(user=self.user, name='Salary only', type='income')

        form = BudgetForm(user=self.user)

        self.assertEqual(form.fields['category'].empty_label, 'Choose an expense category')
        self.assertEqual(
            list(form.fields['category'].queryset.values_list('name', flat=True)),
            ['Auto', 'Zebra'],
        )
        self.assertNotIn(income_category, form.fields['category'].queryset)

    def test_budget_page_explains_how_to_add_a_category_when_none_exist(self):
        response = self.client.get(reverse('budgets'))

        self.assertContains(response, 'Add an expense category before setting a budget.')
        self.assertContains(response, reverse('categories'))

    def test_saving_a_budget_for_the_same_period_updates_its_limit(self):
        expense_category = Category.objects.create(user=self.user, name='Rent', type='expense')
        Budget.objects.create(user=self.user, category=expense_category, start_date='2026-08-01', end_date='2026-08-31', amount_limit='12000.00')

        response = self.client.post(reverse('budgets'), {
            'category': expense_category.id,
            'start_date': '2026-08-01',
            'end_date': '2026-08-31',
            'amount_limit': '16000.00',
        })

        self.assertRedirects(response, reverse('budgets'))
        self.assertEqual(Budget.objects.filter(user=self.user, category=expense_category, start_date='2026-08-01', end_date='2026-08-31').count(), 1)
        self.assertEqual(Budget.objects.get(user=self.user, category=expense_category, start_date='2026-08-01', end_date='2026-08-31').amount_limit, 16000.00)

    def test_budget_can_be_viewed_edited_and_deleted(self):
        expense_category = Category.objects.create(user=self.user, name='Household', type='expense')
        budget = Budget.objects.create(user=self.user, category=expense_category, start_date='2026-08-01', end_date='2026-08-31', amount_limit='500.00')

        page = self.client.get(reverse('budgets'))
        self.assertContains(page, 'Household')
        self.assertContains(page, f'editBudget{budget.id}')
        self.assertContains(page, 'Edit')
        self.assertContains(page, reverse('budget_delete', args=[budget.id]))

        response = self.client.post(reverse('budget_update', args=[budget.id]), {
            'category': expense_category.id, 'start_date': '2026-08-05', 'end_date': '2026-08-31', 'amount_limit': '16000.00',
        })
        self.assertRedirects(response, reverse('budgets'))
        budget.refresh_from_db()
        self.assertEqual(budget.start_date.isoformat(), '2026-08-05')
        self.assertEqual(budget.amount_limit, 16000.00)

        response = self.client.post(reverse('budget_delete', args=[budget.id]))
        self.assertRedirects(response, reverse('budgets'))
        self.assertFalse(Budget.objects.filter(pk=budget.id).exists())

    def test_budget_limit_range_and_expense_threshold_listing(self):
        food = Category.objects.create(user=self.user, name='Food', type='expense')
        travel = Category.objects.create(user=self.user, name='Travel', type='expense')
        Expense.objects.create(user=self.user, category=food, amount='8000.00', currency='NPR', date='2026-08-02')
        Expense.objects.create(user=self.user, category=food, amount='3000.00', currency='NPR', date='2026-08-03')
        Expense.objects.create(user=self.user, category=food, amount='6000.00', currency='NPR', date='2026-07-31')
        Expense.objects.create(user=self.user, category=travel, amount='9000.00', currency='NPR', date='2026-08-04')

        too_small = BudgetForm(data={'category': food.id, 'start_date': '2026-08-01', 'end_date': '2026-08-31', 'amount_limit': '9999.99'}, user=self.user)
        too_large = BudgetForm(data={'category': food.id, 'start_date': '2026-08-01', 'end_date': '2026-08-31', 'amount_limit': '2100000.01'}, user=self.user)
        self.assertIn('amount_limit', too_small.errors)
        self.assertIn('amount_limit', too_large.errors)

        response = self.client.get(reverse('budgets'), {
            'threshold': '10000',
            'threshold_start_date': '2026-08-01',
            'threshold_end_date': '2026-08-31',
        })
        self.assertEqual(response.context['expense_threshold'], 10000)
        self.assertEqual(response.context['expense_threshold_start_date'].isoformat(), '2026-08-01')
        self.assertEqual(response.context['expense_threshold_end_date'].isoformat(), '2026-08-31')
        self.assertEqual(list(response.context['expense_categories_over_threshold']), [{
            'category__name': 'Food', 'currency': 'NPR', 'total_spent': 11000, 'transaction_count': 2,
        }])

    def test_budget_statuses_distinguish_warning_limit_and_exceeded(self):
        expense_category = Category.objects.create(user=self.user, name='Transport', type='expense')
        Budget.objects.create(user=self.user, category=expense_category, start_date='2026-08-01', end_date='2026-08-31', amount_limit='100.00')
        Expense.objects.create(user=self.user, category=expense_category, amount='100.00', currency='USD', date='2026-08-02')

        response = self.client.get(reverse('budgets'))
        self.assertEqual(response.context['budget_rows'][0]['status'], 'limit')

        Expense.objects.create(user=self.user, category=expense_category, amount='1.00', currency='USD', date='2026-08-03')
        response = self.client.get(reverse('budgets'))
        self.assertEqual(response.context['budget_rows'][0]['status'], 'over')

    def test_budget_warning_creates_a_persistent_notification(self):
        expense_category = Category.objects.create(user=self.user, name='Alerts', type='expense')
        Budget.objects.create(user=self.user, category=expense_category, start_date=month_date(day=1), end_date=month_date(day=28), amount_limit='100.00')
        Expense.objects.create(user=self.user, category=expense_category, amount='85.00', currency='USD', date=month_date(day=5))

        self.client.get(reverse('dashboard'))

        notification = Notification.objects.get(user=self.user)
        self.assertEqual(notification.level, 'warning')
        self.assertIn('85.0% used', notification.message)
        response = self.client.post(reverse('mark_notifications_read'), {'next': reverse('dashboard')})
        self.assertRedirects(response, reverse('dashboard'))
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_tools_save_exchange_rate_and_dashboard_converts_transaction(self):
        income_category = Category.objects.create(user=self.user, name='USD Salary', type='income')
        Income.objects.create(user=self.user, category=income_category, amount='10.00', currency='USD', date=month_date(day=1))

        response = self.client.post(reverse('financial_tools'), {
            'action': 'exchange_rate', 'base_currency': 'USD', 'quote_currency': 'NPR',
            'rate': '130.000000', 'effective_date': month_date(day=1),
        })

        self.assertRedirects(response, reverse('financial_tools'))
        self.user.reporting_currency = 'NPR'
        self.user.save(update_fields=['reporting_currency'])
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(ExchangeRate.objects.get(user=self.user).rate, 130)
        self.assertEqual(response.context['converted_current_income'], 1300)
        self.assertTrue(response.context['conversion_complete'])

    def test_interest_calculator_compounds_and_validates_amount(self):
        response = self.client.post(reverse('financial_tools'), {
            'action': 'interest', 'principal': '1000', 'annual_rate': '12',
            'years': '2', 'compounds_per_year': '12',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['interest_result']['ending_balance'], Decimal('1269.73'))
        self.assertEqual(response.context['interest_result']['interest_earned'], Decimal('269.73'))

        invalid = self.client.post(reverse('financial_tools'), {
            'action': 'interest', 'principal': '0', 'annual_rate': '12',
            'years': '2', 'compounds_per_year': '12',
        })
        self.assertContains(invalid, 'Ensure this value is greater than or equal to 0.01.')

        negative = self.client.post(reverse('financial_tools'), {
            'action': 'interest', 'principal': '-1', 'annual_rate': '12',
            'years': '2', 'compounds_per_year': '12',
        })
        self.assertContains(negative, 'Ensure this value is greater than or equal to 0.01.')

    def test_emi_calculator_returns_monthly_payment_and_interest(self):
        response = self.client.post(reverse('financial_tools'), {
            'action': 'emi', 'principal': '100000', 'annual_rate': '12', 'term_months': '12',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['emi_result'], {
            'monthly_payment': Decimal('8884.88'),
            'total_payment': Decimal('106618.56'),
            'total_interest': Decimal('6618.56'),
        })

    def test_loan_calculator_accounts_for_down_payment_and_fees(self):
        response = self.client.post(reverse('financial_tools'), {
            'action': 'loan', 'loan_amount': '300000', 'down_payment': '50000',
            'annual_rate': '10', 'term_years': '5', 'fees': '2500',
        })
        self.assertEqual(response.status_code, 200)
        result = response.context['loan_result']
        self.assertEqual(result['financed_amount'], Decimal('250000.00'))
        self.assertEqual(result['monthly_payment'], Decimal('5311.76'))
        self.assertEqual(result['total_repayment'], Decimal('318705.60'))
        self.assertEqual(result['total_interest'], Decimal('68705.60'))
        self.assertEqual(result['cash_needed'], Decimal('52500.00'))

        invalid = self.client.post(reverse('financial_tools'), {
            'action': 'loan', 'loan_amount': '300000', 'down_payment': '300001',
            'annual_rate': '10', 'term_years': '5', 'fees': '0',
        })
        self.assertIn('Down payment cannot exceed the purchase price.', invalid.context['loan_form'].errors['down_payment'])

        no_down_payment = self.client.post(reverse('financial_tools'), {
            'action': 'loan', 'loan_amount': '300000', 'annual_rate': '10', 'term_years': '5', 'fees': '',
        })
        self.assertEqual(no_down_payment.status_code, 200)
        self.assertEqual(no_down_payment.context['loan_result']['financed_amount'], Decimal('300000.00'))

    def test_profit_loss_calculator_filters_by_period_and_currency(self):
        income_category = Category.objects.create(user=self.user, name='Consulting', type='income')
        expense_category = Category.objects.create(user=self.user, name='Supplies', type='expense')
        Income.objects.create(user=self.user, category=income_category, amount='2500', currency='USD', date='2026-08-10')
        Income.objects.create(user=self.user, category=income_category, amount='1000', currency='EUR', date='2026-08-10')
        Expense.objects.create(user=self.user, category=expense_category, amount='700', currency='USD', date='2026-08-12')
        Expense.objects.create(user=self.user, category=expense_category, amount='100', currency='USD', date='2026-09-01')

        response = self.client.post(reverse('financial_tools'), {
            'action': 'profit_loss', 'start_date': '2026-08-01', 'end_date': '2026-08-31', 'currency': 'USD',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['profit_loss_result']['income'], Decimal('2500'))
        self.assertEqual(response.context['profit_loss_result']['expenses'], Decimal('700'))
        self.assertEqual(response.context['profit_loss_result']['net'], Decimal('1800'))
        self.assertEqual(response.context['profit_loss_result']['label'], 'Profit')

    def test_transfer_account_choices_show_account_numbers(self):
        Account.objects.create(user=self.user, name='Cash', account_number='10001')
        Account.objects.create(user=self.user, name='Bank', account_number='20002')

        response = self.client.get(reverse('financial_tools'))

        self.assertContains(response, 'Cash (10001)')
        self.assertContains(response, 'Bank (20002)')

    def test_account_numbers_require_sixteen_digits_and_are_unique(self):
        Account.objects.create(user=self.user, name='Existing', account_number='1234567890123456')

        duplicate = self.client.post(reverse('financial_tools'), {
            'action': 'account', 'name': 'Duplicate number', 'account_number': '1234567890123456',
            'type': 'bank', 'opening_balance': '0', 'currency': 'USD',
        })
        self.assertEqual(duplicate.status_code, 200)
        self.assertIn('This account number is already in use.', duplicate.context['account_form'].errors['account_number'])

        for account_number in ('1234', '12345678901234567', '123456789012345x'):
            invalid = self.client.post(reverse('financial_tools'), {
                'action': 'account', 'name': f'Invalid {account_number}', 'account_number': account_number,
                'type': 'bank', 'opening_balance': '0', 'currency': 'USD',
            })
            self.assertEqual(invalid.status_code, 200)
            self.assertIn('Account number must contain exactly 16 digits.', invalid.context['account_form'].errors['account_number'])

        valid = self.client.post(reverse('financial_tools'), {
            'action': 'account', 'name': 'Valid account', 'account_number': '9876543210987654',
            'type': 'bank', 'opening_balance': '0', 'currency': 'USD',
        })
        self.assertRedirects(valid, reverse('financial_tools'))

    def test_income_and_expense_creation_persists_selected_tags(self):
        income_tag = TransactionTag.objects.create(user=self.user, name='Recurring income')
        expense_tag = TransactionTag.objects.create(user=self.user, name='Essential expense')
        expense_category = Category.objects.create(user=self.user, name='Groceries tags', type='expense')

        income_response = self.client.post(reverse('income_create'), {
            'category': self.category.id, 'amount': '2500.00', 'date': '2026-08-01',
            'description': 'Tagged salary', 'currency': 'USD', 'tags': [income_tag.id],
        })
        self.assertRedirects(income_response, reverse('income_list'))
        self.assertEqual(list(Income.objects.get(description='Tagged salary').tags.all()), [income_tag])

        expense_response = self.client.post(reverse('expense_create'), {
            'category': expense_category.id, 'amount': '45.50', 'date': '2026-08-02',
            'description': 'Tagged groceries', 'payment_method': 'Card', 'currency': 'USD', 'tags': [expense_tag.id],
        })
        self.assertRedirects(expense_response, reverse('expense_list'))
        self.assertEqual(list(Expense.objects.get(description='Tagged groceries').tags.all()), [expense_tag])

    def test_backup_can_be_restored_without_overwriting_existing_data(self):
        expense_category = Category.objects.create(user=self.user, name='Restored Food', type='expense')
        Expense.objects.create(user=self.user, category=expense_category, amount='40.00', currency='USD', date='2026-08-01', description='Lunch')

        backup = self.client.get(reverse('backup_data')).content
        Expense.objects.all().delete()
        Category.objects.filter(name='Restored Food').delete()
        response = self.client.post(reverse('financial_tools'), {
            'action': 'restore',
            'backup_file': SimpleUploadedFile('backup.json', backup, content_type='application/json'),
        })

        self.assertRedirects(response, reverse('financial_tools'))
        self.assertTrue(Expense.objects.filter(user=self.user, description='Lunch').exists())
        self.assertTrue(AuditLog.objects.filter(user=self.user, object_type='Expense', action='created').exists())

    def test_financial_tools_workflows_create_and_validate_records(self):
        expense_category = Category.objects.create(user=self.user, name='Tools expense', type='expense')
        income_category = Category.objects.create(user=self.user, name='Tools income', type='income')
        member = get_user_model().objects.create_user(username='member', email='member@example.com', password='StrongPass123!')

        for data in (
            {'action': 'account', 'name': 'Cash', 'type': 'cash', 'opening_balance': '10', 'currency': 'USD'},
            {'action': 'account', 'name': 'Bank', 'type': 'bank', 'opening_balance': '20', 'currency': 'USD'},
            {'action': 'goal', 'name': 'Laptop', 'target_amount': '1000', 'current_amount': '100', 'target_date': '2026-12-01', 'color': '#1455c9'},
            {'action': 'reminder', 'title': 'Internet', 'amount': '20', 'due_date': '2026-08-30', 'remind_days_before': '3'},
            {'action': 'tag', 'name': 'Essential', 'color': '#1455c9'},
            {'action': 'share', 'member_username': member.username, 'can_edit': 'on'},
        ):
            self.assertRedirects(self.client.post(reverse('financial_tools'), data), reverse('financial_tools'))

        cash, bank = self.user.accounts.get(name='Cash'), self.user.accounts.get(name='Bank')
        self.assertRedirects(self.client.post(reverse('financial_tools'), {'action': 'transfer', 'from_account': cash.id, 'to_account': bank.id, 'amount': '5', 'date': '2026-08-01', 'note': 'Top up'}), reverse('financial_tools'))
        self.assertRedirects(self.client.post(reverse('financial_tools'), {'action': 'recurring', 'type': 'expense', 'category': expense_category.id, 'account': cash.id, 'amount': '12', 'currency': 'USD', 'frequency': 'monthly', 'next_due_date': '2026-08-01', 'description': 'Subscription'}), reverse('financial_tools'))
        self.assertRedirects(self.client.post(reverse('run_recurring')), reverse('financial_tools'))
        self.assertTrue(Expense.objects.filter(user=self.user, description='Subscription').exists())
        self.assertEqual(self.user.savings_goals.count(), 1)
        self.assertEqual(self.user.bill_reminders.count(), 1)
        self.assertEqual(self.user.transaction_tags.count(), 1)
        self.assertEqual(self.user.shared_finances.count(), 1)
        self.assertEqual(self.user.account_transfers.count(), 1)

        invalid = self.client.post(reverse('financial_tools'), {'action': 'recurring', 'type': 'expense', 'category': income_category.id, 'amount': '10', 'currency': 'USD', 'frequency': 'monthly', 'next_due_date': '2026-08-01'})
        self.assertContains(invalid, 'Choose a category that matches the transaction type.')

    def test_income_and_expense_amounts_must_be_positive(self):
        expense_category = Category.objects.create(user=self.user, name='Utilities', type='expense')
        self.assertIn('amount', ExpenseForm(data={'category': expense_category.id, 'amount': '0', 'currency': 'USD', 'date': '2026-08-02'}, user=self.user).errors)
        self.assertIn('amount', IncomeForm(data={'category': self.category.id, 'amount': '-1', 'currency': 'USD', 'date': '2026-08-02'}, user=self.user).errors)

    def test_reports_page_shows_expense_prediction(self):
        expense_category = Category.objects.create(user=self.user, name='Groceries Forecast', type='expense')
        income_category = Category.objects.create(user=self.user, name='Salary Forecast', type='income')
        for month, expense_amount, income_amount in [
            ('2026-01-01', '100.00', '500.00'),
            ('2026-02-01', '120.00', '550.00'),
            ('2026-03-01', '140.00', '600.00'),
        ]:
            Expense.objects.create(user=self.user, category=expense_category, amount=expense_amount, currency='USD', date=month, description='Groceries')
            Income.objects.create(user=self.user, category=income_category, amount=income_amount, currency='USD', date=month, description='Salary')

        response = self.client.get(reverse('reports'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('expense_prediction', response.context)
        self.assertGreater(response.context['expense_prediction']['predicted_amount'], 0)

    def test_income_crud_flow(self):
        response = self.client.post(
            reverse('income_create'),
            {
                'category': self.category.id,
                'amount': '2500.00',
                'date': '2026-08-01',
                'description': 'Salary deposit',
                'currency': 'USD',
            },
        )
        self.assertEqual(response.status_code, 302)
        income = Income.objects.get(description='Salary deposit')
        self.assertEqual(income.currency, 'USD')

        income = Income.objects.get(description='Salary deposit')
        response = self.client.post(
            reverse('income_update', args=[income.id]),
            {
                'category': self.category.id,
                'amount': '2600.00',
                'date': '2026-08-01',
                'description': 'Updated salary',
                'currency': 'NPR',
            },
        )
        self.assertEqual(response.status_code, 302)
        income.refresh_from_db()
        self.assertEqual(income.amount, 2600.00)

        response = self.client.post(reverse('income_delete', args=[income.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Income.objects.filter(id=income.id).exists())

    def test_expense_crud_flow(self):
        expense_category = Category.objects.create(user=self.user, name='Groceries', type='expense')
        response = self.client.post(
            reverse('expense_create'),
            {
                'category': expense_category.id,
                'amount': '45.50',
                'date': '2026-08-02',
                'description': 'Weekly groceries',
                'payment_method': 'Card',
                'currency': 'USD',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Expense.objects.filter(description='Weekly groceries').exists())

        expense = Expense.objects.get(description='Weekly groceries')
        response = self.client.post(
            reverse('expense_update', args=[expense.id]),
            {
                'category': expense_category.id,
                'amount': '50.00',
                'date': '2026-08-02',
                'description': 'Updated groceries',
                'payment_method': 'Cash',
                'currency': 'EUR',
            },
        )
        self.assertEqual(response.status_code, 302)
        expense.refresh_from_db()
        self.assertEqual(expense.amount, 50.00)

        response = self.client.post(reverse('expense_delete', args=[expense.id]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Expense.objects.filter(id=expense.id).exists())
