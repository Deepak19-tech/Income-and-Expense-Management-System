from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0011_account_account_number'),
    ]

    operations = [
        migrations.AlterField(
            model_name='account',
            name='account_number',
            field=models.CharField(blank=True, error_messages={'max_length': 'Account number must contain exactly 16 digits.'}, max_length=16),
        ),
        migrations.AddConstraint(
            model_name='account',
            constraint=models.UniqueConstraint(
                condition=~Q(('account_number', '')),
                fields=('account_number',),
                name='unique_nonempty_account_number',
            ),
        ),
    ]
