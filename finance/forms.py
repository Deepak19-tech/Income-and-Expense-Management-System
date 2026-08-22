from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Account, AccountTransfer, BillReminder, Budget, Category, Expense, Income, RecurringTransaction, SavingsGoal, SharedAccess, TransactionTag, User


class StyledFormMixin:
    """Apply the shared Bootstrap form styling to every Django field."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = 'form-select' if isinstance(field.widget, forms.Select) else 'form-control'
            field.widget.attrs['class'] = f"{field.widget.attrs.get('class', '')} {css_class}".strip()


class RegistrationForm(StyledFormMixin, UserCreationForm):
    full_name = forms.CharField(max_length=150, required=True)
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ('full_name', 'email', 'username', 'password1', 'password2')

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.full_name = self.cleaned_data['full_name']
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class CategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ('name', 'type')


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


class BudgetForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Budget
        fields = ('category', 'month', 'amount_limit')
        widgets = {'month': forms.TextInput(attrs={'placeholder': 'YYYY-MM'})}

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['category'].queryset = Category.objects.filter(user=user)


class ProfileForm(StyledFormMixin, forms.ModelForm):
    password = forms.CharField(required=False, widget=forms.PasswordInput, help_text='Leave blank to keep current password')

    class Meta:
        model = User
        fields = ('full_name', 'email', 'username')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password'].required = False


class AccountForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Account
        fields = ('name', 'type', 'opening_balance', 'currency')


class TransferForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = AccountTransfer
        fields = ('from_account', 'to_account', 'amount', 'date', 'note')
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            accounts = Account.objects.filter(user=user, is_active=True)
            self.fields['from_account'].queryset = accounts
            self.fields['to_account'].queryset = accounts
    def clean(self):
        cleaned = super().clean()
        if cleaned.get('from_account') == cleaned.get('to_account'):
            self.add_error('to_account', 'Choose a different destination account.')
        return cleaned


class GoalForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = SavingsGoal
        fields = ('name', 'target_amount', 'current_amount', 'target_date', 'color')
        widgets = {'target_date': forms.DateInput(attrs={'type': 'date'}), 'color': forms.TextInput(attrs={'type': 'color'})}


class RecurringTransactionForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = RecurringTransaction
        fields = ('type', 'category', 'account', 'amount', 'currency', 'frequency', 'next_due_date', 'description')
        widgets = {'next_due_date': forms.DateInput(attrs={'type': 'date'})}
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['category'].queryset = Category.objects.filter(user=user)
            self.fields['account'].queryset = Account.objects.filter(user=user, is_active=True)


class BillReminderForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = BillReminder
        fields = ('title', 'amount', 'due_date', 'remind_days_before')
        widgets = {'due_date': forms.DateInput(attrs={'type': 'date'})}


class TagForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = TransactionTag
        fields = ('name', 'color')
        widgets = {'color': forms.TextInput(attrs={'type': 'color'})}


class ShareForm(StyledFormMixin, forms.ModelForm):
    member_username = forms.CharField(max_length=150, label='Member username')
    class Meta:
        model = SharedAccess
        fields = ('can_edit',)
    def clean_member_username(self):
        username = self.cleaned_data['member_username']
        try: return User.objects.get(username=username)
        except User.DoesNotExist: raise forms.ValidationError('No user was found with that username.')
