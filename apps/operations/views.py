from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.operations.models import StaffRequirement
from apps.operations.serializers import StaffRequirementSerializer


class StaffRequirementViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = StaffRequirement.objects.select_related("captured_by", "signed_off_by")
    serializer_class = StaffRequirementSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN, Role.FIELD_STAFF, Role.PROJECT_MANAGER, Role.EXECUTIVE_DIRECTOR]
    filterset_fields = ["captured_by", "validation_status", "process_area"]
    search_fields = ["interviewee_name", "process_area", "feedback"]
    ordering_fields = ["created_at", "validation_status"]

    def perform_create(self, serializer):
        instance = serializer.save(captured_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        requirement = self.get_object()
        requirement.validation_status = StaffRequirement.ValidationStatus.IN_REVIEW
        requirement.save(update_fields=["validation_status"])
        self._write_audit_log("REQUIREMENT_REVIEWED", requirement)
        return Response(self.get_serializer(requirement).data)

    @action(detail=True, methods=["post"], url_path="sign-off")
    def sign_off(self, request, pk=None):
        requirement = self.get_object()
        requirement.validation_status = StaffRequirement.ValidationStatus.APPROVED
        requirement.signed_off_by = request.user
        requirement.signed_off_at = timezone.now()
        requirement.save(update_fields=["validation_status", "signed_off_by", "signed_off_at"])
        self._write_audit_log("REQUIREMENT_SIGNED_OFF", requirement)
        return Response(self.get_serializer(requirement).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        requirement = self.get_object()
        requirement.validation_status = StaffRequirement.ValidationStatus.REJECTED
        requirement.signed_off_by = None
        requirement.signed_off_at = None
        requirement.save(update_fields=["validation_status", "signed_off_by", "signed_off_at"])
        self._write_audit_log("REQUIREMENT_REJECTED", requirement)
        return Response(self.get_serializer(requirement).data)
