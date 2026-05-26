from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.testing_validation.models import TestCase, UATFeedback
from apps.testing_validation.serializers import TestCaseSerializer, UATFeedbackSerializer


class TestCaseViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = TestCase.objects.select_related("created_by")
    serializer_class = TestCaseSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN, Role.EXTERNAL_AUDITOR, Role.EXECUTIVE_DIRECTOR]
    filterset_fields = ["created_by", "environment", "status", "priority"]
    search_fields = ["title", "scenario", "environment"]
    ordering_fields = ["created_at", "status", "priority"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)


class UATFeedbackViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = UATFeedback.objects.select_related("test_case", "submitted_by")
    serializer_class = UATFeedbackSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN, Role.EXTERNAL_AUDITOR, Role.EXECUTIVE_DIRECTOR]
    filterset_fields = ["test_case", "submitted_by", "status"]
    search_fields = ["feedback", "test_case__title"]
    ordering_fields = ["created_at", "status"]

    def perform_create(self, serializer):
        instance = serializer.save(submitted_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)
