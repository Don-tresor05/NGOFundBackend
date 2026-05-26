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

    def __str__(self) -> str:
        return f"{self.report_type} ({self.format})"
