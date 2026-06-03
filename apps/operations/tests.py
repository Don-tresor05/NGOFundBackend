from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient

from apps.operations.models import ProcessDocument, StaffRequirement

User = get_user_model()


class StaffRequirementWorkflowTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="superadmin",
            email="superadmin@example.com",
            password="password123",
            full_name="Super Admin",
            role_id="SUPER_ADMIN",
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

    def test_process_document_publish_flow(self):
        document = ProcessDocument.objects.create(
            title="Procurement Procedure",
            version="v1",
            summary="Procurement operating procedure",
            content="1. Receive request\n2. Review\n3. Approve",
            created_by=self.user,
        )

        submit_response = self.client.post(reverse("process-documents-submit-for-review", args=[document.pk]))
        self.assertEqual(submit_response.status_code, 200)
        self.assertEqual(submit_response.data["status"], ProcessDocument.Status.IN_REVIEW)

        approve_response = self.client.post(reverse("process-documents-approve", args=[document.pk]))
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.data["status"], ProcessDocument.Status.APPROVED)

        publish_response = self.client.post(reverse("process-documents-publish", args=[document.pk]))
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.data["status"], ProcessDocument.Status.PUBLISHED)

        revise_response = self.client.post(reverse("process-documents-revise", args=[document.pk]))
        self.assertEqual(revise_response.status_code, 201)
        self.assertEqual(revise_response.data["status"], ProcessDocument.Status.DRAFT)
        self.assertEqual(revise_response.data["version"], "v2")
