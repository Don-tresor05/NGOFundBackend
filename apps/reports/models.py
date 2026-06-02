from django.db import models


class Report(models.Model):
    class Format(models.TextChoices):
        PDF = "PDF", "PDF"
        EXCEL = "Excel", "Excel"
        CSV = "CSV", "CSV"

    grant = models.ForeignKey("grants.Grant", on_delete=models.PROTECT, related_name="reports")
    generated_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="reports")
    report_type = models.CharField(max_length=100)
    file = models.FileField(upload_to="reports/", null=True, blank=True)
    format = models.CharField(max_length=20, choices=Format.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "reports"

    def __str__(self) -> str:
        return f"{self.report_type} ({self.format})"


class ReportSchedule(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"
        CUSTOM = "custom", "Custom"

    class DeliveryMethod(models.TextChoices):
        EMAIL = "email", "Email"
        DOWNLOAD = "download", "Download"
        ARCHIVE = "archive", "Archive"

    report_type = models.CharField(max_length=100)
    grant = models.ForeignKey("grants.Grant", on_delete=models.PROTECT, null=True, blank=True, related_name="report_schedules")
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="report_schedules")
    frequency = models.CharField(max_length=20, choices=Frequency.choices)
    delivery_method = models.CharField(max_length=20, choices=DeliveryMethod.choices, default=DeliveryMethod.EMAIL)
    recipient_emails = models.TextField(help_text="Comma-separated recipient emails")
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "report_schedules"

    def __str__(self) -> str:
        return f"{self.report_type} schedule ({self.frequency})"


class ReportDelivery(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    report = models.ForeignKey("reports.Report", on_delete=models.CASCADE, related_name="deliveries")
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="report_deliveries")
    delivery_method = models.CharField(max_length=20, default="email")
    destination = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "report_deliveries"

    def __str__(self) -> str:
        return f"{self.report.report_type} to {self.destination}"
