from django.db import transaction as db_transaction
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.finance.models import Transaction
from apps.finance.serializers import TransactionSerializer


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
