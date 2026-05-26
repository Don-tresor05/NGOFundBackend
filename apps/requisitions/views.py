from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.requisitions.models import Requisition
from apps.requisitions.serializers import RequisitionSerializer


class RequisitionViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Requisition.objects.select_related("submitted_by", "budget_line", "budget_line__grant")
    serializer_class = RequisitionSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FIELD_STAFF, Role.PROJECT_MANAGER, Role.EXECUTIVE_DIRECTOR, Role.FINANCE_OFFICER]
    filterset_fields = ["submitted_by", "budget_line", "status"]
    search_fields = ["description", "rejection_reason", "submitted_by__full_name"]
    ordering_fields = ["created_at", "amount", "status"]

    def perform_create(self, serializer):
        instance = serializer.save(submitted_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        requisition = self.get_object()
        requisition.status = Requisition.Status.APPROVED
        requisition.rejection_reason = ""
        requisition.save(update_fields=["status", "rejection_reason"])
        self._write_audit_log("REQUISITION_APPROVED", requisition)
        return Response(self.get_serializer(requisition).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        requisition = self.get_object()
        requisition.status = Requisition.Status.REJECTED
        requisition.rejection_reason = request.data.get("rejection_reason", "")
        requisition.save(update_fields=["status", "rejection_reason"])
        self._write_audit_log("REQUISITION_REJECTED", requisition)
        return Response(self.get_serializer(requisition).data, status=status.HTTP_200_OK)
