# Generated manually for signup OTP link verification.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_signupotp"),
    ]

    operations = [
        migrations.AddField(
            model_name="signupotp",
            name="verification_token",
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
    ]
