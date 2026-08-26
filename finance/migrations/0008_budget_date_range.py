import calendar
import datetime

from django.db import migrations, models


def set_budget_dates(apps, schema_editor):
    Budget = apps.get_model('finance', 'Budget')
    for budget in Budget.objects.all():
        year, month = map(int, budget.month.split('-'))
        budget.start_date = datetime.date(year, month, 1)
        budget.end_date = datetime.date(year, month, calendar.monthrange(year, month)[1])
        budget.save(update_fields=['start_date', 'end_date'])


class Migration(migrations.Migration):
    dependencies = [('finance', '0007_alter_user_email')]
    operations = [
        migrations.AddField(model_name='budget', name='start_date', field=models.DateField(null=True)),
        migrations.AddField(model_name='budget', name='end_date', field=models.DateField(null=True)),
        migrations.RunPython(set_budget_dates, migrations.RunPython.noop),
        migrations.AlterField(model_name='budget', name='start_date', field=models.DateField()),
        migrations.AlterField(model_name='budget', name='end_date', field=models.DateField()),
        migrations.AlterUniqueTogether(name='budget', unique_together={('user', 'category', 'start_date', 'end_date')}),
        migrations.RemoveField(model_name='budget', name='month'),
    ]
