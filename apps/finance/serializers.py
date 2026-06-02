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
