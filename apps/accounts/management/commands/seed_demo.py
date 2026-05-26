from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.models import Role, SystemSetting
from apps.compliance.models import ComplianceItem


class Command(BaseCommand):
    help = "Seed demo users, system settings, and compliance checklist items."

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

        self.stdout.write(self.style.SUCCESS("Demo backend data seeded."))
