from django.db import models


class Requisition(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    submitted_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="requisitions")
    budget_line = models.ForeignKey("projects.BudgetLine", on_delete=models.PROTECT, related_name="requisitions")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.TextField()
    receipt_document = models.FileField(upload_to="receipts/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "requisitions"

    def __str__(self) -> str:
        return f"Requisition #{self.pk} - {self.amount}"


class RequisitionItem(models.Model):
    requisition = models.ForeignKey("requisitions.Requisition", on_delete=models.CASCADE, related_name="items")
    item_name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=2, default=1)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2, editable=False)

    class Meta:
        ordering = ["requisition", "id"]
        db_table = "requisition_items"

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_cost
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.item_name} ({self.line_total})"
