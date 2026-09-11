from django.db import migrations, models
from django.core.validators import RegexValidator


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0012_account_account_number_constraints'),
    ]

    operations = [
        migrations.AlterField(
            model_name='account',
            name='account_number',
            field=models.CharField(
                error_messages={'max_length': 'Account number must contain exactly 16 digits.'},
                max_length=16,
                validators=[RegexValidator(r'^\d{16}$', 'Account number must contain exactly 16 digits.')],
            ),
        ),
    ]