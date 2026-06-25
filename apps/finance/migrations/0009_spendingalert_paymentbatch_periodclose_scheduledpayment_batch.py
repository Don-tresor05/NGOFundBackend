from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0008_vendor_scheduledpayment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=180)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("ready", "Ready"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("scheduled_for", models.DateField(blank=True, null=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="payment_batches", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "processed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="processed_payment_batches",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"db_table": "payment_batches", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="PeriodClose",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("period_start", models.DateField()),
                ("period_end", models.DateField()),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Open"), ("prepared", "Prepared"), ("closed", "Closed")],
                        default="open",
                        max_length=20,
                    ),
                ),
                ("prepared_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("unmatched_statement_lines", models.PositiveIntegerField(default=0)),
                ("reconciliation_exceptions", models.PositiveIntegerField(default=0)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "bank_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="period_closures",
                        to="finance.bankaccount",
                    ),
                ),
                (
                    "closed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="closed_period_closures",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "prepared_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prepared_period_closures",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"db_table": "period_closures", "ordering": ["-period_end", "-created_at"]},
        ),
        migrations.CreateModel(
            name="SpendingAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("threshold_percent", models.DecimalField(decimal_places=2, max_digits=5)),
                (
                    "severity",
                    models.CharField(
                        choices=[("watch", "Watch"), ("warning", "Warning"), ("critical", "Critical")],
                        default="warning",
                        max_length=20,
                    ),
                ),
                ("message", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[("open", "Open"), ("acknowledged", "Acknowledged"), ("resolved", "Resolved")],
                        default="open",
                        max_length=20,
                    ),
                ),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "acknowledged_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="acknowledged_spending_alerts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "budget_line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="spending_alerts",
                        to="projects.budgetline",
                    ),
                ),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resolved_spending_alerts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"db_table": "spending_alerts", "ordering": ["-created_at"]},
        ),
        migrations.AddField(
            model_name="scheduledpayment",
            name="batch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="scheduled_payments",
                to="finance.paymentbatch",
            ),
        ),
    ]
