from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import RegexValidator

from .models import Account, AccountTransfer, BillReminder, Budget, Category, ExchangeRate, Expense, Income, RecurringTransaction, SavingsGoal, SharedAccess, TransactionTag, User
from .validators import validate_com_email


username_starts_with_letter = RegexValidator(
    regex=r'^[A-Za-z]',
    message='Username must start with a letter.',
)
phone_number_validator = RegexValidator(
    regex=r'^\+?[0-9]{7,15}$',
    message='Enter a valid phone number with 7 to 15 digits; a leading + is allowed.',
)


class StyledFormMixin:
    """Apply the shared Bootstrap form styling to every Django field."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            field.widget.attrs['class'] = f"{field.widget.attrs.get('class', '')} {css_class}".strip()


def add_currency_choices(field):
    """Render free-text currency fields as the same select used by transactions."""
    field.choices = Income.CURRENCY_CHOICES
    field.widget = forms.Select(
        choices=Income.CURRENCY_CHOICES,
        attrs={'class': 'form-select'},
    )


class RegistrationForm(StyledFormMixin, UserCreationForm):
    full_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=16, required=True, validators=[phone_number_validator])

    class Meta:
        model = User
        fields = ('full_name', 'email', 'phone_number', 'username', 'password1', 'password2')

    def clean_username(self):
        username = self.cleaned_data['username']
        username_starts_with_letter(username)
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        validate_com_email(email)
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data['phone_number']
        if User.objects.filter(phone_number=phone_number).exists():
            raise forms.ValidationError('A user with this phone number already exists.')
        return phone_number

    def save(self, commit=True):
        user = super().save(commit=False)
        user.full_name = self.cleaned_data['full_name']
        user.email = self.cleaned_data['email']
        user.phone_number = self.cleaned_data['phone_number']
        if commit:
            user.save()
        return user


class CategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ('name', 'type')

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        if self.user and Category.objects.filter(user=self.user, name__iexact=cleaned.get('name', ''), type=cleaned.get('type')).exclude(pk=self.instance.pk).exists():
            self.add_error('name', 'You already have a category with this name and type.')
        return cleaned


class IncomeForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Income
        fields = ('category', 'account', 'amount', 'currency', 'date', 'description', 'tags', 'receipt')
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['category'].queryset = Category.objects.filter(user=user, type='income')
            self.fields['account'].queryset = Account.objects.filter(user=user, is_active=True)
            self.fields['tags'].queryset = TransactionTag.objects.filter(user=user)

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError('Income amount must be greater than zero.')
        return amount


class ExpenseForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Expense
        fields = ('category', 'account', 'amount', 'currency', 'date', 'description', 'payment_method', 'tags', 'receipt')
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['category'].queryset = Category.objects.filter(user=user, type='expense')
            self.fields['account'].queryset = Account.objects.filter(user=user, is_active=True)
            self.fields['tags'].queryset = TransactionTag.objects.filter(user=user)

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError('Expense amount must be greater than zero.')
        return amount


class BudgetForm(StyledFormMixin, forms.ModelForm):
    MINIMUM_BUDGET_LIMIT = 10000
    MAXIMUM_BUDGET_LIMIT = 2100000

    class Meta:
        model = Budget
        fields = ('category', 'start_date', 'end_date', 'amount_limit')
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
        labels = {
            'category': 'Expense category',
            'start_date': 'Start date',
            'end_date': 'End date',
            'amount_limit': 'Budget limit',
        }
        help_texts = {
            'amount_limit': 'Enter an amount from Rs 10,000 to Rs 21,00,000.',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        self.user = user
        super().__init__(*args, **kwargs)
        if user is not None:
            # A budget must only ever be attached to one of the current user's
            # expense categories.  Give the select an explicit prompt so an
            # empty selection is understandable instead of looking like a
            # missing field.
            self.fields['category'].queryset = Category.objects.filter(
                user=user,
                type='expense',
            ).order_by('name')
            self.fields['category'].empty_label = 'Choose an expense category'
        self.fields['amount_limit'].widget.attrs.update({
            'min': self.MINIMUM_BUDGET_LIMIT,
            'max': self.MAXIMUM_BUDGET_LIMIT,
            'step': '0.01',
        })

    def clean_amount_limit(self):
        amount_limit = self.cleaned_data['amount_limit']
        if amount_limit < self.MINIMUM_BUDGET_LIMIT:
            raise forms.ValidationError('Budget must be at least Rs 10,000.')
        if amount_limit > self.MAXIMUM_BUDGET_LIMIT:
            raise forms.ValidationError('Budget cannot exceed Rs 21,00,000.')
        return amount_limit

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get('category')
        start_date = cleaned.get('start_date')
        end_date = cleaned.get('end_date')
        if start_date and end_date and end_date < start_date:
            self.add_error('end_date', 'End date must be on or after the start date.')
        if self.user and category and start_date and end_date:
            overlaps = Budget.objects.filter(
                user=self.user, category=category,
                start_date__lte=end_date, end_date__gte=start_date,
            ).exclude(pk=self.instance.pk).exclude(start_date=start_date, end_date=end_date)
            if overlaps.exists():
                self.add_error('end_date', 'This budget period overlaps an existing budget for this category.')
        return cleaned

class ProfileForm(StyledFormMixin, forms.ModelForm):
    password = forms.CharField(required=False, widget=forms.PasswordInput, help_text='Leave blank to keep current password')

    class Meta:
        model = User
        fields = ('full_name', 'email', 'phone_number', 'username', 'reporting_currency', 'profile_picture')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password'].required = False
        self.fields['phone_number'].required = True
        add_currency_choices(self.fields['reporting_currency'])

    def clean_username(self):
        username = self.cleaned_data['username']
        username_starts_with_letter(username)
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('A user with this username already exists.')
        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        validate_com_email(email)
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data['phone_number']
        phone_number_validator(phone_number)
        if User.objects.filter(phone_number=phone_number).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('A user with this phone number already exists.')
        return phone_number


class OnboardingForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ('full_name', 'profile_picture')
        widgets = {'profile_picture': forms.FileInput(attrs={'accept': 'image/*'})}

    def clean_full_name(self):
        full_name = self.cleaned_data['full_name'].strip()
        if not full_name:
            raise forms.ValidationError('Add a display name so your dashboard feels like yours.')
        return full_name


class AccountForm(StyledFormMixin, forms.ModelForm):
    account_number = forms.CharField(
        required=True,
        max_length=16,
        min_length=16,
        error_messages={
            'required': 'Account number is required.',
            'min_length': 'Account number must contain exactly 16 digits.',
            'max_length': 'Account number must contain exactly 16 digits.',
        },
    )

    class Meta:
        model = Account
        fields = ('name', 'account_number', 'type', 'opening_balance', 'currency')

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        add_currency_choices(self.fields['currency'])
        self.fields['account_number'].widget.attrs.update({'inputmode': 'numeric', 'maxlength': '16', 'minlength': '16', 'pattern': '[0-9]{16}'})

    def clean_name(self):
        name = self.cleaned_data['name']
        if self.user and Account.objects.filter(user=self.user, name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('You already have an account with this name.')
        return name

    def clean_account_number(self):
        account_number = self.cleaned_data['account_number'].strip()
        if len(account_number) != 16 or not account_number.isdigit():
            raise forms.ValidationError('Account number must contain exactly 16 digits.')
        if Account.objects.filter(account_number=account_number).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('This account number is already in use.')
        return account_number


class TransferForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = AccountTransfer
        fields = ('from_account', 'to_account', 'amount', 'date', 'note')
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['from_account'].help_text = 'Select an account with a valid 16-digit account number.'
        self.fields['to_account'].help_text = 'Select an account with a valid 16-digit account number.'
        if user:
            accounts = Account.objects.filter(user=user, is_active=True, account_number__regex=r'^\d{16}$')
            for field_name in ('from_account', 'to_account'):
                self.fields[field_name].queryset = accounts
                self.fields[field_name].label_from_instance = self.account_label

    @staticmethod
    def account_label(account):
        return f'{account.name} ({account.account_number})'
    def clean(self):
        cleaned = super().clean()
        if cleaned.get('from_account') == cleaned.get('to_account'):
            self.add_error('to_account', 'Choose a different destination account.')
        return cleaned

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError('Transfer amount must be greater than zero.')
        return amount


class GoalForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SavingsGoal
        fields = ('name', 'target_amount', 'current_amount', 'target_date', 'color')
        widgets = {'target_date': forms.DateInput(attrs={'type': 'date'}), 'color': forms.TextInput(attrs={'type': 'color'})}

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data['name']
        if self.user and SavingsGoal.objects.filter(user=self.user, name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('You already have a goal with this name.')
        return name

    def clean(self):
        cleaned = super().clean()
        target = cleaned.get('target_amount')
        current = cleaned.get('current_amount')
        if target is not None and target <= 0:
            self.add_error('target_amount', 'Target amount must be greater than zero.')
        if target is not None and current is not None and current > target:
            self.add_error('current_amount', 'Current savings cannot exceed the target amount.')
        return cleaned


class RecurringTransactionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = RecurringTransaction
        fields = ('type', 'category', 'account', 'amount', 'currency', 'frequency', 'next_due_date', 'description')
        widgets = {'next_due_date': forms.DateInput(attrs={'type': 'date'})}
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        add_currency_choices(self.fields['currency'])
        if user:
            self.fields['category'].queryset = Category.objects.filter(user=user)
            self.fields['account'].queryset = Account.objects.filter(user=user, is_active=True)

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get('category')
        if category and cleaned.get('type') and category.type != cleaned['type']:
            self.add_error('category', 'Choose a category that matches the transaction type.')
        if cleaned.get('amount') is not None and cleaned['amount'] <= 0:
            self.add_error('amount', 'Amount must be greater than zero.')
        return cleaned


class BillReminderForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = BillReminder
        fields = ('title', 'amount', 'due_date', 'remind_days_before')
        widgets = {'due_date': forms.DateInput(attrs={'type': 'date'})}

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_title(self):
        title = self.cleaned_data['title']
        if self.user and BillReminder.objects.filter(user=self.user, title__iexact=title).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('You already have a bill reminder with this title.')
        return title


class TagForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = TransactionTag
        fields = ('name', 'color')
        widgets = {'color': forms.TextInput(attrs={'type': 'color'})}

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_name(self):
        name = self.cleaned_data['name']
        if self.user and TransactionTag.objects.filter(user=self.user, name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('You already have a tag with this name.')
        return name


class ShareForm(StyledFormMixin, forms.ModelForm):
    member_username = forms.CharField(max_length=150, label='Member username')
    class Meta:
        model = SharedAccess
        fields = ('can_edit',)
    def clean_member_username(self):
        username = self.cleaned_data['member_username']
        try: return User.objects.get(username=username)
        except User.DoesNotExist: raise forms.ValidationError('No user was found with that username.')


class ExchangeRateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ExchangeRate
        fields = ('base_currency', 'quote_currency', 'rate', 'effective_date')
        widgets = {'effective_date': forms.DateInput(attrs={'type': 'date'}), 'rate': forms.NumberInput(attrs={'step': '0.000001', 'min': '0.000001'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        add_currency_choices(self.fields['base_currency'])
        add_currency_choices(self.fields['quote_currency'])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('base_currency') == cleaned.get('quote_currency'):
            self.add_error('quote_currency', 'Choose a different quote currency.')
        if cleaned.get('rate') is not None and cleaned['rate'] <= 0:
            self.add_error('rate', 'Exchange rate must be greater than zero.')
        return cleaned


class InterestCalculatorForm(StyledFormMixin, forms.Form):
    COMPOUNDING_CHOICES = (
        ('1', 'Annually'),
        ('2', 'Semi-annually'),
        ('4', 'Quarterly'),
        ('12', 'Monthly'),
        ('365', 'Daily'),
    )

    principal = forms.DecimalField(
        label='Starting amount',
        min_value=Decimal('0.01'),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'min': '0.01', 'step': '0.01'}),
    )
    annual_rate = forms.DecimalField(
        label='Annual interest rate (%)',
        min_value=Decimal('0'),
        max_value=Decimal('100'),
        max_digits=6,
        decimal_places=3,
        widget=forms.NumberInput(attrs={'min': '0', 'max': '100', 'step': '0.001'}),
    )
    years = forms.IntegerField(
        label='Years',
        min_value=1,
        max_value=100,
        widget=forms.NumberInput(attrs={'min': '1', 'max': '100', 'step': '1'}),
    )
    compounds_per_year = forms.ChoiceField(
        label='Compounding frequency',
        choices=COMPOUNDING_CHOICES,
    )


class EMICalculatorForm(StyledFormMixin, forms.Form):
    principal = forms.DecimalField(label='Loan principal', min_value=Decimal('0.01'), max_digits=14, decimal_places=2, widget=forms.NumberInput(attrs={'min': '0.01', 'step': '0.01'}))
    annual_rate = forms.DecimalField(label='Annual interest rate (%)', min_value=Decimal('0'), max_value=Decimal('100'), max_digits=6, decimal_places=3, widget=forms.NumberInput(attrs={'min': '0', 'max': '100', 'step': '0.001'}))
    term_months = forms.IntegerField(label='Term (months)', min_value=1, max_value=600, widget=forms.NumberInput(attrs={'min': '1', 'max': '600', 'step': '1'}))


class LoanCalculatorForm(StyledFormMixin, forms.Form):
    loan_amount = forms.DecimalField(label='Purchase price / loan amount', min_value=Decimal('0.01'), max_digits=14, decimal_places=2, widget=forms.NumberInput(attrs={'min': '0.01', 'step': '0.01'}))
    down_payment = forms.DecimalField(label='Down payment', min_value=Decimal('0'), max_digits=14, decimal_places=2, required=False, initial=0, widget=forms.NumberInput(attrs={'min': '0', 'step': '0.01'}))
    annual_rate = forms.DecimalField(label='Annual interest rate (%)', min_value=Decimal('0'), max_value=Decimal('100'), max_digits=6, decimal_places=3, widget=forms.NumberInput(attrs={'min': '0', 'max': '100', 'step': '0.001'}))
    term_years = forms.IntegerField(label='Term (years)', min_value=1, max_value=50, widget=forms.NumberInput(attrs={'min': '1', 'max': '50', 'step': '1'}))
    fees = forms.DecimalField(label='One-time fees', min_value=Decimal('0'), max_digits=14, decimal_places=2, required=False, initial=0, widget=forms.NumberInput(attrs={'min': '0', 'step': '0.01'}))

    def clean(self):
        cleaned = super().clean()
        down_payment = cleaned.get('down_payment') or Decimal('0')
        loan_amount = cleaned.get('loan_amount') or Decimal('0')
        if down_payment > loan_amount:
            self.add_error('down_payment', 'Down payment cannot exceed the purchase price.')
        return cleaned


class ProfitLossForm(StyledFormMixin, forms.Form):
    start_date = forms.DateField(label='From', widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(label='To', widget=forms.DateInput(attrs={'type': 'date'}))
    currency = forms.ChoiceField(label='Currency', choices=Income.CURRENCY_CHOICES)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('start_date') and cleaned.get('end_date') and cleaned['start_date'] > cleaned['end_date']:
            self.add_error('end_date', 'End date must be on or after the start date.')
        return cleaned


class EmergencyFundForm(StyledFormMixin, forms.Form):
    monthly_expenses = forms.DecimalField(min_value=0, max_digits=10, decimal_places=2, label='Monthly essential expenses')
    months_of_cover = forms.IntegerField(min_value=1, max_value=36, initial=6, label='Months of cover')
    current_savings = forms.DecimalField(min_value=0, max_digits=10, decimal_places=2, required=False, initial=0, label='Current emergency savings')


class ExpenseTrendForm(StyledFormMixin, forms.Form):
    months = forms.IntegerField(min_value=3, max_value=24, initial=6, label='Months to analyze')


class RestoreBackupForm(StyledFormMixin, forms.Form):
    backup_file = forms.FileField(label='Backup JSON file')
