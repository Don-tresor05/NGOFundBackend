from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import Notification
from apps.donors.models import Donor
from apps.grants.models import Grant
from apps.projects.models import BudgetLine, Project

User = get_user_model()


class ReallocationWorkflowTests(APITestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="project-manager",
            email="manager@example.com",
            password="password123",
            full_name="Project Manager",
            role_id="PROJECT_MANAGER",
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

    def test_project_creation_notifies_donor_users(self):
        donor_user = User.objects.create_user(
            username="donor-user",
            email="contact@example.com",
            password="password123",
            full_name="Health Equity Fund",
            role_id="DONOR_USER",
        )

        create_response = self.client.post(
            reverse("projects-list"),
            {
                "grant": self.grant.id,
                "name": "Community Health Outreach",
                "description": "Mobile clinics for rural communities.",
                "start_date": "2026-03-01",
                "end_date": "2026-08-31",
                "status": "active",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)

        notification = Notification.objects.filter(user=donor_user, type="new_project").first()
        self.assertIsNotNone(notification)
        self.assertIn("Community Health Outreach", notification.message)
        self.assertIn("Community Health Grant", notification.message)

    def test_creator_without_manager_role_can_edit_own_project_but_not_archive(self):
        staff = User.objects.create_user(
            username="field-staff",
            email="staff@example.com",
            password="password123",
            full_name="Field Staff",
            role_id="FIELD_STAFF",
        )
        self.client.force_authenticate(staff)

        create_response = self.client.post(
            reverse("projects-list"),
            {
                "grant": self.grant.id,
                "name": "Water Access Initiative",
                "start_date": "2026-04-01",
                "end_date": "2026-12-31",
                "status": "active",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201)
        project_id = create_response.data["id"]
        self.assertEqual(create_response.data["created_by"], staff.id)

        # The creator can edit their own project
        patch_response = self.client.patch(
            f"/api/projects/{project_id}/",
            {"name": "Water Access Initiative v2"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)

        # A creator without a manager role cannot archive
        archive_response = self.client.post(reverse("projects-archive", args=[project_id]))
        self.assertEqual(archive_response.status_code, 403)

        # Another staff member cannot edit someone else's project
        other_staff = User.objects.create_user(
            username="field-staff-2",
            email="staff2@example.com",
            password="password123",
            full_name="Field Staff 2",
            role_id="FIELD_STAFF",
        )
        self.client.force_authenticate(other_staff)
        patch_response = self.client.patch(
            f"/api/projects/{project_id}/",
            {"name": "Unauthorized edit"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 403)

    def test_manager_can_archive_and_delete_are_soft(self):
        project = Project.objects.create(
            grant=self.grant,
            name="School Feeding Program",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 11, 30),
            created_by=self.user,
        )

        # PROJECT_MANAGER can edit but cannot archive
        patch_response = self.client.patch(
            f"/api/projects/{project.pk}/",
            {"description": "Expanded scope"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 200)
        archive_response = self.client.post(reverse("projects-archive", args=[project.pk]))
        self.assertEqual(archive_response.status_code, 403)

        # Finance Officer can archive (soft delete)
        finance_officer = User.objects.create_user(
            username="finance-officer",
            email="fo@example.com",
            password="password123",
            full_name="Finance Officer",
            role_id="FINANCE_OFFICER",
        )
        self.client.force_authenticate(finance_officer)
        archive_response = self.client.post(reverse("projects-archive", args=[project.pk]))
        self.assertEqual(archive_response.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.status, Project.Status.CANCELLED)

        # DELETE also soft-archives rather than removing the record
        second_project = Project.objects.create(
            grant=self.grant,
            name="Temporary Cleanup",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 7, 1),
            created_by=finance_officer,
        )
        delete_response = self.client.delete(f"/api/projects/{second_project.pk}/")
        self.assertEqual(delete_response.status_code, 204)
        second_project.refresh_from_db()
        self.assertEqual(second_project.status, Project.Status.CANCELLED)
        self.assertTrue(Project.objects.filter(pk=second_project.pk).exists())

    def test_remove_image_clears_cover(self):
        project = Project.objects.create(
            grant=self.grant,
            name="Covered Project",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            created_by=self.user,
            image=SimpleUploadedFile("cover.jpg", b"fake-image-bytes", content_type="image/jpeg"),
        )
        self.assertTrue(project.image)

        patch_response = self.client.patch(
            f"/api/projects/{project.pk}/",
            {"image": ""},
            format="multipart",
        )
        self.assertEqual(patch_response.status_code, 200)
        project.refresh_from_db()
        self.assertFalse(project.image)

    def test_public_project_list_hides_edit_and_archive_flags(self):
        Project.objects.create(
            grant=self.grant,
            name="Public Project",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            created_by=self.user,
        )
        self.client.force_authenticate(user=None)
        list_response = self.client.get(reverse("projects-list"))
        self.assertEqual(list_response.status_code, 200)
        project_data = list_response.data["results"][0]
        self.assertIs(project_data["can_edit"], False)
        self.assertIs(project_data["can_archive"], False)

    def test_trash_restore_and_permanent_delete_flow(self):
        project = Project.objects.create(
            grant=self.grant,
            name="Trash Test Project",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            created_by=self.user,
        )

        # PROJECT_MANAGER cannot move to trash, restore, or permanently delete
        archive_response = self.client.post(reverse("projects-archive", args=[project.pk]))
        self.assertEqual(archive_response.status_code, 403)
        restore_response = self.client.post(reverse("projects-restore", args=[project.pk]))
        self.assertEqual(restore_response.status_code, 403)
        delete_response = self.client.post(reverse("projects-delete-permanently", args=[project.pk]))
        self.assertEqual(delete_response.status_code, 403)

        # Finance Officer can move to trash
        finance_officer = User.objects.create_user(
            username="finance-officer",
            email="fo@example.com",
            password="password123",
            full_name="Finance Officer",
            role_id="FINANCE_OFFICER",
        )
        self.client.force_authenticate(finance_officer)
        archive_response = self.client.post(reverse("projects-archive", args=[project.pk]))
        self.assertEqual(archive_response.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.status, Project.Status.CANCELLED)

        # Finance Officer can restore — the project returns to its pre-trash status
        restore_response = self.client.post(reverse("projects-restore", args=[project.pk]))
        self.assertEqual(restore_response.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.status, Project.Status.PENDING)

        # A completed project also restores to completed, not active
        completed_project = Project.objects.create(
            grant=self.grant,
            name="Completed Project",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 1),
            status=Project.Status.COMPLETED,
            created_by=finance_officer,
        )
        self.client.post(reverse("projects-archive", args=[completed_project.pk]))
        self.client.post(reverse("projects-restore", args=[completed_project.pk]))
        completed_project.refresh_from_db()
        self.assertEqual(completed_project.status, Project.Status.COMPLETED)

        # Trashed projects cannot be edited
        self.client.post(reverse("projects-archive", args=[project.pk]))
        patch_response = self.client.patch(
            f"/api/projects/{project.pk}/",
            {"name": "Unauthorized edit"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, 400)

        # Active projects cannot be permanently deleted — must be in the trash first
        restore_response = self.client.post(reverse("projects-restore", args=[project.pk]))
        self.assertEqual(restore_response.status_code, 200)
        delete_response = self.client.post(reverse("projects-delete-permanently", args=[project.pk]))
        self.assertEqual(delete_response.status_code, 400)

        # Move to trash again, then permanently delete
        self.client.post(reverse("projects-archive", args=[project.pk]))
        delete_response = self.client.post(reverse("projects-delete-permanently", args=[project.pk]))
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_project_lifecycle_transitions(self):
        project = Project.objects.create(
            grant=self.grant,
            name="Community Clinic Upgrade",
            description="Upgrade the clinic infrastructure.",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 10, 31),
        )

        activate_response = self.client.post(reverse("projects-activate", args=[project.pk]))
        self.assertEqual(activate_response.status_code, 200)
        self.assertEqual(activate_response.data["status"], Project.Status.ACTIVE)

        complete_response = self.client.post(reverse("projects-complete", args=[project.pk]))
        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(complete_response.data["status"], Project.Status.COMPLETED)

        reopen_response = self.client.post(reverse("projects-reopen", args=[project.pk]))
        self.assertEqual(reopen_response.status_code, 200)
        self.assertEqual(reopen_response.data["status"], Project.Status.ACTIVE)
