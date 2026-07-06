from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.donors.models import Donor
from apps.finance.models import BankAccount, BankStatement, BankStatementLine, ExpenseApproval, PaymentBatch, PeriodClose, Reconciliation, ScheduledPayment, SpendingAlert, Transaction, Vendor
from apps.grants.models import Grant
from apps.projects.models import BudgetLine
from apps.requisitions.models import Requisition

User = get_user_model()


class ExpenseApprovalWorkflowTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.field_user = User.objects.create_user(
            username="field-staff",
            email="field@example.com",
            password="password123",
            full_name="Field Staff",
            role_id="FIELD_STAFF",
        )
        self.finance_user = User.objects.create_user(
            username="finance-officer",
            email="finance@example.com",
            password="password123",
            full_name="Finance Officer",
            role_id="FINANCE_OFFICER",
        )
        self.executive_user = User.objects.create_user(
            username="executive-director",
            email="executive@example.com",
            password="password123",
            full_name="Executive Director",
            role_id="EXECUTIVE_DIRECTOR",
        )
        self.client.force_authenticate(self.field_user)
        donor = Donor.objects.create(
            organization_name="Hope Foundation",
            contact_person="Sarah Donor",
            contact_email="sarah@example.com",
            country="Rwanda",
            category="Foundation",
        )
        grant = Grant.objects.create(
            donor=donor,
            grant_title="Maternal Health Grant",
            total_amount=60000,
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="active",
        )
        self.budget_line = BudgetLine.objects.create(grant=grant, line_name="Maternal Care", allocated_amount=15000, spent_amount=5000)
        self.requisition = Requisition.objects.create(
            submitted_by=self.field_user,
            budget_line=self.budget_line,
            amount=2000,
            description="Procure maternal care kits",
        )

    def test_expense_approval_workflow_updates_requisition(self):
        approval = self.client.post(
            reverse("expense-approvals-list"),
            {"requisition": self.requisition.id, "notes": "Initial request submitted."},
            format="json",
        )
        self.assertEqual(approval.status_code, 201)

        department_response = self.client.post(reverse("expense-approvals-department-review", args=[approval.data["id"]]))
        self.assertEqual(department_response.status_code, 200)
        self.assertEqual(department_response.data["stage"], ExpenseApproval.Stage.DEPARTMENT_REVIEW)

        self.client.force_authenticate(self.finance_user)
        finance_response = self.client.post(reverse("expense-approvals-finance-review", args=[approval.data["id"]]))
        self.assertEqual(finance_response.status_code, 200)
        self.assertEqual(finance_response.data["stage"], ExpenseApproval.Stage.FINANCE_REVIEW)

        self.client.force_authenticate(self.executive_user)
        executive_response = self.client.post(reverse("expense-approvals-executive-review", args=[approval.data["id"]]))
        self.assertEqual(executive_response.status_code, 200)
        self.assertEqual(executive_response.data["stage"], ExpenseApproval.Stage.EXECUTIVE_REVIEW)

        approve_response = self.client.post(reverse("expense-approvals-approve", args=[approval.data["id"]]))
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.data["stage"], ExpenseApproval.Stage.APPROVED)

        self.requisition.refresh_from_db()
        self.assertEqual(self.requisition.status, Requisition.Status.APPROVED)

    def test_reconciliation_match_marks_line_and_transaction(self):
        bank_account = BankAccount.objects.create(
            account_name="Main Operating Account",
            bank_name="BPR",
            account_number="1234567890",
            currency="USD",
        )
        statement = BankStatement.objects.create(
            bank_account=bank_account,
            statement_number="ST-001",
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            opening_balance=10000,
            closing_balance=12000,
            imported_by=self.finance_user,
        )
        line = BankStatementLine.objects.create(
            bank_statement=statement,
            transaction_date=date(2026, 5, 15),
            description="Maternal care disbursement",
            reference_number="REF-001",
            amount=2000,
        )
        transaction = Transaction.objects.create(
            requisition=self.requisition,
            budget_line=self.budget_line,
            bank_account=bank_account,
            processed_by=self.finance_user,
            amount=2000,
            transaction_date=date(2026, 5, 15),
            bank_reference_number="REF-001",
            status=Transaction.Status.CLEARED,
        )

        self.client.force_authenticate(self.finance_user)
        reconciliation = self.client.post(
            reverse("reconciliations-list"),
            {"transaction": transaction.id, "bank_statement_line": line.id},
            format="json",
        )
        self.assertEqual(reconciliation.status_code, 201)

        match_response = self.client.post(reverse("reconciliations-match", args=[reconciliation.data["id"]]))
        self.assertEqual(match_response.status_code, 200)
        self.assertEqual(match_response.data["status"], Reconciliation.Status.MATCHED)

        transaction.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(transaction.status, Transaction.Status.RECONCILED)
        self.assertTrue(line.matched)

    def test_bank_statement_import_and_auto_match(self):
        bank_account = BankAccount.objects.create(
            account_name="Main Operating Account",
            bank_name="BPR",
            account_number="1234500000",
            currency="USD",
        )
        statement = BankStatement.objects.create(
            bank_account=bank_account,
            statement_number="TMP-001",
            period_start=date(2026, 5, 1),
            period_end=date(2026, 5, 31),
            opening_balance=10000,
            closing_balance=12000,
            imported_by=self.finance_user,
        )
        self.client.force_authenticate(self.finance_user)
        import_response = self.client.post(
            reverse("bank-statements-import-lines", args=[statement.pk]),
            {
                "statement_number": "ST-002",
                "period_start": "2026-05-01",
                "period_end": "2026-05-31",
                "opening_balance": "10000.00",
                "closing_balance": "12000.00",
                "lines": [
                    {
                        "transaction_date": "2026-05-15",
                        "description": "Maternal care disbursement",
                        "reference_number": "REF-AUTO-1",
                        "amount": "2000.00",
                    }
                ],
            },
            format="json",
        )
        self.assertEqual(import_response.status_code, 201)
        line_id = import_response.data["lines"][0]["id"]

        transaction = Transaction.objects.create(
            requisition=self.requisition,
            budget_line=self.budget_line,
            bank_account=bank_account,
            processed_by=self.finance_user,
            amount=2000,
            transaction_date=date(2026, 5, 15),
            bank_reference_number="REF-AUTO-1",
            status=Transaction.Status.CLEARED,
        )

        auto_match_response = self.client.post(
            reverse("reconciliations-auto-match"),
            {"bank_statement": statement.pk},
            format="json",
        )
        self.assertEqual(auto_match_response.status_code, 200)
        self.assertEqual(auto_match_response.data["matched"], 1)

        statement.refresh_from_db()
        line = BankStatementLine.objects.get(pk=line_id)
        transaction.refresh_from_db()
        self.assertTrue(line.matched)
        self.assertEqual(transaction.status, Transaction.Status.RECONCILED)

    def test_bank_statement_file_upload_is_parsed(self):
        bank_account = BankAccount.objects.create(
            account_name="Operations Account",
            bank_name="BPR",
            account_number="1234500011",
            currency="USD",
        )
        statement = BankStatement.objects.create(
            bank_account=bank_account,
            statement_number="TMP-CSV",
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            opening_balance=1000,
            closing_balance=2000,
            imported_by=self.finance_user,
        )
        statement_file = SimpleUploadedFile(
            "statement.csv",
            b"transaction_date,description,reference_number,amount\n2026-06-01,Donation receipt,REF-CSV-1,1000.00\n",
            content_type="text/csv",
        )

        self.client.force_authenticate(self.finance_user)
        response = self.client.post(
            reverse("bank-statements-import-lines", args=[statement.pk]),
            {
                "statement_number": "ST-CSV",
                "period_start": "2026-06-01",
                "period_end": "2026-06-30",
                "opening_balance": "1000.00",
                "closing_balance": "2000.00",
                "statement_file": statement_file,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data["lines"]), 1)
        self.assertEqual(response.data["lines"][0]["reference_number"], "REF-CSV-1")


class FinanceControlsTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.finance_user = User.objects.create_user(
            username="finance-controls",
            email="finance-controls@example.com",
            password="password123",
            full_name="Finance Controls",
            role_id="FINANCE_OFFICER",
        )
        self.client.force_authenticate(self.finance_user)
        donor = Donor.objects.create(
            organization_name="Controls Donor",
            contact_person="Control Person",
            contact_email="control@example.com",
            country="Rwanda",
            category="Foundation",
        )
        grant = Grant.objects.create(
            donor=donor,
            grant_title="Controls Grant",
            total_amount=40000,
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="active",
        )
        self.budget_line = BudgetLine.objects.create(grant=grant, line_name="Operations", allocated_amount=10000, spent_amount=8500)
        self.vendor = Vendor.objects.create(name="Stationery World", category="Supplies")
        self.bank_account = BankAccount.objects.create(
            account_name="Controls Account",
            bank_name="BPR",
            account_number="9988776655",
            currency="USD",
        )

    def test_generate_spending_alerts(self):
        response = self.client.post(reverse("spending-alerts-generate"), format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["created"], 1)
        self.assertTrue(SpendingAlert.objects.filter(budget_line=self.budget_line).exists())

    def test_finance_dashboard_marks_over_budget_state(self):
        self.budget_line.spent_amount = 12000
        self.budget_line.save(update_fields=["spent_amount"])

        response = self.client.get(reverse("finance-dashboard-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["budget_health"]["status"], "over_budget")
        self.assertEqual(response.data["budget_health"]["deficit_amount"], Decimal("2000"))
        self.assertIsNone(response.data["forecast"]["runway_months"])

    def test_payment_batch_processes_scheduled_payments(self):
        payment = ScheduledPayment.objects.create(
            vendor=self.vendor,
            budget_line=self.budget_line,
            bank_account=self.bank_account,
            scheduled_by=self.finance_user,
            description="Office supplies",
            amount=1000,
            due_date=date(2026, 6, 10),
            currency="USD",
            status=ScheduledPayment.Status.SCHEDULED,
        )
        batch = PaymentBatch.objects.create(name="June batch", created_by=self.finance_user)
        payment.batch = batch
        payment.save(update_fields=["batch"])

        response = self.client.post(reverse("payment-batches-process", args=[batch.id]), format="json")
        self.assertEqual(response.status_code, 200, response.data)
        payment.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(batch.status, PaymentBatch.Status.COMPLETED)
        self.assertEqual(payment.status, ScheduledPayment.Status.PAID)

    def test_period_close_prepare_and_close(self):
        statement = BankStatement.objects.create(
            bank_account=self.bank_account,
            statement_number="CLOSE-001",
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            opening_balance=1000,
            closing_balance=2000,
            imported_by=self.finance_user,
        )
        BankStatementLine.objects.create(
            bank_statement=statement,
            transaction_date=date(2026, 6, 10),
            description="Matched line",
            reference_number="CLOSE-REF-1",
            amount=100,
            matched=True,
        )
        close = PeriodClose.objects.create(
            bank_account=self.bank_account,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            prepared_by=self.finance_user,
        )

        prepare_response = self.client.post(reverse("period-closes-prepare", args=[close.id]), format="json")
        self.assertEqual(prepare_response.status_code, 200)
        self.assertEqual(prepare_response.data["status"], PeriodClose.Status.PREPARED)

        close.refresh_from_db()
        close.unmatched_statement_lines = 0
        close.reconciliation_exceptions = 0
        close.save(update_fields=["unmatched_statement_lines", "reconciliation_exceptions"])
        close_response = self.client.post(reverse("period-closes-close", args=[close.id]), format="json")
        self.assertEqual(close_response.status_code, 200)
        close.refresh_from_db()
        self.assertEqual(close.status, PeriodClose.Status.CLOSED)
