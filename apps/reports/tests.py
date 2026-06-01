from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.donors.models import Donor
from apps.grants.models import Grant
from apps.reports.models import Report, ReportDelivery, ReportSchedule

User = get_user_model()


class ReportWorkflowTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="finance",
            email="finance@example.com",
            password="password123",
            full_name="Finance Officer",
            role="FINANCE_OFFICER",
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

        report = Report.objects.create(
            grant=self.grant,
            generated_by=self.user,
            report_type="Quarterly Finance",
            format="PDF",
        )
        deliver_response = self.client.post(
            reverse("reports-deliver", args=[report.id]),
            {"destination": "board@example.com", "delivery_method": "email"},
            format="json",
        )
        self.assertEqual(deliver_response.status_code, 200)
        self.assertTrue(ReportDelivery.objects.filter(report=report, status=ReportDelivery.Status.SENT).exists())

        deliveries_response = self.client.get(reverse("report-deliveries-list"))
        self.assertEqual(deliveries_response.status_code, 200)
        self.assertGreaterEqual(len(deliveries_response.data), 1)
