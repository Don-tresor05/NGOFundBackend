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
        db_table = "projects"

    def __str__(self) -> str:
        return self.name


class BudgetLine(models.Model):
    grant = models.ForeignKey("grants.Grant", on_delete=models.PROTECT, related_name="budget_lines")
    line_name = models.CharField(max_length=180)
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2)
    spent_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        ordering = ["line_name"]
        db_table = "budget_lines"

    def __str__(self) -> str:
        return self.line_name

    @property
    def remaining_amount(self):
        return self.allocated_amount - self.spent_amount


class ReallocationRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    source_budget_line = models.ForeignKey(
        "projects.BudgetLine",
        on_delete=models.PROTECT,
        related_name="reallocation_sources",
    )
    target_budget_line = models.ForeignKey(
        "projects.BudgetLine",
        on_delete=models.PROTECT,
        related_name="reallocation_targets",
    )
    requested_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="reallocation_requests")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_reallocation_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "reallocation_requests"

    def __str__(self) -> str:
        return f"Reallocation #{self.pk} - {self.amount}"


class ProjectMember(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="project_memberships")
    member_role = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-assigned_at"]
        db_table = "project_members"
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="unique_project_member")
        ]

    def __str__(self) -> str:
        return f"{self.user.full_name} on {self.project.name}"
