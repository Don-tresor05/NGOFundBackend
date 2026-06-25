import csv
import io
from decimal import Decimal

from rest_framework import serializers

from apps.finance.models import (
    BankAccount,
    BankStatement,
    BankStatementLine,
    CurrencyRate,
    ExpenseApproval,
    PeriodClose,
    PaymentBatch,
    Reconciliation,
    SpendingAlert,
    ScheduledPayment,
    Transaction,
    Vendor,
)


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = "__all__"
        read_only_fields = ["created_at", "processed_by", "base_amount"]

    def validate(self, attrs):
        currency = attrs.get('currency', 'RWF')
        amount = attrs.get('amount')
        
        if currency != 'RWF' and amount:
            rate_obj = CurrencyRate.objects.filter(
                from_currency=currency,
                to_currency='RWF',
                effective_date__lte=attrs.get('transaction_date')
            ).order_by('-effective_date').first()
            
            if rate_obj:
                attrs['exchange_rate'] = rate_obj.rate
                attrs['base_amount'] = amount * rate_obj.rate
            else:
                attrs['base_amount'] = amount
        else:
            attrs['base_amount'] = amount
            attrs['exchange_rate'] = Decimal('1.0')
        
        return attrs


class CurrencyRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CurrencyRate
        fields = "__all__"
        read_only_fields = ["created_at"]


class ExpenseApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseApproval
        fields = "__all__"
        read_only_fields = ["requested_by", "reviewed_by", "reviewed_at", "created_at", "stage"]


class BankAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankAccount
        fields = "__all__"


class VendorSerializer(serializers.ModelSerializer):
    outstanding_amount = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    scheduled_count = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = "__all__"
        read_only_fields = ["created_at"]

    def get_outstanding_amount(self, obj):
        payments = obj.scheduled_payments.exclude(
            status__in=[ScheduledPayment.Status.PAID, ScheduledPayment.Status.CANCELLED]
        )
        return sum(payment.amount for payment in payments)

    def get_paid_amount(self, obj):
        payments = obj.scheduled_payments.filter(status=ScheduledPayment.Status.PAID)
        return sum(payment.amount for payment in payments)

    def get_scheduled_count(self, obj):
        return obj.scheduled_payments.count()


class SpendingAlertSerializer(serializers.ModelSerializer):
    budget_line_name = serializers.CharField(source="budget_line.line_name", read_only=True)

    class Meta:
        model = SpendingAlert
        fields = "__all__"
        read_only_fields = [
            "acknowledged_by",
            "resolved_by",
            "acknowledged_at",
            "resolved_at",
            "created_at",
        ]


class PaymentBatchSerializer(serializers.ModelSerializer):
    scheduled_payment_count = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = PaymentBatch
        fields = "__all__"
        read_only_fields = ["created_by", "processed_by", "processed_at", "created_at"]

    def get_scheduled_payment_count(self, obj):
        return obj.scheduled_payments.count()

    def get_total_amount(self, obj):
        return sum((payment.amount for payment in obj.scheduled_payments.all()), Decimal("0"))


class PeriodCloseSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.CharField(source="bank_account.account_name", read_only=True)

    class Meta:
        model = PeriodClose
        fields = "__all__"
        read_only_fields = [
            "prepared_by",
            "closed_by",
            "prepared_at",
            "closed_at",
            "unmatched_statement_lines",
            "reconciliation_exceptions",
            "created_at",
        ]


class ScheduledPaymentSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    budget_line_name = serializers.CharField(source="budget_line.line_name", read_only=True)
    bank_account_name = serializers.CharField(source="bank_account.account_name", read_only=True)
    batch_name = serializers.SerializerMethodField()

    class Meta:
        model = ScheduledPayment
        fields = "__all__"
        read_only_fields = [
            "scheduled_by",
            "approved_by",
            "paid_by",
            "transaction",
            "batch",
            "approved_at",
            "paid_at",
            "created_at",
        ]

    def validate(self, attrs):
        budget_line = attrs.get("budget_line", getattr(self.instance, "budget_line", None))
        amount = attrs.get("amount", getattr(self.instance, "amount", None))
        if budget_line and amount and self.instance is None and amount > budget_line.remaining_amount:
            raise serializers.ValidationError("Scheduled payment exceeds the budget line remaining balance.")
        return attrs

    def get_batch_name(self, obj):
        return obj.batch.name if obj.batch else None


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
    lines = BankStatementLineImportSerializer(many=True, required=False)

    def validate(self, attrs):
        lines = attrs.get("lines") or []
        statement_file = attrs.get("statement_file")
        if not lines and statement_file is None:
            raise serializers.ValidationError("Provide statement lines or upload a statement file.")

        if not lines and statement_file is not None:
            lines = self._parse_statement_file(statement_file)
            attrs["lines"] = lines

        if not lines:
            raise serializers.ValidationError("The imported statement does not contain any lines.")

        return attrs

    def _parse_statement_file(self, statement_file):
        try:
          raw_content = statement_file.read()
        finally:
            try:
                statement_file.seek(0)
            except Exception:
                pass

        try:
            content = raw_content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise serializers.ValidationError("Statement file must be UTF-8 encoded CSV.") from exc

        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            raise serializers.ValidationError("Statement file is missing a header row.")

        normalized_headers = {field.strip().lower(): field for field in reader.fieldnames if field}
        required_headers = {"transaction_date", "description", "amount"}
        missing_headers = required_headers - set(normalized_headers)
        if missing_headers:
            raise serializers.ValidationError(
                f"Statement file is missing required columns: {', '.join(sorted(missing_headers))}."
            )

        parsed_lines = []
        for row in reader:
            payload = {
                "transaction_date": row.get(normalized_headers["transaction_date"], "").strip(),
                "description": row.get(normalized_headers["description"], "").strip(),
                "reference_number": row.get(normalized_headers.get("reference_number", ""), "").strip()
                if normalized_headers.get("reference_number")
                else "",
                "amount": row.get(normalized_headers["amount"], "").strip(),
            }
            if not any(payload.values()):
                continue
            line_serializer = BankStatementLineImportSerializer(data=payload)
            line_serializer.is_valid(raise_exception=True)
            parsed_lines.append(line_serializer.validated_data)

        if not parsed_lines:
            raise serializers.ValidationError("Statement file did not contain any valid lines.")

        return parsed_lines
