from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.donors.models import Donor
from apps.finance.models import ExpenseApproval
from apps.grants.models import Grant
from apps.projects.models import BudgetLine
from apps.requisitions.models import Requisition

User = get_user_model()


class ExpenseApprovalWorkflowTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="field-staff",
            email="field@example.com",
            password="password123",
            full_name="Field Staff",
            role="FIELD_STAFF",
        )
        self.client.force_authenticate(self.user)
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
            submitted_by=self.user,
            budget_line=self.budget_line,
            amount=2000,
            description="Procure maternal care kits",
        )

    def test_expense_approval_approve_updates_requisition(self):
        approval = self.client.post(
            reverse("expense-approvals-list"),
            {"requisition": self.requisition.id, "notes": "Initial request submitted."},
            format="json",
        )
        self.assertEqual(approval.status_code, 201)

        approve_response = self.client.post(reverse("expense-approvals-approve", args=[approval.data["id"]]))
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.data["stage"], ExpenseApproval.Stage.APPROVED)

        self.requisition.refresh_from_db()
        self.assertEqual(self.requisition.status, Requisition.Status.APPROVED)

