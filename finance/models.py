from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    full_name = models.CharField(max_length=150, blank=True)

    def __str__(self):
        return self.get_full_name() or self.username


class Account(models.Model):
    ACCOUNT_TYPES = (('cash', 'Cash'), ('bank', 'Bank account'), ('wallet', 'Digital wallet'), ('card', 'Credit card'))
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='accounts')
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=12, choices=ACCOUNT_TYPES, default='bank')
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default='USD')
    is_active = models.BooleanField(default=True)
    class Meta: unique_together = ('user', 'name')
    def __str__(self): return self.name


class TransactionTag(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='transaction_tags')
    name = models.CharField(max_length=40)
    color = models.CharField(max_length=7, default='#1455c9')
    class Meta: unique_together = ('user', 'name')
    def __str__(self): return self.name


class AccountTransfer(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='account_transfers')
    from_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='outgoing_transfers')
    to_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='incoming_transfers')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    note = models.CharField(max_length=255, blank=True)
    class Meta: ordering = ['-date']


class Category(models.Model):
    CATEGORY_TYPES = (
        ('income', 'Income'),
        ('expense', 'Expense'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=CATEGORY_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = ('user', 'name', 'type')

    def __str__(self):
        return self.name


class Income(models.Model):
    CURRENCY_CHOICES = (
        ('USD', 'US Dollar'),
        ('AUD', 'Australian Dollar'),
        ('EUR', 'Euro'),
        ('GBP', 'Pound Sterling'),
        ('IC', 'IC'),
        ('NPR', 'Nepalese Rupee'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='incomes')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='incomes')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, default='USD')
    date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='incomes')
    tags = models.ManyToManyField(TransactionTag, blank=True, related_name='incomes')
    receipt = models.FileField(upload_to='receipts/income/', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    @property
    def currency_symbol(self):
        return {
            'USD': '$',
            'AUD': 'A$',
            'EUR': '€',
            'GBP': '£',
            'IC': 'IC',
            'NPR': '₨',
        }.get(self.currency, self.currency)

    def __str__(self):
        return f"{self.amount} - {self.description or self.category.name}"


class Expense(models.Model):
    PAYMENT_METHODS = (
        ('Cash', 'Cash'),
        ('Card', 'Card'),
        ('Bank Transfer', 'Bank Transfer'),
        ('Digital Wallet', 'Digital Wallet'),
    )
    CURRENCY_CHOICES = (
        ('USD', 'US Dollar'),
        ('AUD', 'Australian Dollar'),
        ('EUR', 'Euro'),
        ('GBP', 'Pound Sterling'),
        ('IC', 'IC'),
        ('NPR', 'Nepalese Rupee'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expenses')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='expenses')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, default='USD')
    date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHODS, blank=True)
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    tags = models.ManyToManyField(TransactionTag, blank=True, related_name='expenses')
    receipt = models.FileField(upload_to='receipts/expense/', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    @property
    def currency_symbol(self):
        return {
            'USD': '$',
            'AUD': 'A$',
            'EUR': '€',
            'GBP': '£',
            'IC': 'IC',
            'NPR': '₨',
        }.get(self.currency, self.currency)

    def __str__(self):
        return f"{self.amount} - {self.description or self.category.name}"


class Budget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='budgets')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='budgets')
    month = models.CharField(max_length=7)
    amount_limit = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('user', 'category', 'month')

    def __str__(self):
        return f"{self.category.name} - {self.month}"


class SavingsGoal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='savings_goals')
    name = models.CharField(max_length=120)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    target_date = models.DateField(null=True, blank=True)
    color = models.CharField(max_length=7, default='#1455c9')
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return self.name


class RecurringTransaction(models.Model):
    FREQUENCIES = (('weekly', 'Weekly'), ('monthly', 'Monthly'), ('yearly', 'Yearly'))
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recurring_transactions')
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.SET_NULL, null=True, blank=True)
    type = models.CharField(max_length=10, choices=(('income', 'Income'), ('expense', 'Expense')))
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default='USD')
    frequency = models.CharField(max_length=10, choices=FREQUENCIES, default='monthly')
    next_due_date = models.DateField()
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    def __str__(self): return f"{self.description or self.category.name} ({self.frequency})"


class BillReminder(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bill_reminders')
    title = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    due_date = models.DateField()
    remind_days_before = models.PositiveSmallIntegerField(default=3)
    is_paid = models.BooleanField(default=False)
    def __str__(self): return self.title


class ImportBatch(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='import_batches')
    source_file = models.FileField(upload_to='imports/')
    imported_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class SharedAccess(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shared_finances')
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shared_with_me')
    can_edit = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: unique_together = ('owner', 'member')
