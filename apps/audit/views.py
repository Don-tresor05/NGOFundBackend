from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.audit.models import AuditLog, Document
from apps.audit.serializers import AuditLogSerializer, DocumentSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("user")
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXTERNAL_AUDITOR, Role.EXECUTIVE_DIRECTOR]
    filterset_fields = ["user", "action_type", "target_entity_type"]
    search_fields = ["action_type", "target_entity_type", "details", "ip_address"]
    ordering_fields = ["timestamp", "action_type"]


class DocumentViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Document.objects.select_related("uploaded_by")
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXTERNAL_AUDITOR, Role.EXECUTIVE_DIRECTOR, Role.FIELD_STAFF]
    filterset_fields = ["uploaded_by", "related_entity_type", "document_type"]
    search_fields = ["related_entity_type", "document_type"]
    ordering_fields = ["uploaded_at", "document_type"]

    def perform_create(self, serializer):
        instance = serializer.save(uploaded_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)
