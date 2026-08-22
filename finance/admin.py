from django.contrib import admin

from .models import Budget, Category, Expense, Income, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'full_name', 'is_staff')
    search_fields = ('username', 'email', 'full_name')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'user', 'created_at')
    list_filter = ('type', 'user')
    search_fields = ('name', 'user__username')


@admin.register(Income)
class IncomeAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'amount', 'currency', 'date', 'description')
    list_filter = ('date', 'category', 'user')
    search_fields = ('description', 'user__username')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'amount', 'currency', 'date', 'payment_method', 'description')
    list_filter = ('date', 'category', 'payment_method', 'user')
    search_fields = ('description', 'user__username')


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'month', 'amount_limit')
    list_filter = ('month', 'user')
    search_fields = ('category__name', 'user__username')
