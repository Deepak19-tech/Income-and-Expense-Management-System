# HisabKitab — Income & Expense Record Keeper

HisabKitab is a modern, lightweight income and expense record keeping web application designed to help individuals track their financial activity, make informed budgeting decisions, and maintain organized financial records.

## What it does
- Register, log in, and manage a personal profile
- Add, edit, and delete income and expense records
- Categorize transactions for clearer reporting
- View summary metrics: total balance, monthly income, monthly expenses
- Generate reports and download transaction statements as Excel or PDF
- Track budgets and view category-based expense breakdowns

## Features
- User registration, authentication, and profile management
- Income and expense CRUD operations
- Transaction categories and budgets
- Dashboard with metric cards and charts
- Export transactions to Excel or PDF
- Responsive Bootstrap-based UI

## Setup
1. Create and activate a virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Apply migrations: `python manage.py migrate`
4. Create a superuser: `python manage.py createsuperuser`
5. Run the development server: `python manage.py runserver`

## Project Structure
- `expense_manager/` - Django project settings, URLs, and configuration
- `finance/` - finance app with models, views, forms, migrations, and tests
- `finance/templates/` - Django HTML templates
- `static/` - browser CSS, JavaScript, and image assets
- `db.sqlite3` - local SQLite application database
