from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient

from apps.operations.models import StaffRequirement

User = get_user_model()


class StaffRequirementWorkflowTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="superadmin",
            email="superadmin@example.com",
            password="password123",
            full_name="Super Admin",
            role="SUPER_ADMIN",
        )
        self.client.force_authenticate(self.user)

    def test_review_signoff_and_reject_actions(self):
        requirement = StaffRequirement.objects.create(
            captured_by=self.user,
            interviewee_name="Grace Field",
            process_area="Procurement",
            feedback="Need a documented approval flow.",
        )

        review_response = self.client.post(reverse("staff-requirements-review", args=[requirement.pk]))
        self.assertEqual(review_response.status_code, 200)
        self.assertEqual(review_response.data["validation_status"], StaffRequirement.ValidationStatus.IN_REVIEW)

        sign_off_response = self.client.post(reverse("staff-requirements-sign-off", args=[requirement.pk]))
        self.assertEqual(sign_off_response.status_code, 200)
        self.assertEqual(sign_off_response.data["validation_status"], StaffRequirement.ValidationStatus.APPROVED)
        self.assertIsNotNone(sign_off_response.data["signed_off_at"])

        rejected = StaffRequirement.objects.create(
            captured_by=self.user,
            interviewee_name="Patrick Manager",
            process_area="Finance Controls",
            feedback="Missing reconciliation controls.",
        )
        reject_response = self.client.post(reverse("staff-requirements-reject", args=[rejected.pk]))
        self.assertEqual(reject_response.status_code, 200)
        self.assertEqual(reject_response.data["validation_status"], StaffRequirement.ValidationStatus.REJECTED)
        self.assertIsNone(reject_response.data["signed_off_by"])
        self.assertIsNone(reject_response.data["signed_off_at"])

    def test_direct_invalid_approval_update_is_rejected(self):
        requirement = StaffRequirement.objects.create(
            captured_by=self.user,
            interviewee_name="Aline Director",
            process_area="Governance",
            feedback="Review governance process.",
        )

        response = self.client.patch(
            reverse("staff-requirements-detail", args=[requirement.pk]),
            {"validation_status": StaffRequirement.ValidationStatus.APPROVED},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
