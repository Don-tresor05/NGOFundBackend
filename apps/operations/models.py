from django.db import models


class StaffRequirement(models.Model):
    class ValidationStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_REVIEW = "in_review", "In Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    captured_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="captured_requirements")
    interviewee_name = models.CharField(max_length=150)
    process_area = models.CharField(max_length=150)
    feedback = models.TextField(blank=True)
    validation_status = models.CharField(
        max_length=30,
        choices=ValidationStatus.choices,
        default=ValidationStatus.PENDING,
    )
    signed_off_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signed_off_requirements",
    )
    signed_off_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.process_area} - {self.interviewee_name}"
