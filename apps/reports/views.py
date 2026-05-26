from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.reports.models import Report
from apps.reports.serializers import ReportSerializer


class ReportViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Report.objects.select_related("grant", "generated_by")
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR, Role.EXTERNAL_AUDITOR]
    filterset_fields = ["grant", "generated_by", "report_type", "format"]
    search_fields = ["report_type", "grant__grant_title"]
    ordering_fields = ["created_at", "report_type", "format"]

    def perform_create(self, serializer):
        instance = serializer.save(generated_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)
