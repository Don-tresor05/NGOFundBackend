from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
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
