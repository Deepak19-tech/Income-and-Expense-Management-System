from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Category, Expense, Income


class FinanceAuthTests(TestCase):
    def test_register_user_and_login(self):
        response = self.client.post(
            reverse('register'),
            {
                'full_name': 'Test User',
                'email': 'test@example.com',
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
