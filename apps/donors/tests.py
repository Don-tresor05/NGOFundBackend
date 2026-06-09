from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.donors.models import Donor, DonorCommunication

User = get_user_model()


class DonorEngagementTests(APITestCase):
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
        self.donor = self.client.post(
            reverse("donors-list"),
            {
                "organization_name": "Hope Foundation",
                "contact_person": "Sarah Donor",
                "contact_email": "sarah@example.com",
                "country": "Rwanda",
                "category": "Foundation",
            },
            format="json",
        ).data

    def test_acknowledge_creates_communication(self):
        response = self.client.post(
            reverse("donors-acknowledge", args=[self.donor["id"]]),
            {"channel": "email"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(DonorCommunication.objects.filter(donor_id=self.donor["id"]).exists())

    def test_engagement_dashboard_returns_summary(self):
        self.client.post(
            reverse("donors-acknowledge", args=[self.donor["id"]]),
            {"channel": "email"},
            format="json",
        )
        response = self.client.get(reverse("donors-engagement-dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_donors"], 1)
        self.assertGreaterEqual(response.data["total_communications"], 1)

    def test_donor_portal_update_is_self_service(self):
        donor_user = User.objects.create_user(
            username="donor",
            email="sarah@example.com",
            password="password123",
            full_name="Sarah Donor",
            role_id="DONOR_USER",
        )
        self.client.force_authenticate(donor_user)
        response = self.client.patch(
            reverse("donors-me"),
            {
                "contact_person": "Sarah Donor",
                "contact_email": "updated@example.com",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        donor = Donor.objects.get(pk=self.donor["id"])
        self.assertEqual(donor.contact_email, "updated@example.com")
