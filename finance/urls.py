from django.urls import path

from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('categories/', views.category_list, name='categories'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
    path('income/', views.income_list, name='income_list'),
    path('income/create/', views.income_create, name='income_create'),
    path('income/<int:pk>/edit/', views.income_update, name='income_update'),
    path('income/<int:pk>/delete/', views.income_delete, name='income_delete'),
    path('expense/', views.expense_list, name='expense_list'),
    path('expense/create/', views.expense_create, name='expense_create'),
    path('expense/<int:pk>/edit/', views.expense_update, name='expense_update'),
    path('expense/<int:pk>/delete/', views.expense_delete, name='expense_delete'),
    path('quick_transaction/', views.quick_transaction, name='quick_transaction'),
    path('reports/', views.reports, name='reports'),
    path('export/', views.export_transactions, name='export_transactions'),
    path('profile/', views.profile_view, name='profile'),
    path('budgets/', views.budgets, name='budgets'),
    path('tools/', views.financial_tools, name='financial_tools'),
    path('tools/run-recurring/', views.run_recurring, name='run_recurring'),
    path('backup/', views.backup_data, name='backup_data'),
]
