from django.contrib import admin

from .models import Account, AccountTransfer, BillReminder, Budget, Category, Expense, ImportBatch, Income, RecurringTransaction, SavingsGoal, SharedAccess, TransactionTag, User

admin.site.site_header = 'HisabKitab Administration'
admin.site.site_title = 'HisabKitab Admin'
admin.site.index_title = 'System monitoring and data management'


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'full_name', 'is_active', 'is_staff', 'is_superuser', 'last_login')
    list_filter = ('is_active', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'full_name', 'phone_number')
    readonly_fields = ('last_login', 'date_joined')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'user', 'created_at')
    list_filter = ('type', 'user')
    search_fields = ('name', 'user__username')
    readonly_fields = ('created_at',)


class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'amount', 'currency', 'date', 'description')
    list_filter = ('currency', 'date', 'category', 'user')
    search_fields = ('description', 'user__username', 'category__name')
    date_hierarchy = 'date'
    list_select_related = ('user', 'category', 'account')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Income)
class IncomeAdmin(TransactionAdmin):
    pass


@admin.register(Expense)
class ExpenseAdmin(TransactionAdmin):
    list_display = TransactionAdmin.list_display + ('payment_method',)
    list_filter = ('payment_method',) + TransactionAdmin.list_filter


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'start_date', 'end_date', 'amount_limit')
    list_filter = ('start_date', 'end_date', 'user')
    search_fields = ('category__name', 'user__username')
    list_select_related = ('user', 'category')


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'type', 'opening_balance', 'currency', 'is_active')
    list_filter = ('type', 'currency', 'is_active')
    search_fields = ('name', 'user__username')
    list_select_related = ('user',)


@admin.register(AccountTransfer)
class AccountTransferAdmin(admin.ModelAdmin):
    list_display = ('user', 'from_account', 'to_account', 'amount', 'date', 'note')
    list_filter = ('date', 'user')
    search_fields = ('note', 'user__username')
    date_hierarchy = 'date'
    list_select_related = ('user', 'from_account', 'to_account')


@admin.register(TransactionTag)
class TransactionTagAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'color')
    search_fields = ('name', 'user__username')
    list_select_related = ('user',)


@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'target_amount', 'current_amount', 'target_date')
    list_filter = ('target_date', 'user')
    search_fields = ('name', 'user__username')
    list_select_related = ('user',)


@admin.register(RecurringTransaction)
class RecurringTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'type', 'amount', 'frequency', 'next_due_date', 'is_active')
    list_filter = ('type', 'frequency', 'is_active')
    search_fields = ('description', 'user__username', 'category__name')
    list_select_related = ('user', 'category', 'account')


@admin.register(BillReminder)
class BillReminderAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'amount', 'due_date', 'is_paid')
    list_filter = ('is_paid', 'due_date')
    search_fields = ('title', 'user__username')
    date_hierarchy = 'due_date'
    list_select_related = ('user',)


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ('user', 'source_file', 'imported_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'source_file')
    readonly_fields = ('user', 'source_file', 'imported_count', 'created_at')
    list_select_related = ('user',)


@admin.register(SharedAccess)
class SharedAccessAdmin(admin.ModelAdmin):
    list_display = ('owner', 'member', 'can_edit', 'created_at')
    list_filter = ('can_edit', 'created_at')
    search_fields = ('owner__username', 'member__username')
    readonly_fields = ('created_at',)
    list_select_related = ('owner', 'member')
