from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Notification, PasswordResetRequest, SignupOtp, SystemSetting

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
        self.assertEqual(request_response.status_code, 200)
        self.assertEqual(
            request_response.data["detail"],
            "If the account exists, a password reset token has been issued.",
        )

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

    def test_signup_otp_flow_registers_inactive_user_then_verifies(self):
        signup_response = self.client.post(
            reverse("register"),
            {
                "full_name": "New Donor User",
                "email": "new.donor@example.com",
                "password": "password123",
                "role": "DONOR_USER",
                "phone": "+250700000000",
                "location": "Kigali",
                "department": "Donor",
            },
            format="json",
        )
        self.assertEqual(signup_response.status_code, 201)
        self.assertTrue(signup_response.data["verification_required"])
        self.assertEqual(signup_response.data["email"], "new.donor@example.com")

        created_user = User.objects.get(email="new.donor@example.com")
        self.assertFalse(created_user.is_active)
        otp = signup_response.data.get("otp") or SignupOtp.objects.filter(user=created_user).latest("created_at").otp
        self.assertEqual(SignupOtp.objects.filter(user=created_user, otp=otp).count(), 1)

        verify_response = self.client.post(
            reverse("signup_verify_otp"),
            {"email": "new.donor@example.com", "otp": otp},
            format="json",
        )
        self.assertEqual(verify_response.status_code, 200)
        self.assertIn("access", verify_response.data)
        self.assertIn("refresh", verify_response.data)

        created_user.refresh_from_db()
        self.assertTrue(created_user.is_active)

    def test_signup_otp_resend_issues_new_code_for_inactive_user(self):
        signup_response = self.client.post(
            reverse("register"),
            {
                "full_name": "Pending User",
                "email": "pending.user@example.com",
                "password": "password123",
                "role": "DONOR_USER",
                "phone": "+250700000001",
                "location": "Kigali",
                "department": "Donor",
            },
            format="json",
        )
        first_otp = signup_response.data.get("otp") or SignupOtp.objects.filter(user__email="pending.user@example.com").latest("created_at").otp

        resend_response = self.client.post(
            reverse("signup_resend_otp"),
            {"email": "pending.user@example.com"},
            format="json",
        )
        self.assertEqual(resend_response.status_code, 200)
        resent_otp = resend_response.data.get("otp") or SignupOtp.objects.filter(user__email="pending.user@example.com").latest("created_at").otp
        self.assertNotEqual(first_otp, resent_otp)
        self.assertEqual(SignupOtp.objects.filter(user__email="pending.user@example.com", is_used=False).count(), 1)

    def test_signup_can_reuse_pending_inactive_account(self):
        first_response = self.client.post(
            reverse("register"),
            {
                "full_name": "Reuse Pending",
                "email": "reuse.pending@example.com",
                "password": "password123",
                "role": "DONOR_USER",
                "phone": "+250700000002",
                "location": "Kigali",
                "department": "Donor",
            },
            format="json",
        )
        self.assertEqual(first_response.status_code, 201)
        first_otp = SignupOtp.objects.filter(user__email="reuse.pending@example.com").latest("created_at").otp

        second_response = self.client.post(
            reverse("register"),
            {
                "full_name": "Reuse Pending Updated",
                "email": "reuse.pending@example.com",
                "password": "password123",
                "role": "DONOR_USER",
                "phone": "+250700000003",
                "location": "Kigali",
                "department": "Donor",
            },
            format="json",
        )
        self.assertEqual(second_response.status_code, 201)
        second_otp = SignupOtp.objects.filter(user__email="reuse.pending@example.com").latest("created_at").otp
        self.assertNotEqual(first_otp, second_otp)

        pending_user = User.objects.get(email="reuse.pending@example.com")
        self.assertFalse(pending_user.is_active)
        self.assertEqual(pending_user.full_name, "Reuse Pending Updated")

    def test_signup_rejects_existing_active_account_with_conflict(self):
        response = self.client.post(
            reverse("register"),
            {
                "full_name": "Super Admin Duplicate",
                "email": "superadmin@example.com",
                "password": "password123",
                "role": "SUPER_ADMIN",
                "phone": "+250700000004",
                "location": "Kigali",
                "department": "Admin",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.data["conflict"])
