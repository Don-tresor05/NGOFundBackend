from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from apps.audit.models import AuditLog

User = get_user_model()


class AuditRepositoryTests(APITestCase):
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

    def test_document_upload_creates_audit_log(self):
        document = SimpleUploadedFile("receipt.txt", b"receipt contents", content_type="text/plain")

        response = self.client.post(
            reverse("documents-list"),
            {
                "related_entity_type": "requisition",
                "related_entity_id": 1,
                "document_type": "receipt",
                "file": document,
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["uploaded_by"], self.user.id)
        self.assertTrue(
            AuditLog.objects.filter(user=self.user, action_type="CREATED", target_entity_type="document").exists()
        )
