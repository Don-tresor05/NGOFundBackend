from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.reports.models import Report, ReportDelivery, ReportSchedule


def build_report_delivery_body(report: Report, delivery: ReportDelivery) -> str:
    return (
        f"Report type: {report.report_type}\n"
        f"Grant: {report.grant.grant_title}\n"
        f"Generated at: {report.created_at.isoformat()}\n"
        f"Delivery method: {delivery.delivery_method}\n"
    )


def dispatch_report_delivery(delivery: ReportDelivery) -> ReportDelivery:
    report = delivery.report
    subject = f"{report.report_type} - {report.format}"
    body = build_report_delivery_body(report, delivery)
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
    except Exception as exc:  # pragma: no cover - surfaced through API/command
        delivery.status = ReportDelivery.Status.FAILED
        delivery.save(update_fields=["status"])
        raise ValidationError(f"Report delivery failed: {exc}") from exc


def get_next_run_at(schedule: ReportSchedule, base_time):
    if schedule.frequency == ReportSchedule.Frequency.DAILY:
        return base_time + timedelta(days=1)
    if schedule.frequency == ReportSchedule.Frequency.WEEKLY:
        return base_time + timedelta(days=7)
    if schedule.frequency == ReportSchedule.Frequency.MONTHLY:
        return base_time + timedelta(days=30)
    if schedule.frequency == ReportSchedule.Frequency.QUARTERLY:
        return base_time + timedelta(days=90)
    return None


def get_schedule_report(schedule: ReportSchedule) -> Report:
    report_queryset = Report.objects.filter(report_type=schedule.report_type)
    if schedule.grant_id:
        report_queryset = report_queryset.filter(grant=schedule.grant)
    report = report_queryset.order_by("-created_at").first()
    if not report:
        raise ValidationError("No matching report exists to dispatch for this schedule.")
    return report


def get_schedule_recipients(schedule: ReportSchedule) -> list[str]:
    recipients = [email.strip() for email in schedule.recipient_emails.split(",") if email.strip()]
    if not recipients:
        raise ValidationError("This schedule does not have any recipients.")
    if len(set(recipients)) != len(recipients):
        raise ValidationError("Recipient emails must be unique.")
    return recipients


def run_report_schedule(schedule: ReportSchedule, *, triggered_by) -> list[ReportDelivery]:
    if not schedule.is_active:
        raise ValidationError("Inactive report schedules cannot be run.")

    report = get_schedule_report(schedule)
    recipients = get_schedule_recipients(schedule)
    now = timezone.now()
    deliveries: list[ReportDelivery] = []
    with transaction.atomic():
        for recipient in recipients:
            delivery = ReportDelivery.objects.create(
                report=report,
                created_by=triggered_by,
                delivery_method=schedule.delivery_method,
                destination=recipient,
            )
            dispatch_report_delivery(delivery)
            deliveries.append(delivery)
        schedule.last_run_at = now
        schedule.next_run_at = get_next_run_at(schedule, now)
        schedule.save(update_fields=["last_run_at", "next_run_at"])
    return deliveries


def run_due_report_schedules(*, triggered_by=None, now=None) -> list[dict[str, Any]]:
    current_time = now or timezone.now()
    schedules = (
        ReportSchedule.objects.select_related("grant", "created_by")
        .filter(is_active=True)
        .filter(Q(next_run_at__lte=current_time) | (Q(next_run_at__isnull=True) & ~Q(frequency=ReportSchedule.Frequency.CUSTOM)))
        .order_by("next_run_at", "created_at")
    )
    results: list[dict[str, Any]] = []
    for schedule in schedules:
        actor = triggered_by or schedule.created_by
        try:
            deliveries = run_report_schedule(schedule, triggered_by=actor)
        except ValidationError as exc:
            results.append(
                {
                    "schedule_id": schedule.id,
                    "report_type": schedule.report_type,
                    "deliveries": [],
                    "error": str(exc),
                }
            )
        else:
            results.append(
                {
                    "schedule_id": schedule.id,
                    "report_type": schedule.report_type,
                    "deliveries": deliveries,
                    "error": None,
                }
            )
    return results
