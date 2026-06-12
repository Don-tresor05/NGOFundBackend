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


class Transaction(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CLEARED = "cleared", "Cleared"
        RECONCILED = "reconciled", "Reconciled"

    requisition = models.ForeignKey("requisitions.Requisition", on_delete=models.PROTECT, related_name="transactions")
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
