from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import PasswordResetRequest

User = get_user_model()


class AccountSecurityTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="superadmin",
            email="superadmin@example.com",
            password="password123",
            full_name="Super Admin",
            role="SUPER_ADMIN",
        )
        self.target = User.objects.create_user(
            username="finance",
            email="finance@example.com",
            password="password123",
            full_name="Finance Officer",
            role="FINANCE_OFFICER",
        )
        self.client.force_authenticate(self.admin)

    def test_password_reset_request_and_confirm(self):
        request_response = self.client.post(
            reverse("users-password-reset-request"),
            {"email": self.target.email},
            format="json",
        )
        self.assertEqual(request_response.status_code, 201)

        reset_request = PasswordResetRequest.objects.latest("created_at")
        confirm_response = self.client.post(
            reverse("users-password-reset-confirm"),
            {"token": reset_request.token, "new_password": "new-password123"},
            format="json",
        )
        self.assertEqual(confirm_response.status_code, 200)

        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password("new-password123"))

