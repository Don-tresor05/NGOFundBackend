from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.finance.models import ExpenseApproval, Transaction
from apps.finance.serializers import ExpenseApprovalSerializer, TransactionSerializer
from apps.requisitions.models import Requisition


class TransactionViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Transaction.objects.select_related("requisition", "budget_line", "processed_by")
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR, Role.DONOR_USER]
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
    filterset_fields = ["requisition", "requested_by", "reviewed_by", "stage"]
    search_fields = ["notes", "decision_reason", "requisition__description"]
    ordering_fields = ["created_at", "reviewed_at", "stage"]

    def perform_create(self, serializer):
        instance = serializer.save(requested_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    def _advance_stage(self, request, pk, stage, action_name):
        approval = self.get_object()
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
        return self._advance_stage(request, pk, ExpenseApproval.Stage.DEPARTMENT_REVIEW, "EXPENSE_DEPARTMENT_REVIEW")

    @action(detail=True, methods=["post"], url_path="finance-review")
    def finance_review(self, request, pk=None):
        return self._advance_stage(request, pk, ExpenseApproval.Stage.FINANCE_REVIEW, "EXPENSE_FINANCE_REVIEW")

    @action(detail=True, methods=["post"], url_path="executive-review")
    def executive_review(self, request, pk=None):
        return self._advance_stage(request, pk, ExpenseApproval.Stage.EXECUTIVE_REVIEW, "EXPENSE_EXECUTIVE_REVIEW")

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        approval = self.get_object()
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
