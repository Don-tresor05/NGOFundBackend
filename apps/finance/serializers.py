import csv
import io

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
