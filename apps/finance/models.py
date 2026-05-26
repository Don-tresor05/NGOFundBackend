from django.db import models


class Transaction(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CLEARED = "cleared", "Cleared"
        RECONCILED = "reconciled", "Reconciled"

    requisition = models.ForeignKey("requisitions.Requisition", on_delete=models.PROTECT, related_name="transactions")
    budget_line = models.ForeignKey("projects.BudgetLine", on_delete=models.PROTECT, related_name="transactions")
    processed_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="processed_transactions")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    transaction_date = models.DateField()
    bank_reference_number = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-transaction_date", "-created_at"]

    def __str__(self) -> str:
        return self.bank_reference_number
