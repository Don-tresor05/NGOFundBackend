from datetime import date

from django.core.management import call_command
from django.core import mail
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.donors.models import Donor
from apps.finance.models import BankAccount, BankStatement, BankStatementLine, Reconciliation, Transaction
from apps.grants.models import Grant
from apps.projects.models import BudgetLine, Project
from apps.reports.models import Report, ReportDelivery, ReportSchedule
from apps.requisitions.models import Requisition

User = get_user_model()


class ReportWorkflowTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="finance",
            email="finance@example.com",
            password="password123",
            full_name="Finance Officer",
            role_id="FINANCE_OFFICER",
        )
        self.client.force_authenticate(self.user)
        donor = Donor.objects.create(
            organization_name="Health Equity Fund",
            contact_person="Robert Johnson",
            contact_email="contact@example.com",
            country="Rwanda",
            category="Foundation",
        )
        self.grant = Grant.objects.create(
            donor=donor,
            grant_title="Community Health Grant",
            total_amount=45000,
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="active",
        )

    def test_schedule_creation_and_report_delivery(self):
        schedule_response = self.client.post(
            reverse("report-schedules-list"),
            {
                "grant": self.grant.id,
                "report_type": "Quarterly Finance",
                "frequency": "quarterly",
                "delivery_method": "email",
                "recipient_emails": "board@example.com,finance@example.com",
            },
            format="json",
        )
        self.assertEqual(schedule_response.status_code, 201)
        schedule_id = schedule_response.data["id"]

        report = Report.objects.create(
            grant=self.grant,
            generated_by=self.user,
            report_type="Quarterly Finance",
            format="PDF",
        )
        run_response = self.client.post(reverse("report-schedules-run", args=[schedule_id]))
        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(len(run_response.data["deliveries"]), 2)
        self.assertEqual(len(mail.outbox), 2)

        schedule = ReportSchedule.objects.get(pk=schedule_id)
        self.assertIsNotNone(schedule.last_run_at)
        self.assertIsNotNone(schedule.next_run_at)

        deliver_response = self.client.post(
            reverse("reports-deliver", args=[report.id]),
            {"destination": "board@example.com", "delivery_method": "email"},
            format="json",
        )
        self.assertEqual(deliver_response.status_code, 200)
        self.assertTrue(ReportDelivery.objects.filter(report=report, status=ReportDelivery.Status.SENT).exists())

        dispatch_response = self.client.post(
            reverse("report-deliveries-dispatch", args=[deliver_response.data["id"]]),
        )
        self.assertEqual(dispatch_response.status_code, 200)

        deliveries_response = self.client.get(reverse("report-deliveries-list"))
        self.assertEqual(deliveries_response.status_code, 200)
        self.assertGreaterEqual(len(deliveries_response.data), 1)

    def test_scheduled_reports_management_command(self):
        schedule = ReportSchedule.objects.create(
            grant=self.grant,
            created_by=self.user,
            report_type="Monthly Finance",
            frequency="monthly",
            delivery_method="email",
            recipient_emails="board@example.com,finance@example.com",
        )
        Report.objects.create(
            grant=self.grant,
            generated_by=self.user,
            report_type="Monthly Finance",
            format="PDF",
        )

        call_command("run_scheduled_reports")

        schedule.refresh_from_db()
        self.assertIsNotNone(schedule.last_run_at)
        self.assertIsNotNone(schedule.next_run_at)
        self.assertEqual(len(mail.outbox), 2)
        self.assertTrue(ReportDelivery.objects.filter(report__report_type="Monthly Finance").exists())

    def test_generated_report_snapshot_contains_ngo_report_sections(self):
        budget_line = BudgetLine.objects.create(
            grant=self.grant,
            line_name="Clinical Supplies",
            allocated_amount=10000,
            spent_amount=2500,
        )
        Project.objects.create(
            grant=self.grant,
            name="Community Screening",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            status="active",
        )
        requisition = Requisition.objects.create(
            submitted_by=self.user,
            budget_line=budget_line,
            amount=2500,
            description="Supplies purchase",
            status=Requisition.Status.PENDING,
        )
        bank_account = BankAccount.objects.create(
            account_name="Grant Account",
            bank_name="Bank of Kigali",
            account_number="BK-REPORT-001",
            currency="USD",
        )
        transaction = Transaction.objects.create(
            requisition=requisition,
            budget_line=budget_line,
            bank_account=bank_account,
            processed_by=self.user,
            amount=2500,
            currency="USD",
            transaction_date=date(2026, 2, 1),
            bank_reference_number="REF-REPORT-001",
            status=Transaction.Status.CLEARED,
        )
        statement = BankStatement.objects.create(
            bank_account=bank_account,
            statement_number="FEB-2026",
            period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28),
            opening_balance=0,
            closing_balance=2500,
            imported_by=self.user,
        )
        statement_line = BankStatementLine.objects.create(
            bank_statement=statement,
            transaction_date=date(2026, 2, 1),
            description="Supplies purchase",
            reference_number="REF-REPORT-001",
            amount=2500,
            matched=True,
        )
        Reconciliation.objects.create(
            transaction=transaction,
            bank_statement_line=statement_line,
            reviewed_by=self.user,
            status=Reconciliation.Status.MATCHED,
            difference_amount=0,
        )

        response = self.client.post(
            reverse("reports-list"),
            {
                "grant": self.grant.id,
                "report_type": "Full NGO Finance Report",
                "format": "PDF",
                "custom_fields": {"audience": "Finance", "sections": ["financial-summary"]},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        snapshot = Report.objects.get(pk=response.data["id"]).custom_fields["snapshot"]
        self.assertIn("financial_summary", snapshot)
        self.assertIn("donor_funding", snapshot)
        self.assertIn("project_utilization", snapshot)
        self.assertIn("reconciliation_report", snapshot)
        self.assertIn("audit_compliance_report", snapshot)
        self.assertEqual(snapshot["financial_summary"]["allocated_budget"], "10000.00")
        self.assertEqual(snapshot["financial_summary"]["spent_amount"], "2500.00")
        self.assertEqual(snapshot["donor_funding"]["donor_name"], "Health Equity Fund")
        self.assertEqual(snapshot["project_utilization"]["project_count"], 1)
        self.assertEqual(snapshot["reconciliation_report"]["matched_items"], 1)
        self.assertGreaterEqual(snapshot["audit_compliance_report"]["missing_receipts"], 1)
