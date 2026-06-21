from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.reports.models import Report, ReportDelivery, ReportSchedule, ReportTemplate
from apps.reports.serializers import (
    ReportDeliverySerializer,
    ReportScheduleSerializer,
    ReportSerializer,
    ReportTemplateSerializer,
)
from apps.reports.services import dispatch_report_delivery, run_report_schedule


class ReportTemplateViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ReportTemplate.objects.select_related("created_by")
    serializer_class = ReportTemplateSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.SUPER_ADMIN]
    required_permissions = ["manage_reports"]
    filterset_fields = ["is_active", "created_by"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=False, methods=["get"], url_path="available-fields")
    def available_fields(self, request):
        return Response({
            "donor_fields": ["organization_name", "contact_person", "contact_email", "country", "category", "status"],
            "grant_fields": ["grant_title", "donor", "total_amount", "grant_date", "start_date", "end_date", "status"],
            "project_fields": ["name", "grant", "start_date", "end_date", "status"],
            "transaction_fields": ["amount", "currency", "base_amount", "transaction_date", "bank_reference_number", "status"],
            "budget_fields": ["line_name", "allocated_amount", "spent_amount", "remaining_amount"],
            "requisition_fields": ["description", "amount", "requisition_date", "status"],
        })


class ReportViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Report.objects.select_related("grant", "generated_by")
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR, Role.EXTERNAL_AUDITOR]
    required_permissions = ["manage_reports"]
    filterset_fields = ["grant", "generated_by", "report_type", "format"]
    search_fields = ["report_type", "grant__grant_title"]
    ordering_fields = ["created_at", "report_type", "format"]

    def perform_create(self, serializer):
        instance = serializer.save(generated_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)
        
        # Notify donors who funded this grant's project
        if instance.grant:
            from apps.accounts.models import User, Notification
            from apps.donors.models import Donor
            
            donor = instance.grant.donor
            if donor:
                donor_user = User.objects.filter(email=donor.contact_email).first()
                if donor_user:
                    project_name = instance.grant.project_set.first().name if instance.grant.project_set.exists() else instance.grant.grant_title
                    Notification.objects.create(
                        user=donor_user,
                        type='impact_report_ready',
                        title='New Impact Report Available',
                        message=f'A new {instance.report_type} report is ready for {project_name}. See the impact of your contribution!'
                    )

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
        )
        dispatch_report_delivery(delivery)
        self._write_audit_log("REPORT_DELIVERED", report)
        return Response(ReportDeliverySerializer(delivery).data)


class ReportDeliveryViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ReportDelivery.objects.select_related("report", "created_by")
    serializer_class = ReportDeliverySerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR, Role.EXTERNAL_AUDITOR]
    required_permissions = ["manage_reports"]
    filterset_fields = ["report", "created_by", "delivery_method", "status"]
    search_fields = ["destination", "report__report_type"]
    ordering_fields = ["created_at", "sent_at", "status"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="dispatch", url_name="dispatch")
    def dispatch_delivery(self, request, pk=None):
        delivery = self.get_object()
        dispatch_report_delivery(delivery)
        self._write_audit_log("REPORT_DELIVERY_DISPATCHED", delivery)
        return Response(self.get_serializer(delivery).data)


class ReportScheduleViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ReportSchedule.objects.select_related("grant", "created_by")
    serializer_class = ReportScheduleSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_reports"]
    action_roles = {
        "run": [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
        "activate": [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
        "deactivate": [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
    }
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

    @action(detail=True, methods=["post"], url_path="run")
    def run(self, request, pk=None):
        schedule = self.get_object()
        deliveries = run_report_schedule(schedule, triggered_by=request.user)
        self._write_audit_log("REPORT_SCHEDULE_RUN", schedule)
        return Response(
            {
                "schedule": self.get_serializer(schedule).data,
                "deliveries": ReportDeliverySerializer(deliveries, many=True).data,
            }
        )
