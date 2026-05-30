from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.operations.models import ProcessDocument, StaffRequirement
from apps.operations.serializers import ProcessDocumentSerializer, StaffRequirementSerializer


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


class ProcessDocumentViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ProcessDocument.objects.select_related("created_by", "approved_by")
    serializer_class = ProcessDocumentSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN, Role.FIELD_STAFF, Role.PROJECT_MANAGER, Role.EXECUTIVE_DIRECTOR]
    filterset_fields = ["created_by", "approved_by", "status"]
    search_fields = ["title", "summary", "content", "version"]
    ordering_fields = ["created_at", "updated_at", "status", "version"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="submit-for-review")
    def submit_for_review(self, request, pk=None):
        document = self.get_object()
        document.status = ProcessDocument.Status.IN_REVIEW
        document.save(update_fields=["status"])
        self._write_audit_log("PROCESS_DOCUMENT_SUBMITTED", document)
        return Response(self.get_serializer(document).data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        document = self.get_object()
        document.status = ProcessDocument.Status.APPROVED
        document.approved_by = request.user
        document.save(update_fields=["status", "approved_by"])
        self._write_audit_log("PROCESS_DOCUMENT_APPROVED", document)
        return Response(self.get_serializer(document).data)

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, pk=None):
        document = self.get_object()
        document.status = ProcessDocument.Status.PUBLISHED
        document.approved_by = request.user
        document.save(update_fields=["status", "approved_by"])
        self._write_audit_log("PROCESS_DOCUMENT_PUBLISHED", document)
        return Response(self.get_serializer(document).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        document = self.get_object()
        document.status = ProcessDocument.Status.REJECTED
        document.save(update_fields=["status"])
        self._write_audit_log("PROCESS_DOCUMENT_REJECTED", document)
        return Response(self.get_serializer(document).data)
