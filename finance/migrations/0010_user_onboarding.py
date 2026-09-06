from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('finance', '0009_user_reporting_currency_alter_account_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='onboarding_complete',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='user',
            name='profile_picture',
            field=models.ImageField(blank=True, upload_to='profile_pictures/'),
        ),
    ]