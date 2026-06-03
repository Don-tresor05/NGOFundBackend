from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Notification, Permission, Role, RolePermission, SystemSetting
from apps.audit.models import AuditLog
from apps.compliance.models import ComplianceItem
from apps.donors.models import Donor
from apps.finance.models import BankAccount, BankStatement, BankStatementLine, Reconciliation, Transaction
from apps.grants.models import Grant
from apps.projects.models import BudgetLine, Project, ProjectMember
from apps.reports.models import Report
from apps.requisitions.models import Requisition, RequisitionItem


class Command(BaseCommand):
    help = "Seed demo data for the frontend integration flows."

    def handle(self, *args, **options):
        User = get_user_model()
        for role_key, role_name in [
            (Role.SUPER_ADMIN, "Super Administrator"),
            (Role.FINANCE_OFFICER, "Finance Officer"),
            (Role.PROJECT_MANAGER, "Project Manager"),
            (Role.EXECUTIVE_DIRECTOR, "Executive Director"),
            (Role.FIELD_STAFF, "Field Staff"),
            (Role.EXTERNAL_AUDITOR, "External Auditor"),
            (Role.DONOR_USER, "Donor User"),
        ]:
            Role.objects.get_or_create(role_key=role_key, defaults={"role_name": role_name})

        permissions = [
            ("manage_users", "Manage Users"),
            ("manage_roles", "Manage Roles"),
            ("manage_permissions", "Manage Permissions"),
            ("manage_settings", "Manage Settings"),
            ("manage_donors", "Manage Donors"),
            ("manage_projects", "Manage Projects"),
            ("manage_finance", "Manage Finance"),
            ("manage_reports", "Manage Reports"),
            ("manage_operations", "Manage Operations"),
            ("manage_testing", "Manage Testing"),
            ("manage_compliance", "Manage Compliance"),
            ("view_audit_logs", "View Audit Logs"),
        ]
        for permission_key, permission_name in permissions:
            Permission.objects.get_or_create(
                permission_key=permission_key,
                defaults={"permission_name": permission_name},
            )

        role_permissions = {
            Role.SUPER_ADMIN: [permission_key for permission_key, _ in permissions],
            Role.FINANCE_OFFICER: [
                "manage_donors",
                "manage_projects",
                "manage_finance",
                "manage_reports",
                "view_audit_logs",
            ],
            Role.PROJECT_MANAGER: [
                "manage_donors",
                "manage_projects",
                "manage_operations",
                "manage_testing",
            ],
            Role.EXECUTIVE_DIRECTOR: [
                "manage_donors",
                "manage_projects",
                "manage_finance",
                "manage_reports",
                "manage_settings",
                "manage_operations",
                "manage_testing",
                "manage_compliance",
                "view_audit_logs",
            ],
            Role.FIELD_STAFF: [
                "manage_donors",
                "manage_projects",
                "manage_operations",
                "manage_testing",
            ],
            Role.EXTERNAL_AUDITOR: [
                "manage_reports",
                "manage_compliance",
                "view_audit_logs",
            ],
            Role.DONOR_USER: [
                "manage_donors",
                "manage_projects",
                "manage_reports",
            ],
        }
        for role_key, permission_keys in role_permissions.items():
            role = Role.objects.get(role_key=role_key)
            for permission_key in permission_keys:
                permission = Permission.objects.get(permission_key=permission_key)
                RolePermission.objects.get_or_create(role=role, permission=permission)

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
                    "role_id": role,
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

        ProjectMember.objects.get_or_create(
            project=water_project,
            user=users["manager@ngofund.org"],
            defaults={"member_role": "Project Lead", "status": ProjectMember.Status.ACTIVE},
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

        RequisitionItem.objects.get_or_create(
            requisition=req1,
            item_name="Water pump",
            defaults={"description": "Pump for community water access", "quantity": 1, "unit_cost": 3500},
        )
        RequisitionItem.objects.get_or_create(
            requisition=req1,
            item_name="PVC fittings",
            defaults={"description": "Pipe fittings and connectors", "quantity": 18, "unit_cost": 100},
        )

        bank_account, _ = BankAccount.objects.get_or_create(
            account_number="000123456789",
            defaults={
                "account_name": "RPA Main Operating Account",
                "bank_name": "Bank of Kigali",
                "currency": "USD",
                "is_active": True,
            },
        )
        statement, _ = BankStatement.objects.get_or_create(
            bank_account=bank_account,
            statement_number="STMT-2026-05",
            defaults={
                "period_start": "2026-05-01",
                "period_end": "2026-05-31",
                "opening_balance": 25000,
                "closing_balance": 32000,
                "imported_by": users["finance@ngofund.org"],
            },
        )
        statement_line, _ = BankStatementLine.objects.get_or_create(
            bank_statement=statement,
            reference_number="BNK-10042",
            defaults={
                "transaction_date": "2026-05-22",
                "description": "Nutrition kit reimbursement",
                "amount": 7800,
                "matched": True,
            },
        )
        Transaction.objects.get_or_create(
            bank_reference_number="BNK-10042",
            defaults={
                "requisition": req2,
                "budget_line": nutrition_budget,
                "bank_account": bank_account,
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
                "bank_account": bank_account,
                "processed_by": users["finance@ngofund.org"],
                "amount": 4200,
                "transaction_date": "2026-05-25",
                "status": Transaction.Status.PENDING,
            },
        )

        Reconciliation.objects.get_or_create(
            transaction=Transaction.objects.get(bank_reference_number="BNK-10042"),
            bank_statement_line=statement_line,
            defaults={
                "reviewed_by": users["finance@ngofund.org"],
                "status": Reconciliation.Status.MATCHED,
                "difference_amount": 0,
                "notes": "Auto-matched from statement import.",
                "matched_at": timezone.now(),
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
