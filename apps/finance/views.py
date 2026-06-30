from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
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
    PeriodClose,
    PaymentBatch,
    Reconciliation,
    SpendingAlert,
    ScheduledPayment,
    Transaction,
    Vendor,
)
from apps.finance.serializers import (
    BankAccountSerializer,
    BankStatementImportSerializer,
    BankStatementLineSerializer,
    BankStatementSerializer,
    CurrencyRateSerializer,
    ExpenseApprovalSerializer,
    PeriodCloseSerializer,
    PaymentBatchSerializer,
    ReconciliationSerializer,
    SpendingAlertSerializer,
    ScheduledPaymentSerializer,
    TransactionSerializer,
    VendorSerializer,
)
from apps.projects.models import BudgetLine, Project
from apps.requisitions.models import Requisition


def _decimal(value):
    return value or Decimal("0")


class FinanceDashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_finance"]

    def list(self, request):
        try:
            budget_lines = BudgetLine.objects.select_related("grant")
            transactions = Transaction.objects.select_related("budget_line", "bank_account")
            scheduled_payments = ScheduledPayment.objects.select_related("vendor", "budget_line")
            statement_lines = BankStatementLine.objects.select_related("bank_statement", "bank_statement__bank_account")
            reconciliations = Reconciliation.objects.select_related("transaction", "bank_statement_line")

            total_budget = _decimal(budget_lines.aggregate(total=Sum("allocated_amount"))["total"])
            total_spent = _decimal(budget_lines.aggregate(total=Sum("spent_amount"))["total"])
            total_income = _decimal(
                transactions.filter(status__in=[Transaction.Status.CLEARED, Transaction.Status.RECONCILED]).aggregate(total=Sum("amount"))["total"]
            )
            scheduled_total = _decimal(
                scheduled_payments.exclude(status__in=[ScheduledPayment.Status.PAID, ScheduledPayment.Status.CANCELLED]).aggregate(total=Sum("amount"))["total"]
            )
            overdue_total = _decimal(
                scheduled_payments.filter(due_date__lt=timezone.now().date()).exclude(
                    status__in=[ScheduledPayment.Status.PAID, ScheduledPayment.Status.CANCELLED]
                ).aggregate(total=Sum("amount"))["total"]
            )

            project_rows = []
            for project in Project.objects.select_related("grant").order_by("name"):
                lines = list(budget_lines.filter(grant=project.grant))
                allocated = sum((line.allocated_amount for line in lines), Decimal("0"))
                spent = sum((line.spent_amount for line in lines), Decimal("0"))
                utilization = float((spent / allocated) * 100) if allocated else 0.0
                project_rows.append(
                    {
                        "project_id": project.pk,
                        "project_name": project.name,
                        "grant_id": project.grant_id,
                        "grant_title": project.grant.grant_title,
                        "allocated": allocated,
                        "spent": spent,
                        "remaining": allocated - spent,
                        "utilization": round(utilization, 2),
                        "status": project.status,
                    }
                )

            alerts = []
            for line in budget_lines:
                utilization = float((line.spent_amount / line.allocated_amount) * 100) if line.allocated_amount else 0.0
                if utilization >= 100:
                    severity = "critical"
                elif utilization >= 90:
                    severity = "warning"
                elif utilization >= 80:
                    severity = "watch"
                else:
                    continue
                alerts.append(
                    {
                        "severity": severity,
                        "budget_line_id": line.pk,
                        "budget_line": line.line_name,
                        "grant": line.grant.grant_title,
                        "allocated": line.allocated_amount,
                        "spent": line.spent_amount,
                        "remaining": line.remaining_amount,
                        "utilization": round(utilization, 2),
                    }
                )

            account_rows = []
            for account in BankAccount.objects.order_by("bank_name", "account_name"):
                account_statement_lines = statement_lines.filter(bank_statement__bank_account=account)
                unmatched = account_statement_lines.filter(matched=False).count()
                matched = account_statement_lines.filter(matched=True).count()
                account_rows.append(
                    {
                        "bank_account_id": account.pk,
                        "account_name": account.account_name,
                        "bank_name": account.bank_name,
                        "currency": account.currency,
                        "matched_lines": matched,
                        "unmatched_lines": unmatched,
                        "reconciliations": reconciliations.filter(transaction__bank_account=account).count(),
                        "reconciliation_rate": round((matched / (matched + unmatched)) * 100, 2) if matched + unmatched else 0,
                    }
                )

            vendor_rows = []
            for vendor in Vendor.objects.prefetch_related("scheduled_payments").order_by("name"):
                payments = vendor.scheduled_payments.all()
                vendor_rows.append(
                    {
                        "vendor_id": vendor.pk,
                        "name": vendor.name,
                        "status": vendor.status,
                        "scheduled_count": payments.count(),
                        "paid_amount": sum((payment.amount for payment in payments if payment.status == ScheduledPayment.Status.PAID), Decimal("0")),
                        "outstanding_amount": sum(
                            (
                                payment.amount
                                for payment in payments
                                if payment.status not in [ScheduledPayment.Status.PAID, ScheduledPayment.Status.CANCELLED]
                            ),
                            Decimal("0"),
                        ),
                    }
                )

            recent_transactions = TransactionSerializer(transactions.order_by("-transaction_date", "-created_at")[:8], many=True).data
            upcoming_payments = ScheduledPaymentSerializer(
                scheduled_payments.exclude(status__in=[ScheduledPayment.Status.PAID, ScheduledPayment.Status.CANCELLED]).order_by("due_date")[:8],
                many=True,
            ).data

            monthly_burn_rate = total_spent / Decimal("12") if total_spent else Decimal("0")
            forecast = {
                "monthly_burn_rate": monthly_burn_rate,
                "next_month_balance": (total_budget - total_spent) - monthly_burn_rate,
                "three_month_balance": (total_budget - total_spent) - (monthly_burn_rate * Decimal("3")),
                "runway_months": int((total_budget - total_spent) / monthly_burn_rate) if monthly_burn_rate > 0 else None,
            }

            return Response(
                {
                    "totals": {
                        "total_budget": total_budget,
                        "total_spent": total_spent,
                        "remaining_budget": total_budget - total_spent,
                        "total_income": total_income,
                        "scheduled_payments": scheduled_total,
                        "overdue_payments": overdue_total,
                        "pending_requisitions": Requisition.objects.filter(status=Requisition.Status.PENDING).count(),
                        "pending_expense_approvals": ExpenseApproval.objects.exclude(
                            stage__in=[ExpenseApproval.Stage.APPROVED, ExpenseApproval.Stage.REJECTED]
                        ).count(),
                        "unmatched_statement_lines": statement_lines.filter(matched=False).count(),
                        "reconciliation_exceptions": reconciliations.filter(status=Reconciliation.Status.EXCEPTION).count(),
                    },
                    "project_budgets": project_rows,
                    "budget_alerts": sorted(alerts, key=lambda row: row["utilization"], reverse=True),
                    "bank_accounts": account_rows,
                    "vendors": vendor_rows,
                    "recent_transactions": recent_transactions,
                    "upcoming_payments": upcoming_payments,
                    "forecast": forecast,
                }
            )
        except Exception as exc:
            return Response(
                {
                    "totals": {
                        "total_budget": Decimal("0"),
                        "total_spent": Decimal("0"),
                        "remaining_budget": Decimal("0"),
                        "total_income": Decimal("0"),
                        "scheduled_payments": Decimal("0"),
                        "overdue_payments": Decimal("0"),
                        "pending_requisitions": 0,
                        "pending_expense_approvals": 0,
                        "unmatched_statement_lines": 0,
                        "reconciliation_exceptions": 0,
                    },
                    "project_budgets": [],
                    "budget_alerts": [],
                    "bank_accounts": [],
                    "vendors": [],
                    "recent_transactions": [],
                    "upcoming_payments": [],
                    "forecast": {
                        "monthly_burn_rate": Decimal("0"),
                        "next_month_balance": Decimal("0"),
                        "three_month_balance": Decimal("0"),
                        "runway_months": None,
                    },
                    "error": str(exc),
                },
                status=200,
            )


