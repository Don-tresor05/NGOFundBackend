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
            f"<tr><td style='padding:7px 14px;color:#6b7280;border-bottom:1px solid #fef3c7;font-size:13px'>{label}</td>"
            f"<td style='padding:7px 14px;font-weight:600;text-align:right;border-bottom:1px solid #fef3c7;color:#0f2942;font-size:13px'>{_fmt(v)}</td></tr>"
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
            f"<h3 style='margin:24px 0 8px;font-size:13px;font-weight:700;color:#0f2942;text-transform:uppercase;letter-spacing:0.5px;border-left:3px solid #f59e0b;padding-left:10px'>{title}</h3>"
            f"<table width='100%' cellpadding='0' cellspacing='0' style='background:#fffbf0;border-radius:8px;border:1px solid #fef3c7;overflow:hidden'>{_section_rows(data)}</table>"
        )

    budget_lines = snap.get("budget_lines", [])
    if budget_lines:
        rows = "".join(
            f"<tr><td style='padding:7px 14px;border-bottom:1px solid #fef3c7;font-size:13px'>{bl.get('line_name','')}</td>"
            f"<td style='padding:7px 14px;text-align:right;border-bottom:1px solid #fef3c7;font-size:13px'>{_fmt(bl.get('allocated_amount'))}</td>"
            f"<td style='padding:7px 14px;text-align:right;border-bottom:1px solid #fef3c7;font-size:13px'>{_fmt(bl.get('spent_amount'))}</td>"
            f"<td style='padding:7px 14px;text-align:right;border-bottom:1px solid #fef3c7;font-size:13px;color:{'#dc2626' if float(bl.get('remaining_amount',0) or 0) < 0 else '#059669'}'>{_fmt(bl.get('remaining_amount'))}</td></tr>"
            for bl in budget_lines
        )
        sections_html += (
            "<h3 style='margin:24px 0 8px;font-size:13px;font-weight:700;color:#0f2942;text-transform:uppercase;letter-spacing:0.5px;border-left:3px solid #f59e0b;padding-left:10px'>Budget Lines</h3>"
            "<table width='100%' cellpadding='0' cellspacing='0' style='background:#fffbf0;border-radius:8px;border:1px solid #fef3c7;overflow:hidden'>"
            "<tr style='background:linear-gradient(90deg,#0f2942,#1a4068);color:#ffffff;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:0.4px'>"
            "<td style='padding:9px 14px'>Line</td><td style='padding:9px 14px;text-align:right'>Allocated</td>"
            "<td style='padding:9px 14px;text-align:right'>Spent</td><td style='padding:9px 14px;text-align:right'>Remaining</td></tr>"
            f"{rows}</table>"
        )

    return (
        "<!DOCTYPE html><html><body style='margin:0;padding:0;background:#f7f3e8;font-family:Inter,Arial,sans-serif'>"
        "<table width='100%' cellpadding='0' cellspacing='0' style='background:#f7f3e8;padding:36px 0'><tr><td align='center'>"
        "<table width='620' cellpadding='0' cellspacing='0' style='background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(148,118,39,0.13);border:1px solid #f0e6c8'>"

        # Header
        "<tr><td style='background:linear-gradient(135deg,#0f2942 0%,#1a4068 60%,#1f6f78 100%);padding:32px 36px'>"
        "<table width='100%' cellpadding='0' cellspacing='0'><tr>"
        "<td><div style='width:40px;height:40px;background:rgba(255,200,87,0.2);border-radius:10px;display:inline-block;text-align:center;line-height:40px;font-size:20px;margin-bottom:12px'>📊</div>"
        f"<h1 style='margin:0;color:#ffffff;font-size:22px;font-weight:700;letter-spacing:-0.3px'>{report.report_type}</h1>"
        f"<p style='margin:6px 0 0;color:#93c5fd;font-size:13px'>{grant.grant_title} &nbsp;·&nbsp; "
        f"<span style='background:rgba(255,200,87,0.25);color:#fcd34d;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600'>{report.format}</span>"
        f" &nbsp;·&nbsp; {report.created_at.strftime('%d %b %Y')}</p></td>"
        "</tr></table></td></tr>"

        # Gold divider
        "<tr><td style='height:4px;background:linear-gradient(90deg,#f59e0b,#fcd34d,#1f6f78)'></td></tr>"

        # Body
        f"<tr><td style='padding:28px 36px 36px'>{sections_html}"

        # Footer
        "<tr><td style='padding:0 36px 28px'>"
        "<table width='100%' cellpadding='0' cellspacing='0' style='border-top:1px solid #f0e6c8;padding-top:20px;margin-top:8px'><tr>"
        "<td style='font-size:12px;color:#9ca3af'>"
        "Generated by <strong style='color:#0f2942'>NGO Fund Platform</strong> &nbsp;·&nbsp; Rwanda Paediatric Association<br>"
        f"<span style='color:#b45309'>Delivered to: {delivery.destination}</span>"
        "</td>"
        "<td align='right'><div style='width:32px;height:32px;background:linear-gradient(135deg,#0f2942,#1f6f78);border-radius:8px;display:inline-block'></div></td>"
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
