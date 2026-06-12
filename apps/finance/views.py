from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.finance.models import (
    BankAccount,
    BankStatement,
    BankStatementLine,
    CurrencyRate,
    ExpenseApproval,
    Reconciliation,
    Transaction,
)
from apps.finance.serializers import (
    BankAccountSerializer,
    BankStatementImportSerializer,
    BankStatementLineSerializer,
    BankStatementSerializer,
    CurrencyRateSerializer,
    ExpenseApprovalSerializer,
    ReconciliationSerializer,
    TransactionSerializer,
)
from apps.requisitions.models import Requisition


class CurrencyRateViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = CurrencyRate.objects.all()
    serializer_class = CurrencyRateSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.SUPER_ADMIN]
    required_permissions = ["manage_finance"]
    filterset_fields = ["from_currency", "to_currency", "effective_date"]
    ordering_fields = ["effective_date", "from_currency", "to_currency"]

    @action(detail=False, methods=["get"], url_path="convert")
    def convert(self, request):
        from_currency = request.query_params.get('from')
        to_currency = request.query_params.get('to', 'RWF')
        amount = request.query_params.get('amount', '0')
        date = request.query_params.get('date', timezone.now().date())
        
        try:
            amount = float(amount)
        except ValueError:
            return Response({"error": "Invalid amount"}, status=400)
        
        if from_currency == to_currency:
            return Response({"converted_amount": amount, "rate": 1.0, "from_currency": from_currency, "to_currency": to_currency})
        
        rate_obj = CurrencyRate.objects.filter(
            from_currency=from_currency,
            to_currency=to_currency,
            effective_date__lte=date
        ).order_by('-effective_date').first()
        
        if not rate_obj:
            return Response({"error": f"No exchange rate found for {from_currency}/{to_currency}"}, status=404)
        
        converted = amount * float(rate_obj.rate)
        return Response({
            "converted_amount": round(converted, 2),
            "rate": float(rate_obj.rate),
            "from_currency": from_currency,
            "to_currency": to_currency,
            "effective_date": rate_obj.effective_date
        })


class TransactionViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Transaction.objects.select_related("requisition", "budget_line", "processed_by")
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR, Role.DONOR_USER]
    required_permissions = ["manage_finance"]
    action_roles = {
        "reconcile": [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
    }
    filterset_fields = ["budget_line", "processed_by", "status", "transaction_date"]
    search_fields = ["bank_reference_number", "budget_line__line_name"]
    ordering_fields = ["transaction_date", "amount", "status", "created_at"]

    def perform_create(self, serializer):
        with db_transaction.atomic():
            instance = serializer.save(processed_by=self.request.user)
            budget_line = instance.budget_line
            budget_line.spent_amount += instance.amount
            budget_line.save(update_fields=["spent_amount"])
            self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="reconcile")
    def reconcile(self, request, pk=None):
        instance = self.get_object()
        if instance.status == Transaction.Status.RECONCILED:
            return Response(self.get_serializer(instance).data)
        instance.status = Transaction.Status.RECONCILED
        if request.data.get("bank_reference_number"):
            instance.bank_reference_number = request.data["bank_reference_number"]
        instance.save(update_fields=["status", "bank_reference_number"])
        self._write_audit_log("TRANSACTION_RECONCILED", instance)
        return Response(self.get_serializer(instance).data)


class ExpenseApprovalViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ExpenseApproval.objects.select_related("requisition", "requested_by", "reviewed_by")
    serializer_class = ExpenseApprovalSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FIELD_STAFF, Role.PROJECT_MANAGER, Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_finance", "manage_projects"]
    action_roles = {
        "department_review": [Role.FIELD_STAFF, Role.PROJECT_MANAGER],
        "finance_review": [Role.FINANCE_OFFICER],
        "executive_review": [Role.EXECUTIVE_DIRECTOR],
        "approve": [Role.EXECUTIVE_DIRECTOR],
        "reject": [Role.FIELD_STAFF, Role.PROJECT_MANAGER, Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
    }
    filterset_fields = ["requisition", "requested_by", "reviewed_by", "stage"]
    search_fields = ["notes", "decision_reason", "requisition__description"]
    ordering_fields = ["created_at", "reviewed_at", "stage"]

    def perform_create(self, serializer):
        instance = serializer.save(requested_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    def _advance_stage(self, request, stage, action_name, expected_current_stages):
        approval = self.get_object()
        if approval.stage not in expected_current_stages:
            raise ValidationError("Invalid expense approval stage transition.")
        approval.stage = stage
        approval.reviewed_by = request.user
        approval.reviewed_at = timezone.now()
        approval.notes = request.data.get("notes", approval.notes)
        approval.decision_reason = request.data.get("decision_reason", approval.decision_reason)
        approval.save(update_fields=["stage", "reviewed_by", "reviewed_at", "notes", "decision_reason"])
        self._write_audit_log(action_name, approval)
        return Response(self.get_serializer(approval).data)

    @action(detail=True, methods=["post"], url_path="department-review")
    def department_review(self, request, pk=None):
        return self._advance_stage(
            request,
            ExpenseApproval.Stage.DEPARTMENT_REVIEW,
            "EXPENSE_DEPARTMENT_REVIEW",
            {ExpenseApproval.Stage.SUBMITTED},
        )

    @action(detail=True, methods=["post"], url_path="finance-review")
    def finance_review(self, request, pk=None):
        return self._advance_stage(
            request,
            ExpenseApproval.Stage.FINANCE_REVIEW,
            "EXPENSE_FINANCE_REVIEW",
            {ExpenseApproval.Stage.DEPARTMENT_REVIEW},
        )

    @action(detail=True, methods=["post"], url_path="executive-review")
    def executive_review(self, request, pk=None):
        return self._advance_stage(
            request,
            ExpenseApproval.Stage.EXECUTIVE_REVIEW,
            "EXPENSE_EXECUTIVE_REVIEW",
            {ExpenseApproval.Stage.FINANCE_REVIEW},
        )

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        approval = self.get_object()
        if approval.stage != ExpenseApproval.Stage.EXECUTIVE_REVIEW:
            raise ValidationError("Expense approvals can only be approved after executive review.")
        approval.stage = ExpenseApproval.Stage.APPROVED
        approval.reviewed_by = request.user
        approval.reviewed_at = timezone.now()
        approval.notes = request.data.get("notes", approval.notes)
        approval.save(update_fields=["stage", "reviewed_by", "reviewed_at", "notes"])
        requisition = approval.requisition
        requisition.status = Requisition.Status.APPROVED
        requisition.rejection_reason = ""
        requisition.save(update_fields=["status", "rejection_reason"])
        self._write_audit_log("EXPENSE_APPROVED", approval)
        return Response(self.get_serializer(approval).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        approval = self.get_object()
        if approval.stage == ExpenseApproval.Stage.APPROVED:
            raise ValidationError("Approved expense approvals cannot be rejected.")
        approval.stage = ExpenseApproval.Stage.REJECTED
        approval.reviewed_by = request.user
        approval.reviewed_at = timezone.now()
        approval.decision_reason = request.data.get("decision_reason", approval.decision_reason)
        approval.save(update_fields=["stage", "reviewed_by", "reviewed_at", "decision_reason"])
        requisition = approval.requisition
        requisition.status = Requisition.Status.REJECTED
        requisition.rejection_reason = approval.decision_reason
        requisition.save(update_fields=["status", "rejection_reason"])
        self._write_audit_log("EXPENSE_REJECTED", approval)
        return Response(self.get_serializer(approval).data)


class BankAccountViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = BankAccount.objects.all()
    serializer_class = BankAccountSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_finance"]
    filterset_fields = ["bank_name", "currency", "is_active"]
    search_fields = ["account_name", "bank_name", "account_number", "currency"]
    ordering_fields = ["bank_name", "account_name", "created_at"]


class BankStatementViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = BankStatement.objects.select_related("bank_account", "imported_by")
    serializer_class = BankStatementSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_finance"]
    filterset_fields = ["bank_account", "imported_by"]
    search_fields = ["statement_number", "bank_account__account_name", "bank_account__bank_name"]
    ordering_fields = ["created_at", "period_start", "period_end"]

    def perform_create(self, serializer):
        instance = serializer.save(imported_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="import-lines")
    def import_lines(self, request, pk=None):
        statement = self.get_object()
        serializer = BankStatementImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lines = []
        with db_transaction.atomic():
            statement.statement_number = serializer.validated_data["statement_number"]
            statement.period_start = serializer.validated_data["period_start"]
            statement.period_end = serializer.validated_data["period_end"]
            statement.opening_balance = serializer.validated_data["opening_balance"]
            statement.closing_balance = serializer.validated_data["closing_balance"]
            if serializer.validated_data.get("statement_file") is not None:
                statement.statement_file = serializer.validated_data["statement_file"]
            statement.imported_by = request.user
            statement.save()
            for line_data in serializer.validated_data["lines"]:
                lines.append(
                    BankStatementLine.objects.create(
                        bank_statement=statement,
                        transaction_date=line_data["transaction_date"],
                        description=line_data["description"],
                        reference_number=line_data.get("reference_number", ""),
                        amount=line_data["amount"],
                    )
                )
        self._write_audit_log("BANK_STATEMENT_IMPORTED", statement)
        return Response(
            {
                "statement": self.get_serializer(statement).data,
                "lines": BankStatementLineSerializer(lines, many=True).data,
            },
            status=201,
        )


class BankStatementLineViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = BankStatementLine.objects.select_related("bank_statement")
    serializer_class = BankStatementLineSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_finance"]
    filterset_fields = ["bank_statement", "matched"]
    search_fields = ["description", "reference_number"]
    ordering_fields = ["transaction_date", "amount", "matched"]


class ReconciliationViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Reconciliation.objects.select_related("transaction", "bank_statement_line", "reviewed_by")
    serializer_class = ReconciliationSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_finance"]
    action_roles = {
        "match": [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
        "mark_exception": [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
    }
    filterset_fields = ["transaction", "bank_statement_line", "reviewed_by", "status"]
    search_fields = ["notes", "transaction__bank_reference_number", "bank_statement_line__reference_number"]
    ordering_fields = ["created_at", "matched_at", "status"]

    def perform_create(self, serializer):
        instance = serializer.save(reviewed_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=False, methods=["post"], url_path="auto-match")
    def auto_match(self, request):
        bank_statement_id = request.data.get("bank_statement")
        if not bank_statement_id:
            raise ValidationError("bank_statement is required.")

        statement = BankStatement.objects.select_related("bank_account").prefetch_related("lines").get(pk=bank_statement_id)
        matched = 0
        created = 0
        with db_transaction.atomic():
            for line in statement.lines.filter(matched=False):
                transaction = Transaction.objects.filter(
                    bank_account=statement.bank_account,
                    bank_reference_number=line.reference_number,
                    amount=line.amount,
                ).first()
                if not transaction:
                    continue
                reconciliation, was_created = Reconciliation.objects.get_or_create(
                    transaction=transaction,
                    bank_statement_line=line,
                    defaults={
                        "reviewed_by": request.user,
                        "status": Reconciliation.Status.MATCHED,
                        "difference_amount": 0,
                        "matched_at": timezone.now(),
                    },
                )
                if not was_created and reconciliation.status != Reconciliation.Status.MATCHED:
                    reconciliation.status = Reconciliation.Status.MATCHED
                    reconciliation.reviewed_by = request.user
                    reconciliation.difference_amount = 0
                    reconciliation.matched_at = timezone.now()
                    reconciliation.save(update_fields=["status", "reviewed_by", "difference_amount", "matched_at"])
                line.matched = True
                line.save(update_fields=["matched"])
                transaction.status = Transaction.Status.RECONCILED
                transaction.save(update_fields=["status"])
                matched += 1
                if was_created:
                    created += 1
        self._write_audit_log("RECONCILIATION_AUTO_MATCHED", statement)
        return Response({"matched": matched, "created": created})

    @action(detail=True, methods=["post"], url_path="match")
    def match(self, request, pk=None):
        reconciliation = self.get_object()
        difference_amount = request.data.get("difference_amount", reconciliation.difference_amount)
        if difference_amount not in (0, "0", 0.0, "0.00"):
            raise ValidationError("Matched reconciliations must have zero difference.")

        with db_transaction.atomic():
            reconciliation.status = Reconciliation.Status.MATCHED
            reconciliation.difference_amount = 0
            reconciliation.notes = request.data.get("notes", reconciliation.notes)
            reconciliation.reviewed_by = request.user
            reconciliation.matched_at = timezone.now()
            reconciliation.save(
                update_fields=["status", "difference_amount", "notes", "reviewed_by", "matched_at"]
            )
            transaction = reconciliation.transaction
            transaction.status = Transaction.Status.RECONCILED
            transaction.save(update_fields=["status"])
            statement_line = reconciliation.bank_statement_line
            statement_line.matched = True
            statement_line.save(update_fields=["matched"])
        self._write_audit_log("RECONCILIATION_MATCHED", reconciliation)
        return Response(self.get_serializer(reconciliation).data)

    @action(detail=True, methods=["post"], url_path="mark-exception")
    def mark_exception(self, request, pk=None):
        reconciliation = self.get_object()
        with db_transaction.atomic():
            reconciliation.status = Reconciliation.Status.EXCEPTION
            reconciliation.difference_amount = request.data.get(
                "difference_amount",
                reconciliation.difference_amount,
            )
            reconciliation.notes = request.data.get("notes", reconciliation.notes)
            reconciliation.reviewed_by = request.user
            reconciliation.save(
                update_fields=["status", "difference_amount", "notes", "reviewed_by"]
            )
            reconciliation.bank_statement_line.matched = False
            reconciliation.bank_statement_line.save(update_fields=["matched"])
        self._write_audit_log("RECONCILIATION_EXCEPTION_RECORDED", reconciliation)
        return Response(self.get_serializer(reconciliation).data)
