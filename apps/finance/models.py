from django.db import models


class CurrencyRate(models.Model):
    from_currency = models.CharField(max_length=3)
    to_currency = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=12, decimal_places=6)
    effective_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date"]
        db_table = "currency_rates"
        constraints = [
            models.UniqueConstraint(
                fields=["from_currency", "to_currency", "effective_date"],
                name="unique_currency_rate_per_date"
            )
        ]

    def __str__(self) -> str:
        return f"{self.from_currency}/{self.to_currency}: {self.rate}"


class BankAccount(models.Model):
    account_name = models.CharField(max_length=180)
    bank_name = models.CharField(max_length=180)
    account_number = models.CharField(max_length=100, unique=True)
    currency = models.CharField(max_length=10)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["bank_name", "account_name"]
        db_table = "bank_accounts"

    def __str__(self) -> str:
        return f"{self.bank_name} - {self.account_name}"


class Vendor(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    name = models.CharField(max_length=180)
    contact_person = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    category = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        db_table = "vendors"

    def __str__(self) -> str:
        return self.name


class SpendingAlert(models.Model):
    class Severity(models.TextChoices):
        WATCH = "watch", "Watch"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        RESOLVED = "resolved", "Resolved"

    budget_line = models.ForeignKey("projects.BudgetLine", on_delete=models.CASCADE, related_name="spending_alerts")
    threshold_percent = models.DecimalField(max_digits=5, decimal_places=2)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.WARNING)
    message = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    acknowledged_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_spending_alerts",
    )
    resolved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_spending_alerts",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "spending_alerts"

    def __str__(self) -> str:
        return f"{self.budget_line.line_name} - {self.severity}"


class PaymentBatch(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        READY = "ready", "Ready"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    name = models.CharField(max_length=180)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    scheduled_for = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="payment_batches")
    processed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_payment_batches",
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "payment_batches"

    def __str__(self) -> str:
        return self.name


class PeriodClose(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PREPARED = "prepared", "Prepared"
        CLOSED = "closed", "Closed"

    bank_account = models.ForeignKey(
        "finance.BankAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="period_closures",
    )
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    prepared_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prepared_period_closures",
    )
    closed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_period_closures",
    )
    prepared_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    unmatched_statement_lines = models.PositiveIntegerField(default=0)
    reconciliation_exceptions = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_end", "-created_at"]
        db_table = "period_closures"

    def __str__(self) -> str:
        scope = self.bank_account.account_name if self.bank_account else "All accounts"
        return f"{scope} {self.period_start} to {self.period_end}"


class Transaction(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CLEARED = "cleared", "Cleared"
        RECONCILED = "reconciled", "Reconciled"

    donor = models.ForeignKey("donors.Donor", on_delete=models.SET_NULL, null=True, blank=True, related_name="transactions")
    requisition = models.ForeignKey("requisitions.Requisition", on_delete=models.PROTECT, related_name="transactions", null=True, blank=True)
    budget_line = models.ForeignKey("projects.BudgetLine", on_delete=models.PROTECT, related_name="transactions")
    bank_account = models.ForeignKey(
        "finance.BankAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    processed_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="processed_transactions")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="RWF")
    base_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    transaction_date = models.DateField()
    bank_reference_number = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-transaction_date", "-created_at"]
        db_table = "transactions"

    def __str__(self) -> str:
        return self.bank_reference_number


class ScheduledPayment(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    vendor = models.ForeignKey("finance.Vendor", on_delete=models.PROTECT, related_name="scheduled_payments")
    requisition = models.ForeignKey(
        "requisitions.Requisition",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_payments",
    )
    budget_line = models.ForeignKey("projects.BudgetLine", on_delete=models.PROTECT, related_name="scheduled_payments")
    batch = models.ForeignKey(
        "finance.PaymentBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_payments",
    )
    bank_account = models.ForeignKey(
        "finance.BankAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_payments",
    )
    scheduled_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="scheduled_payments")
    approved_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_scheduled_payments",
    )
    paid_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paid_scheduled_payments",
    )
    transaction = models.ForeignKey(
        "finance.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_payments",
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="RWF")
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED)
    notes = models.TextField(blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "-created_at"]
        db_table = "scheduled_payments"

    def __str__(self) -> str:
        return f"{self.vendor.name} - {self.amount} due {self.due_date}"


class ExpenseApproval(models.Model):
    class Stage(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        DEPARTMENT_REVIEW = "department_review", "Department Review"
        FINANCE_REVIEW = "finance_review", "Finance Review"
        EXECUTIVE_REVIEW = "executive_review", "Executive Review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    requisition = models.ForeignKey(
        "requisitions.Requisition",
        on_delete=models.CASCADE,
        related_name="expense_approvals",
    )
    requested_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="expense_approval_requests")
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_expense_approvals",
    )
    stage = models.CharField(max_length=40, choices=Stage.choices, default=Stage.SUBMITTED)
    notes = models.TextField(blank=True)
    decision_reason = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "expense_approvals"

    def __str__(self) -> str:
        return f"Expense approval #{self.pk} - {self.stage}"


class BankStatement(models.Model):
    bank_account = models.ForeignKey("finance.BankAccount", on_delete=models.PROTECT, related_name="statements")
    statement_number = models.CharField(max_length=100)
    period_start = models.DateField()
    period_end = models.DateField()
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=14, decimal_places=2)
    imported_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="bank_statements")
    statement_file = models.FileField(upload_to="bank-statements/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "bank_statements"
        constraints = [
            models.UniqueConstraint(fields=["bank_account", "statement_number"], name="unique_bank_statement")
        ]

    def __str__(self) -> str:
        return f"{self.bank_account.account_name} #{self.statement_number}"


class BankStatementLine(models.Model):
    bank_statement = models.ForeignKey("finance.BankStatement", on_delete=models.CASCADE, related_name="lines")
    transaction_date = models.DateField()
    description = models.TextField()
    reference_number = models.CharField(max_length=120, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    matched = models.BooleanField(default=False)

    class Meta:
        ordering = ["-transaction_date", "id"]
        db_table = "bank_statement_lines"

    def __str__(self) -> str:
        return self.reference_number or self.description[:40]


class Reconciliation(models.Model):
    class Status(models.TextChoices):
        MATCHED = "matched", "Matched"
        UNMATCHED = "unmatched", "Unmatched"
        EXCEPTION = "exception", "Exception"

    transaction = models.ForeignKey("finance.Transaction", on_delete=models.CASCADE, related_name="reconciliations")
    bank_statement_line = models.ForeignKey(
        "finance.BankStatementLine",
        on_delete=models.CASCADE,
        related_name="reconciliations",
    )
    reviewed_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="reconciliations")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNMATCHED)
    difference_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    matched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "reconciliations"
        constraints = [
            models.UniqueConstraint(
                fields=["transaction", "bank_statement_line"],
                name="unique_transaction_statement_line_reconciliation",
            )
        ]

    def __str__(self) -> str:
        return f"Reconciliation #{self.pk} - {self.status}"
