from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import BudgetForm, ExpenseForm, IncomeForm, ProfileForm, RegistrationForm
from .models import Budget, Category, Expense, Income


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
            follow=True,
        )
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
        )
        self.category = Category.objects.create(user=self.user, name='Salary', type='income')
        self.client.force_login(self.user)

    def test_dashboard_exposes_savings_and_budget_insights(self):
        income_category = Category.objects.create(user=self.user, name='Freelance', type='income')
        expense_category = Category.objects.create(user=self.user, name='Groceries', type='expense')
        Income.objects.create(user=self.user, category=income_category, amount='1200.00', currency='USD', date='2026-08-01', description='Freelance payment')
        Expense.objects.create(user=self.user, category=expense_category, amount='350.00', currency='USD', date='2026-08-02', description='Groceries')
        Category.objects.create(user=self.user, name='Rent', type='expense')

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['savings_this_month'], 850.00)
        self.assertEqual(response.context['budget_alerts'], 0)
        self.assertIn('budget_summary', response.context)

    def test_budget_monitoring_uses_its_own_month_and_flags_overspending(self):
        expense_category = Category.objects.create(user=self.user, name='Food', type='expense')
        Budget.objects.create(user=self.user, category=expense_category, start_date='2026-08-01', end_date='2026-08-31', amount_limit='100.00')
        Expense.objects.create(user=self.user, category=expense_category, amount='125.00', currency='USD', date='2026-08-02')
        Expense.objects.create(user=self.user, category=expense_category, amount='500.00', currency='USD', date='2026-07-02')

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
        Budget.objects.create(user=self.user, category=expense_category, start_date='2026-08-01', end_date='2026-08-31', amount_limit='500.00')

        response = self.client.post(reverse('budgets'), {
            'category': expense_category.id,
            'start_date': '2026-08-01',
            'end_date': '2026-08-31',
            'amount_limit': '650.00',
        })

        self.assertRedirects(response, reverse('budgets'))
        self.assertEqual(Budget.objects.filter(user=self.user, category=expense_category, start_date='2026-08-01', end_date='2026-08-31').count(), 1)
        self.assertEqual(Budget.objects.get(user=self.user, category=expense_category, start_date='2026-08-01', end_date='2026-08-31').amount_limit, 650.00)

    def test_budget_statuses_distinguish_warning_limit_and_exceeded(self):
        expense_category = Category.objects.create(user=self.user, name='Transport', type='expense')
        Budget.objects.create(user=self.user, category=expense_category, start_date='2026-08-01', end_date='2026-08-31', amount_limit='100.00')
        Expense.objects.create(user=self.user, category=expense_category, amount='100.00', currency='USD', date='2026-08-02')

        response = self.client.get(reverse('budgets'))
        self.assertEqual(response.context['budget_rows'][0]['status'], 'limit')

        Expense.objects.create(user=self.user, category=expense_category, amount='1.00', currency='USD', date='2026-08-03')
        response = self.client.get(reverse('budgets'))
        self.assertEqual(response.context['budget_rows'][0]['status'], 'over')

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
