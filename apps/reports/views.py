from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.reports.models import Report, ReportDelivery, ReportSchedule
from apps.reports.serializers import ReportDeliverySerializer, ReportScheduleSerializer, ReportSerializer


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

    @action(detail=True, methods=["post"], url_path="deliver")
    def deliver(self, request, pk=None):
        report = self.get_object()
        destination = request.data.get("destination", request.user.email)
        delivery_method = request.data.get("delivery_method", "email")
        delivery = ReportDelivery.objects.create(
            report=report,
            created_by=request.user,
            delivery_method=delivery_method,
            destination=destination,
            status=ReportDelivery.Status.SENT,
            sent_at=timezone.now(),
        )
        self._write_audit_log("REPORT_DELIVERED", report)
        return Response(ReportDeliverySerializer(delivery).data)


class ReportScheduleViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ReportSchedule.objects.select_related("grant", "created_by")
    serializer_class = ReportScheduleSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    filterset_fields = ["grant", "created_by", "frequency", "delivery_method", "is_active"]
    search_fields = ["report_type", "recipient_emails"]
    ordering_fields = ["created_at", "next_run_at", "frequency"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        schedule = self.get_object()
        schedule.is_active = True
        schedule.save(update_fields=["is_active"])
        self._write_audit_log("REPORT_SCHEDULE_ACTIVATED", schedule)
        return Response(self.get_serializer(schedule).data)

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        schedule = self.get_object()
        schedule.is_active = False
        schedule.save(update_fields=["is_active"])
        self._write_audit_log("REPORT_SCHEDULE_DEACTIVATED", schedule)
        return Response(self.get_serializer(schedule).data)
