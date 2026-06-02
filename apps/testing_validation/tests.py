from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.testing_validation.models import BugReport, ReleaseNote, TestCase, UATFeedback

User = get_user_model()


class TestingValidationWorkflowTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="executive",
            email="executive@example.com",
            password="password123",
            full_name="Executive Director",
            role_id="EXECUTIVE_DIRECTOR",
        )
        self.client.force_authenticate(self.user)

    def test_test_case_status_actions(self):
        test_case = TestCase.objects.create(
            created_by=self.user,
            title="Login smoke test",
            scenario="Verify role portal login.",
            environment="Staging",
        )

        start_response = self.client.post(reverse("test-cases-start", args=[test_case.pk]))
        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(start_response.data["status"], TestCase.Status.IN_PROGRESS)

        review_response = self.client.post(reverse("test-cases-review", args=[test_case.pk]))
        self.assertEqual(review_response.status_code, 200)
        self.assertEqual(review_response.data["status"], TestCase.Status.IN_REVIEW)

        approve_response = self.client.post(reverse("test-cases-approve", args=[test_case.pk]))
        self.assertEqual(approve_response.status_code, 200)
        self.assertEqual(approve_response.data["status"], TestCase.Status.APPROVED)

        direct_reject_response = self.client.patch(
            reverse("test-cases-detail", args=[test_case.pk]),
            {"status": TestCase.Status.REJECTED},
            format="json",
        )
        self.assertEqual(direct_reject_response.status_code, 400)

    def test_uat_feedback_actions(self):
        test_case = TestCase.objects.create(
            created_by=self.user,
            title="Signup smoke test",
            scenario="Verify role-specific create account flow.",
            environment="Staging",
        )
        feedback = UATFeedback.objects.create(
            test_case=test_case,
            submitted_by=self.user,
            feedback="The final submission button should be more prominent.",
        )

        resolve_response = self.client.post(reverse("uat-feedback-resolve", args=[feedback.pk]))
        self.assertEqual(resolve_response.status_code, 200)
        self.assertEqual(resolve_response.data["status"], UATFeedback.Status.RESOLVED)

        close_response = self.client.post(reverse("uat-feedback-close", args=[feedback.pk]))
        self.assertEqual(close_response.status_code, 200)
        self.assertEqual(close_response.data["status"], UATFeedback.Status.CLOSED)

    def test_bug_board_and_release_notes(self):
        bug = BugReport.objects.create(
            reported_by=self.user,
            title="Login page alignment issue",
            description="The login card is slightly elevated.",
            environment="Staging",
            severity=BugReport.Severity.MEDIUM,
        )
        triage_response = self.client.post(reverse("bug-reports-triage", args=[bug.pk]))
        self.assertEqual(triage_response.status_code, 200)
        self.assertEqual(triage_response.data["status"], BugReport.Status.TRIAGED)

        release_note = ReleaseNote.objects.create(
            version="v1.2.0",
            title="Workflow hardening release",
            summary="Adds workflow controls and board actions.",
            changelog="Added approval chains and schedules.",
            environment="Production",
            created_by=self.user,
        )
        publish_response = self.client.post(reverse("release-notes-publish", args=[release_note.pk]))
        self.assertEqual(publish_response.status_code, 200)
        self.assertEqual(publish_response.data["status"], ReleaseNote.Status.PUBLISHED)
