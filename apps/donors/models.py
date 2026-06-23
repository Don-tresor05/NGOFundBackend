from django.db import models


class Donor(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    organization_name = models.CharField(max_length=150)
    contact_person = models.CharField(max_length=150)
    contact_email = models.EmailField()
    country = models.CharField(max_length=100)
    category = models.CharField(max_length=80)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["organization_name"]
        db_table = "donors"

    def __str__(self) -> str:
        return self.organization_name


class DonorCommunication(models.Model):
    class CommunicationType(models.TextChoices):
        GENERAL = "general", "General"
        ACKNOWLEDGMENT = "acknowledgment", "Acknowledgment"
        UPDATE = "update", "Update"
        NEWSLETTER = "newsletter", "Newsletter"

    class Status(models.TextChoices):
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        BOUNCED = "bounced", "Bounced"

    donor = models.ForeignKey("donors.Donor", on_delete=models.CASCADE, related_name="communications")
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="donor_communications", null=True, blank=True)
    channel = models.CharField(max_length=50)
    subject = models.CharField(max_length=180)
    message = models.TextField()
    communication_date = models.DateTimeField()
    communication_type = models.CharField(max_length=50, choices=CommunicationType.choices, default=CommunicationType.GENERAL)
    reference = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.SENT)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-communication_date"]
        db_table = "donor_communications"

    def __str__(self) -> str:
        return f"{self.channel}: {self.subject}"