def _alert_severity(utilization):
    if utilization >= 100:
        return SpendingAlert.Severity.CRITICAL
    if utilization >= 90:
        return SpendingAlert.Severity.WARNING
    return SpendingAlert.Severity.WATCH


class SpendingAlertViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = SpendingAlert.objects.select_related("budget_line", "acknowledged_by", "resolved_by")
    serializer_class = SpendingAlertSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_finance"]
    filterset_fields = ["budget_line", "severity", "status"]
    search_fields = ["message", "budget_line__line_name"]
    ordering_fields = ["created_at", "threshold_percent", "severity", "status"]

    @action(detail=False, methods=["post"], url_path="generate")
    def generate(self, request):
        created = 0
        refreshed = 0
        with db_transaction.atomic():
            for line in BudgetLine.objects.select_related("grant").all():
                if not line.allocated_amount:
                    continue
                utilization = float((line.spent_amount / line.allocated_amount) * 100)
                if utilization < 80:
                    continue
                threshold = Decimal(str(round(utilization, 2)))
                severity = _alert_severity(utilization)
                alert, was_created = SpendingAlert.objects.get_or_create(
                    budget_line=line,
                    status=SpendingAlert.Status.OPEN,
                    defaults={
                        "threshold_percent": threshold,
                        "severity": severity,
                        "message": f"{line.line_name} is at {round(utilization, 2)}% utilization.",
                    },
                )
                if was_created:
                    created += 1
                else:
                    alert.threshold_percent = threshold
                    alert.severity = severity
                    alert.message = f"{line.line_name} is at {round(utilization, 2)}% utilization."
                    alert.save(update_fields=["threshold_percent", "severity", "message"])
                    refreshed += 1
        return Response({"created": created, "refreshed": refreshed})

    @action(detail=True, methods=["post"], url_path="acknowledge")
    def acknowledge(self, request, pk=None):
        alert = self.get_object()
        alert.status = SpendingAlert.Status.ACKNOWLEDGED
        alert.acknowledged_by = request.user
        alert.acknowledged_at = timezone.now()
        alert.save(update_fields=["status", "acknowledged_by", "acknowledged_at"])
        return Response(self.get_serializer(alert).data)

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        alert = self.get_object()
        alert.status = SpendingAlert.Status.RESOLVED
        alert.resolved_by = request.user
        alert.resolved_at = timezone.now()
        alert.save(update_fields=["status", "resolved_by", "resolved_at"])
        return Response(self.get_serializer(alert).data)


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
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR, Role.DONOR_USER]
    required_permissions = ["manage_finance"]
    action_roles = {
        "reconcile": [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
    }
    filterset_fields = ["budget_line", "processed_by", "status", "transaction_date"]
    search_fields = ["bank_reference_number", "budget_line__line_name"]
    ordering_fields = ["transaction_date", "amount", "status", "created_at"]
    
    def get_permissions(self):
        """Allow public read access"""
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated(), RoleBasedPermission()]

    def perform_create(self, serializer):
        with db_transaction.atomic():
            instance = serializer.save(processed_by=self.request.user)
            if instance.requisition_id:
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


class VendorViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Vendor.objects.prefetch_related("scheduled_payments")
    serializer_class = VendorSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_finance"]
    filterset_fields = ["status", "category"]
    search_fields = ["name", "contact_person", "email", "phone", "category"]
    ordering_fields = ["name", "created_at", "status"]


class ScheduledPaymentViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ScheduledPayment.objects.select_related(
        "vendor",
        "requisition",
        "budget_line",
        "bank_account",
        "batch",
        "scheduled_by",
        "approved_by",
        "paid_by",
        "transaction",
    )
    serializer_class = ScheduledPaymentSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_finance"]
    action_roles = {
        "approve": [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
        "pay": [Role.FINANCE_OFFICER],
        "cancel": [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
    }
    filterset_fields = ["vendor", "budget_line", "bank_account", "status", "due_date"]
    search_fields = ["description", "vendor__name", "notes"]
    ordering_fields = ["due_date", "amount", "status", "created_at"]

    def perform_create(self, serializer):
        instance = serializer.save(scheduled_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        payment = self.get_object()
        if payment.status not in {ScheduledPayment.Status.SCHEDULED, ScheduledPayment.Status.OVERDUE}:
            raise ValidationError("Only scheduled or overdue payments can be approved.")
        payment.status = ScheduledPayment.Status.APPROVED
        payment.approved_by = request.user
        payment.approved_at = timezone.now()
        payment.save(update_fields=["status", "approved_by", "approved_at"])
        self._write_audit_log("SCHEDULED_PAYMENT_APPROVED", payment)
        return Response(self.get_serializer(payment).data)

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, pk=None):
        payment = self.get_object()
        if payment.status != ScheduledPayment.Status.APPROVED:
            raise ValidationError("Only approved payments can be paid.")
        if payment.amount > payment.budget_line.remaining_amount:
            raise ValidationError("Payment exceeds the budget line remaining balance.")

        with db_transaction.atomic():
            transaction = Transaction.objects.create(
                requisition=payment.requisition,
                budget_line=payment.budget_line,
                bank_account=payment.bank_account,
                processed_by=request.user,
                amount=payment.amount,
                currency=payment.currency,
                transaction_date=timezone.now().date(),
                bank_reference_number=request.data.get("bank_reference_number") or f"PAY-{payment.pk}",
                status=Transaction.Status.CLEARED,
            )
            payment.budget_line.spent_amount += payment.amount
            payment.budget_line.save(update_fields=["spent_amount"])
            payment.status = ScheduledPayment.Status.PAID
            payment.paid_by = request.user
            payment.paid_at = timezone.now()
            payment.transaction = transaction
            payment.save(update_fields=["status", "paid_by", "paid_at", "transaction"])
        self._write_audit_log("SCHEDULED_PAYMENT_PAID", payment)
        return Response(self.get_serializer(payment).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        payment = self.get_object()
        if payment.status == ScheduledPayment.Status.PAID:
            raise ValidationError("Paid payments cannot be cancelled.")
        payment.status = ScheduledPayment.Status.CANCELLED
        payment.notes = request.data.get("notes", payment.notes)
        payment.save(update_fields=["status", "notes"])
        self._write_audit_log("SCHEDULED_PAYMENT_CANCELLED", payment)
        return Response(self.get_serializer(payment).data)


class PaymentBatchViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = PaymentBatch.objects.prefetch_related("scheduled_payments")
    serializer_class = PaymentBatchSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_finance"]
    filterset_fields = ["status", "scheduled_for", "created_by"]
    search_fields = ["name", "notes"]
    ordering_fields = ["created_at", "scheduled_for", "status"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="add-payments")
    def add_payments(self, request, pk=None):
        batch = self.get_object()
        payment_ids = request.data.get("scheduled_payments") or []
        if not isinstance(payment_ids, list) or not payment_ids:
            raise ValidationError("scheduled_payments must be a non-empty list.")
        payments = ScheduledPayment.objects.filter(pk__in=payment_ids)
        if payments.count() != len(set(payment_ids)):
            raise ValidationError("One or more scheduled payments were not found.")
        with db_transaction.atomic():
            payments.update(batch=batch)
            batch.status = PaymentBatch.Status.READY
            batch.save(update_fields=["status"])
        return Response(self.get_serializer(batch).data)

    @action(detail=True, methods=["post"], url_path="process")
    def process(self, request, pk=None):
        batch = self.get_object()
        payments = list(batch.scheduled_payments.exclude(status__in=[ScheduledPayment.Status.PAID, ScheduledPayment.Status.CANCELLED]))
        if not payments:
            raise ValidationError("The batch does not contain any payable scheduled payments.")

        processed = 0
        with db_transaction.atomic():
            batch.status = PaymentBatch.Status.PROCESSING
            batch.processed_by = request.user
            batch.processed_at = timezone.now()
            batch.save(update_fields=["status", "processed_by", "processed_at"])
            for payment in payments:
                if payment.status == ScheduledPayment.Status.SCHEDULED:
                    payment.status = ScheduledPayment.Status.APPROVED
                    payment.approved_by = request.user
                    payment.approved_at = timezone.now()
                    payment.save(update_fields=["status", "approved_by", "approved_at"])
                if payment.status == ScheduledPayment.Status.APPROVED:
                    if payment.amount > payment.budget_line.remaining_amount:
                        raise ValidationError(f"Payment {payment.pk} exceeds the budget line balance.")
                    transaction = Transaction.objects.create(
                        requisition=payment.requisition,
                        budget_line=payment.budget_line,
                        bank_account=payment.bank_account,
                        processed_by=request.user,
                        amount=payment.amount,
                        currency=payment.currency,
                        transaction_date=timezone.now().date(),
                        bank_reference_number=request.data.get("bank_reference_number") or f"BATCH-{batch.pk}-{payment.pk}",
                        status=Transaction.Status.CLEARED,
                    )
                    payment.budget_line.spent_amount += payment.amount
                    payment.budget_line.save(update_fields=["spent_amount"])
                    payment.status = ScheduledPayment.Status.PAID
                    payment.paid_by = request.user
                    payment.paid_at = timezone.now()
                    payment.transaction = transaction
                    payment.save(update_fields=["status", "paid_by", "paid_at", "transaction"])
                    processed += 1
            batch.status = PaymentBatch.Status.COMPLETED
            batch.save(update_fields=["status"])
        return Response({"processed": processed, "batch": self.get_serializer(batch).data})


class PeriodCloseViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = PeriodClose.objects.select_related("bank_account", "prepared_by", "closed_by")
    serializer_class = PeriodCloseSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_finance"]
    filterset_fields = ["bank_account", "status", "period_start", "period_end"]
    search_fields = ["notes", "bank_account__account_name", "bank_account__bank_name"]
    ordering_fields = ["period_end", "created_at", "status"]

    def perform_create(self, serializer):
        instance = serializer.save(prepared_by=self.request.user, prepared_at=timezone.now())
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="prepare")
    def prepare(self, request, pk=None):
        close = self.get_object()
        lines = BankStatementLine.objects.filter(
            bank_statement__period_start__gte=close.period_start,
            bank_statement__period_end__lte=close.period_end,
        )
        if close.bank_account_id:
            lines = lines.filter(bank_statement__bank_account=close.bank_account)
        close.unmatched_statement_lines = lines.filter(matched=False).count()
        close.reconciliation_exceptions = Reconciliation.objects.filter(
            created_at__date__range=(close.period_start, close.period_end),
            status=Reconciliation.Status.EXCEPTION,
        ).count()
        if close.bank_account_id:
            close.reconciliation_exceptions = Reconciliation.objects.filter(
                created_at__date__range=(close.period_start, close.period_end),
                status=Reconciliation.Status.EXCEPTION,
                transaction__bank_account=close.bank_account,
            ).count()
        close.status = PeriodClose.Status.PREPARED
        close.prepared_by = request.user
        close.prepared_at = timezone.now()
        close.save(
            update_fields=[
                "unmatched_statement_lines",
                "reconciliation_exceptions",
                "status",
                "prepared_by",
                "prepared_at",
            ]
        )
        return Response(self.get_serializer(close).data)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        close = self.get_object()
        if close.unmatched_statement_lines or close.reconciliation_exceptions:
            raise ValidationError("Period cannot be closed while there are unmatched lines or reconciliation exceptions.")
        close.status = PeriodClose.Status.CLOSED
        close.closed_by = request.user
        close.closed_at = timezone.now()
        close.notes = request.data.get("notes", close.notes)
        close.save(update_fields=["status", "closed_by", "closed_at", "notes"])
        self._write_audit_log("PERIOD_CLOSED", close)
        return Response(self.get_serializer(close).data)


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
