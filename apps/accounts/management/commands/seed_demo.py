from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Notification, Role, SystemSetting
from apps.audit.models import AuditLog
from apps.compliance.models import ComplianceItem
from apps.donors.models import Donor
from apps.finance.models import Transaction
from apps.grants.models import Grant
from apps.projects.models import BudgetLine, Project
from apps.reports.models import Report
from apps.requisitions.models import Requisition


class Command(BaseCommand):
    help = "Seed demo data for the frontend integration flows."

    def handle(self, *args, **options):
        User = get_user_model()
        demo_users = [
            ("superadmin@ngofund.org", "Nadine Uwase", Role.SUPER_ADMIN),
            ("finance@ngofund.org", "Michael Finance", Role.FINANCE_OFFICER),
            ("field@ngofund.org", "Aline Field", Role.FIELD_STAFF),
            ("manager@ngofund.org", "Patrick Manager", Role.PROJECT_MANAGER),
            ("director@ngofund.org", "Grace Director", Role.EXECUTIVE_DIRECTOR),
            ("auditor@ngofund.org", "Lisa Auditor", Role.EXTERNAL_AUDITOR),
            ("donor@ngofund.org", "Sarah Donor", Role.DONOR_USER),
        ]

        users = {}
        for email, full_name, role in demo_users:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": email,
                    "full_name": full_name,
                    "role": role,
                    "is_staff": role == Role.SUPER_ADMIN,
                    "is_superuser": role == Role.SUPER_ADMIN,
                },
            )
            if created:
                user.set_password("demo12345")
                user.save()
            users[email] = user

        settings = [
            ("session_timeout_minutes", "Session Timeout", "30", "access"),
            ("receipt_currency", "Receipt Currency", "USD", "finance"),
            ("approval_alerts", "Approval Alerts", "enabled", "notifications"),
        ]
        for key, label, value, group in settings:
            SystemSetting.objects.get_or_create(
                setting_key=key,
                defaults={"label": label, "setting_value": value, "setting_group": group},
            )

        for title, owner in [
            ("Donor consent evidence attached", "Fundraising"),
            ("Expense receipt archive complete", "Finance"),
            ("Quarterly audit export reviewed", "Audit"),
        ]:
            ComplianceItem.objects.get_or_create(title=title, defaults={"owner": owner})

        sarah, _ = Donor.objects.get_or_create(
            organization_name="Sarah Donor",
            defaults={
                "contact_person": "Sarah Donor",
                "contact_email": "donor@ngofund.org",
                "country": "Rwanda",
                "category": "Individual",
                "notes": "Supports maternal care and water access.",
            },
        )
        health_equity, _ = Donor.objects.get_or_create(
            organization_name="Health Equity Fund",
            defaults={
                "contact_person": "Robert Johnson",
                "contact_email": "contact@hef.org",
                "country": "United States",
                "category": "Foundation",
                "notes": "Quarterly compliance package required.",
            },
        )

        health_grant, _ = Grant.objects.get_or_create(
            grant_title="Health Systems Grant",
            defaults={
                "donor": health_equity,
                "total_amount": 85000,
                "currency": "USD",
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "status": Grant.Status.ACTIVE,
                "compliance_notes": "Quarterly utilization and audit report required.",
            },
        )
        maternal_grant, _ = Grant.objects.get_or_create(
            grant_title="Maternal Care Support",
            defaults={
                "donor": sarah,
                "total_amount": 32000,
                "currency": "USD",
                "start_date": "2026-03-01",
                "end_date": "2026-09-30",
                "status": Grant.Status.ACTIVE,
                "compliance_notes": "Receipts required for all field claims.",
            },
        )

        water_project, _ = Project.objects.get_or_create(
            name="Water Access",
            defaults={
                "grant": health_grant,
                "description": "Community water-point rehabilitation and monitoring.",
                "start_date": "2026-02-01",
                "end_date": "2026-10-31",
                "status": Project.Status.ACTIVE,
            },
        )
        Project.objects.get_or_create(
            name="School Nutrition",
            defaults={
                "grant": health_grant,
                "description": "Nutrition support for school-age children.",
                "start_date": "2026-01-15",
                "end_date": "2026-11-30",
                "status": Project.Status.ACTIVE,
            },
        )
        Project.objects.get_or_create(
            name="Maternal Care",
            defaults={
                "grant": maternal_grant,
                "description": "Field care support for mothers and newborns.",
                "start_date": "2026-03-01",
                "end_date": "2026-09-30",
                "status": Project.Status.ACTIVE,
            },
        )

        water_budget, _ = BudgetLine.objects.get_or_create(
            grant=health_grant,
            line_name="Water Access",
            defaults={"allocated_amount": 25000, "spent_amount": 16400},
        )
        nutrition_budget, _ = BudgetLine.objects.get_or_create(
            grant=health_grant,
            line_name="School Nutrition",
            defaults={"allocated_amount": 18000, "spent_amount": 9100},
        )
        BudgetLine.objects.get_or_create(
            grant=maternal_grant,
            line_name="Maternal Care",
            defaults={"allocated_amount": 21000, "spent_amount": 8750},
        )

        req1, _ = Requisition.objects.get_or_create(
            submitted_by=users["field@ngofund.org"],
            budget_line=water_budget,
            description="Water pump installation materials",
            defaults={"amount": 5300, "status": Requisition.Status.PENDING},
        )
        req2, _ = Requisition.objects.get_or_create(
            submitted_by=users["manager@ngofund.org"],
            budget_line=nutrition_budget,
            description="Nutrition kit procurement",
            defaults={"amount": 7800, "status": Requisition.Status.APPROVED},
        )

        Transaction.objects.get_or_create(
            bank_reference_number="BNK-10042",
            defaults={
                "requisition": req2,
                "budget_line": nutrition_budget,
                "processed_by": users["finance@ngofund.org"],
                "amount": 7800,
                "transaction_date": "2026-05-22",
                "status": Transaction.Status.RECONCILED,
            },
        )
        Transaction.objects.get_or_create(
            bank_reference_number="PENDING",
            defaults={
                "requisition": req1,
                "budget_line": water_budget,
                "processed_by": users["finance@ngofund.org"],
                "amount": 4200,
                "transaction_date": "2026-05-25",
                "status": Transaction.Status.PENDING,
            },
        )

        Report.objects.get_or_create(
            grant=health_grant,
            report_type="Q2 Financial Position",
            defaults={"generated_by": users["finance@ngofund.org"], "format": Report.Format.PDF},
        )

        Notification.objects.get_or_create(
            user=users["finance@ngofund.org"],
            title="Bank reference pending",
            defaults={
                "type": "finance",
                "message": "Transaction PENDING needs reconciliation.",
                "is_read": False,
            },
        )

        AuditLog.objects.get_or_create(
            user=users["finance@ngofund.org"],
            action_type="SEED_DEMO_DATA",
            target_entity_id=water_project.id,
            target_entity_type="project",
            defaults={
                "ip_address": "127.0.0.1",
                "details": f"Demo data seeded at {timezone.now().isoformat()}",
            },
        )

        self.stdout.write(self.style.SUCCESS("Demo backend data seeded."))
