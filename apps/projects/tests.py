from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.donors.models import Donor
from apps.grants.models import Grant
from apps.projects.models import BudgetLine

User = get_user_model()


class ReallocationWorkflowTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="project-manager",
            email="manager@example.com",
            password="password123",
            full_name="Project Manager",
            role="PROJECT_MANAGER",
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
            total_amount=50000,
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            status="active",
        )
        self.source = BudgetLine.objects.create(grant=self.grant, line_name="Training", allocated_amount=20000, spent_amount=4000)
        self.target = BudgetLine.objects.create(grant=self.grant, line_name="Medical Supplies", allocated_amount=10000, spent_amount=1000)

    def test_reallocation_approval_moves_budget(self):
        create_response = self.client.post(
            reverse("reallocation-requests-list"),
            {
                "source_budget_line": self.source.id,
                "target_budget_line": self.target.id,
                "amount": "3000.00",
                "reason": "Shift funds to urgent supplies.",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)

        approve_response = self.client.post(reverse("reallocation-requests-approve", args=[create_response.data["id"]]))
        self.assertEqual(approve_response.status_code, 200)

        self.source.refresh_from_db()
        self.target.refresh_from_db()
        self.assertEqual(str(self.source.allocated_amount), "17000.00")
        self.assertEqual(str(self.target.allocated_amount), "13000.00")

