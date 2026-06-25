# Generated for finance officer workflow enhancements.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0007_alter_transaction_requisition"),
        ("projects", "0004_alter_budgetline_table_alter_project_table_and_more"),
        ("requisitions", "0003_alter_requisition_table_alter_requisitionitem_table"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Vendor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=180)),
                ("contact_person", models.CharField(blank=True, max_length=150)),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=40)),
                ("category", models.CharField(blank=True, max_length=100)),
                ("status", models.CharField(choices=[("active", "Active"), ("inactive", "Inactive")], default="active", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "vendors",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ScheduledPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(max_length=255)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="RWF", max_length=3)),
                ("due_date", models.DateField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("scheduled", "Scheduled"),
                            ("approved", "Approved"),
                            ("paid", "Paid"),
                            ("overdue", "Overdue"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="scheduled",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "approved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="approved_scheduled_payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "bank_account",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scheduled_payments",
                        to="finance.bankaccount",
                    ),
                ),
                (
                    "budget_line",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="scheduled_payments",
                        to="projects.budgetline",
                    ),
                ),
                (
                    "paid_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="paid_scheduled_payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "requisition",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scheduled_payments",
                        to="requisitions.requisition",
                    ),
                ),
                (
                    "scheduled_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="scheduled_payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="scheduled_payments",
                        to="finance.transaction",
                    ),
                ),
                (
                    "vendor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="scheduled_payments",
                        to="finance.vendor",
                    ),
                ),
            ],
            options={
                "db_table": "scheduled_payments",
                "ordering": ["due_date", "-created_at"],
            },
        ),
    ]
