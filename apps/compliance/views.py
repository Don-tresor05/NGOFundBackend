from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.compliance.models import ComplianceItem
from apps.compliance.serializers import ComplianceItemSerializer


class ComplianceItemViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ComplianceItem.objects.select_related("verified_by")
    serializer_class = ComplianceItemSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.EXTERNAL_AUDITOR, Role.EXECUTIVE_DIRECTOR, Role.FINANCE_OFFICER]
    filterset_fields = ["verified", "owner", "verified_by"]
    search_fields = ["title", "owner"]
    ordering_fields = ["title", "verified_at"]

    @action(detail=True, methods=["post"], url_path="verify")
    def verify(self, request, pk=None):
        item = self.get_object()
        if not item.verified:
            item.verified = True
            item.verified_by = request.user
            item.verified_at = timezone.now()
        item.save(update_fields=["verified", "verified_by", "verified_at"])
        self._write_audit_log("COMPLIANCE_VERIFIED", item)
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"], url_path="unverify")
    def unverify(self, request, pk=None):
        item = self.get_object()
        item.verified = False
        item.verified_by = None
        item.verified_at = None
        item.save(update_fields=["verified", "verified_by", "verified_at"])
        self._write_audit_log("COMPLIANCE_UNVERIFIED", item)
        return Response(self.get_serializer(item).data)
