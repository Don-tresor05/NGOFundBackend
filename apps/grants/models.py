from django.db import models


class Grant(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING = "pending", "Pending"
        CLOSED = "closed", "Closed"

    donor = models.ForeignKey("donors.Donor", on_delete=models.PROTECT, related_name="grants")
    grant_title = models.CharField(max_length=200)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    compliance_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date", "grant_title"]

    def __str__(self) -> str:
        return self.grant_title
