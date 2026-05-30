from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.compliance.models import ComplianceItem

User = get_user_model()


class ComplianceWorkflowTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="auditor",
            email="auditor@example.com",
            password="password123",
            full_name="External Auditor",
            role="EXTERNAL_AUDITOR",
        )
        self.client.force_authenticate(self.user)

    def test_verify_and_unverify_actions(self):
        item = ComplianceItem.objects.create(title="Donor consent evidence attached", owner="Fundraising")

        verify_response = self.client.post(reverse("compliance-items-verify", args=[item.pk]))
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(verify_response.data["verified"])
        self.assertIsNotNone(verify_response.data["verified_by"])

        unverify_response = self.client.post(reverse("compliance-items-unverify", args=[item.pk]))
        self.assertEqual(unverify_response.status_code, 200)
        self.assertFalse(unverify_response.data["verified"])
        self.assertIsNone(unverify_response.data["verified_by"])
        self.assertIsNone(unverify_response.data["verified_at"])
