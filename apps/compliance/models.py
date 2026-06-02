from django.db import models


class ComplianceItem(models.Model):
    title = models.CharField(max_length=180)
    owner = models.CharField(max_length=120)
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_compliance_items",
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["title"]
        db_table = "compliance_items"

    def __str__(self) -> str:
        return self.title
