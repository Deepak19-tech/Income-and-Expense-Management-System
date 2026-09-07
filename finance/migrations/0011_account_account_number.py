from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0010_user_onboarding'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='account_number',
            field=models.CharField(blank=True, max_length=34),
        ),
    ]