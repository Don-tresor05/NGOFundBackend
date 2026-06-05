# Generated manually for signup OTP verification.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_seed_permission_matrix"),
    ]

    operations = [
        migrations.CreateModel(
            name="SignupOtp",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("otp", models.CharField(max_length=6)),
                ("expires_at", models.DateTimeField()),
                ("is_used", models.BooleanField(default=False)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="signup_otps",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "db_table": "signup_otps",
                "ordering": ["-created_at"],
            },
        ),
    ]
