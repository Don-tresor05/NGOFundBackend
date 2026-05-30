from django.db import models


class TestCase(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "Todo"
        IN_PROGRESS = "in_progress", "In Progress"
        IN_REVIEW = "in_review", "In Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="test_cases")
    title = models.CharField(max_length=180)
    scenario = models.TextField()
    environment = models.CharField(max_length=80)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.TODO)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class UATFeedback(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_REVIEW = "in_review", "In Review"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"

    test_case = models.ForeignKey("testing_validation.TestCase", on_delete=models.CASCADE, related_name="uat_feedback")
    submitted_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="uat_feedback")
    feedback = models.TextField()
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Feedback for {self.test_case_id}"
