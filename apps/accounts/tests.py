from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Notification, PasswordResetRequest, SystemSetting

User = get_user_model()


class AccountSecurityTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="superadmin",
            email="superadmin@example.com",
            password="password123",
            full_name="Super Admin",
            role_id="SUPER_ADMIN",
        )
        self.target = User.objects.create_user(
            username="finance",
            email="finance@example.com",
            password="password123",
            full_name="Finance Officer",
            role_id="FINANCE_OFFICER",
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

    def test_notification_lifecycle_and_summary(self):
        notification = Notification.objects.create(
            user=self.target,
            type="system",
            title="Security notice",
            message="Please review your password policy.",
        )

        summary_response = self.client.get(reverse("notifications-summary"))
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.data["unread"], 1)

        mark_read_response = self.client.post(reverse("notifications-mark-read", args=[notification.pk]))
        self.assertEqual(mark_read_response.status_code, 200)
        self.assertTrue(mark_read_response.data["is_read"])

        mark_unread_response = self.client.post(reverse("notifications-mark-unread", args=[notification.pk]))
        self.assertEqual(mark_unread_response.status_code, 200)
        self.assertFalse(mark_unread_response.data["is_read"])

    def test_permission_matrix_blocks_users_endpoint_for_non_admin(self):
        self.client.force_authenticate(self.target)
        response = self.client.get(reverse("users-list"))
        self.assertEqual(response.status_code, 403)

    def test_system_settings_summary_and_bulk_update(self):
        SystemSetting.objects.create(
            setting_key="session_timeout_minutes",
            label="Session Timeout",
            setting_value="45",
            setting_group=SystemSetting.SettingGroup.ACCESS,
        )

        summary_response = self.client.get(reverse("system-settings-summary"))
        self.assertEqual(summary_response.status_code, 200)
        self.assertEqual(summary_response.data["access_timeout_minutes"], 45)

        bulk_response = self.client.post(
            reverse("system-settings-bulk-update"),
            [
                {
                    "setting_key": "session_timeout_minutes",
                    "label": "Session Timeout",
                    "setting_value": "60",
                    "setting_group": SystemSetting.SettingGroup.ACCESS,
                },
                {
                    "setting_key": "approval_alerts",
                    "label": "Approval Alerts",
                    "setting_value": "enabled",
                    "setting_group": SystemSetting.SettingGroup.NOTIFICATIONS,
                },
            ],
            format="json",
        )
        self.assertEqual(bulk_response.status_code, 200)
        self.assertEqual(SystemSetting.objects.get(setting_key="session_timeout_minutes").setting_value, "60")
