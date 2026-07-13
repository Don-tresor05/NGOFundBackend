from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.reports.models import Report, ReportDelivery, ReportSchedule


def _fmt(value) -> str:
    if value is None or value == "":
        return "—"
    try:
        f = float(value)
        return f"{f:,.2f}" if f != int(f) else f"{int(f):,}"
    except (TypeError, ValueError):
        return str(value)


def _section_rows(data: dict) -> str:
    rows = ""
    for k, v in data.items():
        label = k.replace("_", " ").title()
        rows += (
            f"<tr><td style='padding:7px 14px;color:#6b7280;border-bottom:1px solid #eef0f3;font-size:13px'>{label}</td>"
            f"<td style='padding:7px 14px;font-weight:600;text-align:right;border-bottom:1px solid #eef0f3;color:#0f2942;font-size:13px'>{_fmt(v)}</td></tr>"
        )
    return rows


def build_report_delivery_body(report: Report, delivery: ReportDelivery) -> str:
    snap = (report.custom_fields or {}).get("snapshot", {})
    grant = report.grant

    sections_html = ""
    for title, data in [
        ("Financial Summary", snap.get("financial_summary")),
        ("Donor Funding", snap.get("donor_funding")),
        ("Project Utilization", snap.get("project_utilization")),
        ("Reconciliation", snap.get("reconciliation_report")),
        ("Audit & Compliance", snap.get("audit_compliance_report")),
    ]:
        if not data:
            continue
        sections_html += (
            f"<h3 style='margin:20px 0 6px;font-size:11px;font-weight:700;color:#1a4068;text-transform:uppercase;letter-spacing:0.6px'>{title}</h3>"
            f"<table width='100%' cellpadding='0' cellspacing='0' style='background:#f8f9fb;border-radius:6px;border:1px solid #e4e8ee;overflow:hidden'>{_section_rows(data)}</table>"
        )

    budget_lines = snap.get("budget_lines", [])
    if budget_lines:
        rows = "".join(
            f"<tr><td style='padding:7px 14px;border-bottom:1px solid #eef0f3;font-size:13px'>{bl.get('line_name','')}</td>"
            f"<td style='padding:7px 14px;text-align:right;border-bottom:1px solid #eef0f3;font-size:13px'>{_fmt(bl.get('allocated_amount'))}</td>"
            f"<td style='padding:7px 14px;text-align:right;border-bottom:1px solid #eef0f3;font-size:13px'>{_fmt(bl.get('spent_amount'))}</td>"
            f"<td style='padding:7px 14px;text-align:right;border-bottom:1px solid #eef0f3;font-size:13px;color:{'#c0392b' if float(bl.get('remaining_amount',0) or 0) < 0 else '#1a6b3c'}'>{_fmt(bl.get('remaining_amount'))}</td></tr>"
            for bl in budget_lines
        )
        sections_html += (
            "<h3 style='margin:20px 0 6px;font-size:11px;font-weight:700;color:#1a4068;text-transform:uppercase;letter-spacing:0.6px'>Budget Lines</h3>"
            "<table width='100%' cellpadding='0' cellspacing='0' style='background:#f8f9fb;border-radius:6px;border:1px solid #e4e8ee;overflow:hidden'>"
            "<tr style='background:#1a4068;color:#ffffff;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.4px'>"
            "<td style='padding:8px 14px'>Line</td><td style='padding:8px 14px;text-align:right'>Allocated</td>"
            "<td style='padding:8px 14px;text-align:right'>Spent</td><td style='padding:8px 14px;text-align:right'>Remaining</td></tr>"
            f"{rows}</table>"
        )

    return (
        "<!DOCTYPE html><html><body style='margin:0;padding:0;background:#f4f6f9;font-family:Arial,sans-serif'>"
        "<table width='100%' cellpadding='0' cellspacing='0' style='background:#f4f6f9;padding:36px 0'><tr><td align='center'>"
        "<table width='620' cellpadding='0' cellspacing='0' style='background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.10);border:1px solid #dde2ea'>"

        # Header
        "<tr><td style='background:#0f2942;padding:28px 32px'>"
        f"<h1 style='margin:0;color:#ffffff;font-size:20px;font-weight:700'>{report.report_type}</h1>"
        f"<p style='margin:6px 0 0;color:#93c5fd;font-size:13px'>{grant.grant_title} &nbsp;·&nbsp; {report.format} &nbsp;·&nbsp; {report.created_at.strftime('%d %b %Y')}</p>"
        "</td></tr>"

        # Navy top-border accent
        "<tr><td style='height:3px;background:#1a4068'></td></tr>"

        # Body
        f"<tr><td style='padding:28px 32px 32px'>{sections_html}"

        # Footer
        "<tr><td style='padding:0 32px 24px'>"
        "<table width='100%' cellpadding='0' cellspacing='0' style='border-top:1px solid #e4e8ee;padding-top:16px'><tr>"
        "<td style='font-size:12px;color:#9ca3af'>"
        "NGO Fund Platform &nbsp;·&nbsp; Rwanda Paediatric Association<br>"
        f"Delivered to: {delivery.destination}"
        "</td>"
        "</tr></table></td></tr>"

        "</table></td></tr></table></body></html>"
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
            email.content_subtype = "html"
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
