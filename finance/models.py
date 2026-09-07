from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models

from .validators import validate_com_email


class User(AbstractUser):
    full_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(unique=True, validators=[validate_com_email])
    phone_number = models.CharField(max_length=16, unique=True, blank=True, null=True)
    reporting_currency = models.CharField(max_length=10, default='USD')
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True)
    onboarding_complete = models.BooleanField(default=False)

    def __str__(self):
        return self.get_full_name() or self.username


class Account(models.Model):
    ACCOUNT_TYPES = (('cash', 'Cash'), ('bank', 'Bank account'), ('wallet', 'Digital wallet'), ('card', 'Credit card'))
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='accounts')
    name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=34, blank=True)
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
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='income_amount_positive'),
        ]

    def clean(self):
        if self.category_id and self.category.type != 'income':
            raise ValidationError({'category': 'Income must use an income category.'})

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
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='expense_amount_positive'),
        ]

    def clean(self):
        if self.category_id and self.category.type != 'expense':
            raise ValidationError({'category': 'Expenses must use an expense category.'})

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
    start_date = models.DateField()
    end_date = models.DateField()
    amount_limit = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ('user', 'category', 'start_date', 'end_date')
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_limit__gte=0),
                name='budget_amount_limit_non_negative',
            ),
        ]

    def __str__(self):
        return f"{self.category.name} - {self.start_date} to {self.end_date}"

    def clean(self):
        if self.category_id and self.category.type != 'expense':
            raise ValidationError({'category': 'Budgets can only be assigned to expense categories.'})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({'end_date': 'End date must be on or after the start date.'})


class SavingsGoal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='savings_goals')
    name = models.CharField(max_length=120)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2)
    current_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    target_date = models.DateField(null=True, blank=True)
    color = models.CharField(max_length=7, default='#1455c9')
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        unique_together = ('user', 'name')
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
    class Meta:
        unique_together = ('user', 'title')
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


class ExchangeRate(models.Model):
    """A user-managed rate used to convert transactions for reporting."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exchange_rates')
    base_currency = models.CharField(max_length=10)
    quote_currency = models.CharField(max_length=10)
    rate = models.DecimalField(max_digits=16, decimal_places=6)
    effective_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'base_currency', 'quote_currency', 'effective_date')
        ordering = ['-effective_date', 'base_currency', 'quote_currency']

    def clean(self):
        if self.base_currency == self.quote_currency:
            raise ValidationError({'quote_currency': 'Choose a different quote currency.'})
        if self.rate <= 0:
            raise ValidationError({'rate': 'Exchange rate must be greater than zero.'})

    def __str__(self):
        return f'1 {self.base_currency} = {self.rate} {self.quote_currency}'


class Notification(models.Model):
    LEVELS = (('info', 'Info'), ('warning', 'Warning'), ('danger', 'Danger'), ('success', 'Success'))
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=160)
    message = models.CharField(max_length=500)
    level = models.CharField(max_length=10, choices=LEVELS, default='info')
    link = models.CharField(max_length=255, blank=True)
    dedupe_key = models.CharField(max_length=200, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=('user', 'dedupe_key'), condition=~models.Q(dedupe_key=''), name='unique_notification_dedupe_key')]


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=40)
    object_type = models.CharField(max_length=80)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    description = models.CharField(max_length=500)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
