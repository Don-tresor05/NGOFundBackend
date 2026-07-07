from django.db.models import Q, Sum
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.audit.models import AuditLog, Document
from apps.compliance.models import ComplianceItem
from apps.finance.models import BankStatementLine, ExpenseApproval, Reconciliation, Transaction
from apps.projects.models import BudgetLine, Project
from apps.reports.models import Report, ReportDelivery, ReportSchedule, ReportTemplate
from apps.requisitions.models import Requisition
from apps.reports.serializers import (
    ReportDeliverySerializer,
    ReportScheduleSerializer,
    ReportSerializer,
    ReportTemplateSerializer,
)
from apps.reports.services import dispatch_report_delivery, run_report_schedule


class ReportTemplateViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ReportTemplate.objects.select_related("created_by")
    serializer_class = ReportTemplateSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.SUPER_ADMIN]
    required_permissions = ["manage_reports"]
    filterset_fields = ["is_active", "created_by"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=False, methods=["get"], url_path="available-fields")
    def available_fields(self, request):
        return Response({
            "donor_fields": ["organization_name", "contact_person", "contact_email", "country", "category", "status"],
            "grant_fields": ["grant_title", "donor", "total_amount", "grant_date", "start_date", "end_date", "status"],
            "project_fields": ["name", "grant", "start_date", "end_date", "status"],
            "transaction_fields": ["amount", "currency", "base_amount", "transaction_date", "bank_reference_number", "status"],
            "budget_fields": ["line_name", "allocated_amount", "spent_amount", "remaining_amount"],
            "requisition_fields": ["description", "amount", "requisition_date", "status"],
        })


class ReportViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Report.objects.select_related("grant", "generated_by")
    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR, Role.EXTERNAL_AUDITOR]
    required_permissions = ["manage_reports"]
    filterset_fields = ["grant", "generated_by", "report_type", "format"]
    search_fields = ["report_type", "grant__grant_title"]
    ordering_fields = ["created_at", "report_type", "format"]

    def _build_report_snapshot(self, report):
        grant = report.grant
        donor = grant.donor
        budget_lines = BudgetLine.objects.filter(grant=grant).order_by("line_name")
        projects = Project.objects.filter(grant=grant).order_by("name")
        transactions = Transaction.objects.filter(budget_line__grant=grant).select_related("donor").order_by("-transaction_date", "-created_at")
        donor_transactions = Transaction.objects.filter(donor=donor).order_by("-transaction_date", "-created_at")
        reconciliations = Reconciliation.objects.filter(transaction__budget_line__grant=grant).order_by("-created_at")
        requisitions = Requisition.objects.filter(budget_line__grant=grant).order_by("-created_at")
        expense_approvals = ExpenseApproval.objects.filter(requisition__budget_line__grant=grant).order_by("-created_at")
        transaction_references = list(transactions.exclude(bank_reference_number="").values_list("bank_reference_number", flat=True))
        bank_statement_lines = BankStatementLine.objects.filter(reference_number__in=transaction_references).order_by("-transaction_date", "id")
        audit_logs = AuditLog.objects.filter(
            target_entity_type__in=["grant", "project", "budgetline", "transaction", "requisition", "reconciliation", "report"],
        ).order_by("-timestamp")[:25]
        receipt_documents = Document.objects.filter(
            related_entity_type__in=["requisition", "transaction", "report"],
        ).order_by("-uploaded_at")
        compliance_items = ComplianceItem.objects.all().order_by("title")

        allocated_total = sum((line.allocated_amount for line in budget_lines), 0)
        spent_total = sum((line.spent_amount for line in budget_lines), 0)
        remaining_total = allocated_total - spent_total
        cleared_total = donor_transactions.filter(status__in=[Transaction.Status.CLEARED, Transaction.Status.RECONCILED]).aggregate(total=Sum("amount"))["total"] or 0
        contribution_total = donor_transactions.aggregate(total=Sum("amount"))["total"] or 0
        budget_variance = remaining_total
        utilization_percent = (spent_total / allocated_total * 100) if allocated_total else 0
        burn_rate = spent_total / 12 if spent_total else 0
        missing_receipts = requisitions.filter(Q(receipt_document__isnull=True) | Q(receipt_document="")).count()
        pending_approvals = requisitions.filter(status=Requisition.Status.PENDING).count() + expense_approvals.exclude(
            stage__in=[ExpenseApproval.Stage.APPROVED, ExpenseApproval.Stage.REJECTED]
        ).count()
        matched_reconciliations = reconciliations.filter(status=Reconciliation.Status.MATCHED).count()
        exception_reconciliations = reconciliations.filter(status=Reconciliation.Status.EXCEPTION).count()
        imported_bank_line_count = bank_statement_lines.count()
        unmatched_statement_lines = bank_statement_lines.filter(matched=False).count()
        verified_compliance = compliance_items.filter(verified=True).count()
        overrun_lines = sum(1 for line in budget_lines if line.spent_amount > line.allocated_amount)
        underspent_lines = sum(1 for line in budget_lines if line.spent_amount < line.allocated_amount)

        return {
            "financial_summary": {
                "total_grant_amount": str(grant.total_amount),
                "allocated_budget": str(allocated_total),
                "spent_amount": str(spent_total),
                "remaining_balance": str(remaining_total),
                "budget_variance": str(budget_variance),
                "budget_utilization_percent": round(float(utilization_percent), 2),
                "monthly_burn_rate": str(burn_rate),
            },
            "donor_funding": {
                "donor_name": donor.organization_name,
                "contact_person": donor.contact_person,
                "contact_email": donor.contact_email,
                "contributions_received": str(contribution_total),
                "cleared_funds": str(cleared_total),
                "projects_supported": projects.count(),
                "receipts_generated": donor_transactions.count(),
                "impact_reports_delivered": ReportDelivery.objects.filter(report__grant=grant, status=ReportDelivery.Status.SENT).count(),
            },
            "project_utilization": {
                "project_count": projects.count(),
                "budget_line_count": budget_lines.count(),
                "actual_spending": str(spent_total),
                "remaining_funds": str(remaining_total),
                "overrun_lines": overrun_lines,
                "underspent_lines": underspent_lines,
            },
            "reconciliation_report": {
                "ledger_transactions": transactions.count(),
                "imported_bank_lines": imported_bank_line_count,
                "matched_items": matched_reconciliations,
                "unmatched_items": unmatched_statement_lines,
                "exceptions": exception_reconciliations,
                "reconciliation_rate": round((matched_reconciliations / imported_bank_line_count) * 100, 2) if imported_bank_line_count else 0,
            },
            "audit_compliance_report": {
                "audit_trail_references": len(audit_logs),
                "missing_receipts": missing_receipts,
                "pending_approvals": pending_approvals,
                "policy_exceptions": exception_reconciliations + missing_receipts,
                "compliance_items": compliance_items.count(),
                "verified_compliance_items": verified_compliance,
                "compliance_checklist_status": "complete" if compliance_items.count() and verified_compliance == compliance_items.count() else "in_progress",
            },
            "donor": {
                "id": donor.pk,
                "organization_name": donor.organization_name,
                "contact_person": donor.contact_person,
                "contact_email": donor.contact_email,
                "category": donor.category,
                "status": donor.status,
            },
            "grant": {
                "id": grant.pk,
                "grant_title": grant.grant_title,
                "total_amount": str(grant.total_amount),
                "currency": grant.currency,
                "start_date": grant.start_date.isoformat(),
                "end_date": grant.end_date.isoformat(),
                "status": grant.status,
            },
            "projects": [
                {
                    "id": project.pk,
                    "name": project.name,
                    "status": project.status,
                    "start_date": project.start_date.isoformat(),
                    "end_date": project.end_date.isoformat(),
                }
                for project in projects
            ],
            "project_utilization_lines": [
                {
                    "id": line.pk,
                    "line_name": line.line_name,
                    "allocated_amount": str(line.allocated_amount),
                    "spent_amount": str(line.spent_amount),
                    "remaining_amount": str(line.remaining_amount),
                    "variance_status": "overrun" if line.spent_amount > line.allocated_amount else "underspent" if line.spent_amount < line.allocated_amount else "on_budget",
                }
                for line in budget_lines
            ],
            "budget_lines": [
                {
                    "id": line.pk,
                    "line_name": line.line_name,
                    "allocated_amount": str(line.allocated_amount),
                    "spent_amount": str(line.spent_amount),
                    "remaining_amount": str(line.remaining_amount),
                }
                for line in budget_lines
            ],
            "transactions": [
                {
                    "id": transaction.pk,
                    "budget_line": transaction.budget_line_id,
                    "amount": str(transaction.amount),
                    "currency": transaction.currency,
                    "donor": transaction.donor_id,
                    "transaction_date": transaction.transaction_date.isoformat(),
                    "bank_reference_number": transaction.bank_reference_number,
                    "status": transaction.status,
                }
                for transaction in transactions
            ],
            "bank_statement_lines": [
                {
                    "id": line.pk,
                    "transaction_date": line.transaction_date.isoformat(),
                    "reference_number": line.reference_number,
                    "amount": str(line.amount),
                    "matched": line.matched,
                }
                for line in bank_statement_lines
            ],
            "reconciliations": [
                {
                    "id": reconciliation.pk,
                    "transaction": reconciliation.transaction_id,
                    "bank_statement_line": reconciliation.bank_statement_line_id,
                    "status": reconciliation.status,
                    "difference_amount": str(reconciliation.difference_amount),
                    "created_at": reconciliation.created_at.isoformat(),
                    "matched_at": reconciliation.matched_at.isoformat() if reconciliation.matched_at else None,
                }
                for reconciliation in reconciliations
            ],
            "audit_references": [
                {
                    "id": log.pk,
                    "action_type": log.action_type,
                    "target_entity_type": log.target_entity_type,
                    "target_entity_id": log.target_entity_id,
                    "timestamp": log.timestamp.isoformat(),
                }
                for log in audit_logs
            ],
            "compliance_items": [
                {
                    "id": item.pk,
                    "title": item.title,
                    "owner": item.owner,
                    "verified": item.verified,
                    "verified_at": item.verified_at.isoformat() if item.verified_at else None,
                }
                for item in compliance_items
            ],
        }

    def perform_create(self, serializer):
        instance = serializer.save(generated_by=self.request.user)
        custom_fields = instance.custom_fields or {}
        custom_fields["snapshot"] = self._build_report_snapshot(instance)
        instance.custom_fields = custom_fields
        instance.save(update_fields=["custom_fields"])
        self._write_audit_log(self.audit_create_action, instance)
        
        # Notify donors who funded this grant's project
        if instance.grant:
            from apps.accounts.models import User, Notification
            from apps.donors.models import Donor
            
            donor = instance.grant.donor
            if donor:
                donor_user = User.objects.filter(email=donor.contact_email).first()
                if donor_user:
                    project_name = instance.grant.projects.first().name if instance.grant.projects.exists() else instance.grant.grant_title
                    Notification.objects.create(
                        user=donor_user,
                        type='impact_report_ready',
                        title='New Impact Report Available',
                        message=f'A new {instance.report_type} report is ready for {project_name}. See the impact of your contribution!'
                    )

    @action(detail=False, methods=["post"], url_path="backfill-snapshots")
    def backfill_snapshots(self, request):
        reports = Report.objects.filter(grant__isnull=False).exclude(
            custom_fields__snapshot__isnull=False
        )
        updated = 0
        for report in reports:
            custom_fields = report.custom_fields or {}
            if custom_fields.get("snapshot"):
                continue
            custom_fields["snapshot"] = self._build_report_snapshot(report)
            report.custom_fields = custom_fields
            report.save(update_fields=["custom_fields"])
            updated += 1
        return Response({"backfilled": updated})

    @action(detail=True, methods=["post"], url_path="deliver")
    def deliver(self, request, pk=None):
        report = self.get_object()
        destination = request.data.get("destination", request.user.email)
        delivery_method = request.data.get("delivery_method", "email")
        delivery = ReportDelivery.objects.create(
            report=report,
            created_by=request.user,
            delivery_method=delivery_method,
            destination=destination,
        )
        dispatch_report_delivery(delivery)
        self._write_audit_log("REPORT_DELIVERED", report)
        return Response(ReportDeliverySerializer(delivery).data)


class ReportDeliveryViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ReportDelivery.objects.select_related("report", "created_by")
    serializer_class = ReportDeliverySerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR, Role.EXTERNAL_AUDITOR]
    required_permissions = ["manage_reports"]
    filterset_fields = ["report", "created_by", "delivery_method", "status"]
    search_fields = ["destination", "report__report_type"]
    ordering_fields = ["created_at", "sent_at", "status"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="dispatch", url_name="dispatch")
    def dispatch_delivery(self, request, pk=None):
        delivery = self.get_object()
        dispatch_report_delivery(delivery)
        self._write_audit_log("REPORT_DELIVERY_DISPATCHED", delivery)
        return Response(self.get_serializer(delivery).data)


class ReportScheduleViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ReportSchedule.objects.select_related("grant", "created_by")
    serializer_class = ReportScheduleSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_reports"]
    action_roles = {
        "run": [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
        "activate": [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
        "deactivate": [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR],
    }
    filterset_fields = ["grant", "created_by", "frequency", "delivery_method", "is_active"]
    search_fields = ["report_type", "recipient_emails"]
    ordering_fields = ["created_at", "next_run_at", "frequency"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        schedule = self.get_object()
        schedule.is_active = True
        schedule.save(update_fields=["is_active"])
        self._write_audit_log("REPORT_SCHEDULE_ACTIVATED", schedule)
        return Response(self.get_serializer(schedule).data)

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        schedule = self.get_object()
        schedule.is_active = False
        schedule.save(update_fields=["is_active"])
        self._write_audit_log("REPORT_SCHEDULE_DEACTIVATED", schedule)
        return Response(self.get_serializer(schedule).data)

    @action(detail=True, methods=["post"], url_path="run")
    def run(self, request, pk=None):
        schedule = self.get_object()
        deliveries = run_report_schedule(schedule, triggered_by=request.user)
        self._write_audit_log("REPORT_SCHEDULE_RUN", schedule)
        return Response(
            {
                "schedule": self.get_serializer(schedule).data,
                "deliveries": ReportDeliverySerializer(deliveries, many=True).data,
            }
        )
