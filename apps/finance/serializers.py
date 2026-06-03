from rest_framework import serializers

from apps.finance.models import BankAccount, BankStatement, BankStatementLine, ExpenseApproval, Reconciliation, Transaction


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = "__all__"
        read_only_fields = ["created_at", "processed_by"]


class ExpenseApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseApproval
        fields = "__all__"
        read_only_fields = ["requested_by", "reviewed_by", "reviewed_at", "created_at", "stage"]


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = "__all__"


class BankStatementSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankStatement
        fields = "__all__"
        read_only_fields = ["imported_by", "created_at"]


class BankStatementLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankStatementLine
        fields = "__all__"


class ReconciliationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reconciliation
        fields = "__all__"
        read_only_fields = ["reviewed_by", "created_at", "matched_at"]

    def validate(self, attrs):
        transaction = attrs.get("transaction", getattr(self.instance, "transaction", None))
        bank_statement_line = attrs.get("bank_statement_line", getattr(self.instance, "bank_statement_line", None))
        status = attrs.get("status", getattr(self.instance, "status", Reconciliation.Status.UNMATCHED))
        difference_amount = attrs.get(
            "difference_amount",
            getattr(self.instance, "difference_amount", 0),
        )

        if transaction and bank_statement_line and transaction.bank_account_id:
            if bank_statement_line.bank_statement.bank_account_id != transaction.bank_account_id:
                raise serializers.ValidationError("Reconciliations must use a bank statement line from the same bank account.")

        if status == Reconciliation.Status.MATCHED and difference_amount != 0:
            raise serializers.ValidationError("Matched reconciliations must have zero difference.")

        return attrs


class BankStatementLineImportSerializer(serializers.Serializer):
    transaction_date = serializers.DateField()
    description = serializers.CharField()
    reference_number = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class BankStatementImportSerializer(serializers.Serializer):
    statement_number = serializers.CharField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    opening_balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    closing_balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    statement_file = serializers.FileField(required=False, allow_null=True)
    lines = BankStatementLineImportSerializer(many=True)
