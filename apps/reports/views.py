from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.reports.models import Report, ReportDelivery, ReportSchedule
from apps.reports.serializers import ReportDeliverySerializer, ReportScheduleSerializer, ReportSerializer


def _dispatch_report_delivery(delivery: ReportDelivery):
    report = delivery.report
    subject = f"{report.report_type} - {report.format}"
    body = (
        f"Report type: {report.report_type}\n"
        f"Grant: {report.grant.grant_title}\n"
        f"Generated at: {report.created_at.isoformat()}\n"
        f"Delivery method: {delivery.delivery_method}\n"
    )
    try:
        if delivery.delivery_method == ReportSchedule.DeliveryMethod.EMAIL:
            email = EmailMessage(
                subject=subject,
                body=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@ngofund.local"),
                to=[delivery.destination],
            )
            if report.file:
                try:
                    email.attach_file(report.file.path)
                except (ValueError, FileNotFoundError, OSError):
                    pass
            email.send(fail_silently=False)
        delivery.status = ReportDelivery.Status.SENT
        delivery.sent_at = timezone.now()
        delivery.save(update_fields=["status", "sent_at"])
        return delivery
    except Exception as exc:  # pragma: no cover - surfaced through API
        delivery.status = ReportDelivery.Status.FAILED
        delivery.save(update_fields=["status"])
        raise ValidationError(f"Report delivery failed: {exc}")


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
        _dispatch_report_delivery(delivery)
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
        _dispatch_report_delivery(delivery)
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

    def _next_run_at(self, schedule, base_time):
        if schedule.frequency == ReportSchedule.Frequency.DAILY:
            return base_time + timedelta(days=1)
        if schedule.frequency == ReportSchedule.Frequency.WEEKLY:
            return base_time + timedelta(days=7)
        if schedule.frequency == ReportSchedule.Frequency.MONTHLY:
            return base_time + timedelta(days=30)
        if schedule.frequency == ReportSchedule.Frequency.QUARTERLY:
            return base_time + timedelta(days=90)
        return None

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
        if not schedule.is_active:
            raise ValidationError("Inactive report schedules cannot be run.")

        report_queryset = Report.objects.filter(report_type=schedule.report_type)
        if schedule.grant_id:
            report_queryset = report_queryset.filter(grant=schedule.grant)
        report = report_queryset.order_by("-created_at").first()
        if not report:
            raise ValidationError("No matching report exists to dispatch for this schedule.")

        recipients = [email.strip() for email in schedule.recipient_emails.split(",") if email.strip()]
        if not recipients:
            raise ValidationError("This schedule does not have any recipients.")

        now = timezone.now()
        with db_transaction.atomic():
            deliveries = [
                _dispatch_report_delivery(
                    ReportDelivery.objects.create(
                        report=report,
                        created_by=request.user,
                        delivery_method=schedule.delivery_method,
                        destination=recipient,
                    )
                )
                for recipient in recipients
            ]
            schedule.last_run_at = now
            schedule.next_run_at = self._next_run_at(schedule, now)
            schedule.save(update_fields=["last_run_at", "next_run_at"])
        self._write_audit_log("REPORT_SCHEDULE_RUN", schedule)
        return Response(
            {
                "schedule": self.get_serializer(schedule).data,
                "deliveries": ReportDeliverySerializer(deliveries, many=True).data,
            }
        )
