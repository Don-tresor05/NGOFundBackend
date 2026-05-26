from django.db import models


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"

    grant = models.ForeignKey("grants.Grant", on_delete=models.PROTECT, related_name="projects")
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class BudgetLine(models.Model):
    grant = models.ForeignKey("grants.Grant", on_delete=models.PROTECT, related_name="budget_lines")
    line_name = models.CharField(max_length=180)
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2)
    spent_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["line_name"]

    def __str__(self) -> str:
        return self.line_name

    @property
    def remaining_amount(self):
        return self.allocated_amount - self.spent_amount
