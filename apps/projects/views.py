from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.projects.models import BudgetLine, Project, ProjectMember, ReallocationRequest
from apps.projects.serializers import (
    BudgetLineSerializer,
    ProjectMemberSerializer,
    ProjectSerializer,
    ReallocationRequestSerializer,
)


class ProjectViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Project.objects.select_related("grant")
    serializer_class = ProjectSerializer
    allowed_roles = [Role.FINANCE_OFFICER, Role.PROJECT_MANAGER, Role.EXECUTIVE_DIRECTOR, Role.DONOR_USER]
    required_permissions = ["manage_projects"]
    action_roles = {
        "activate": [Role.FINANCE_OFFICER, Role.PROJECT_MANAGER, Role.EXECUTIVE_DIRECTOR],
        "complete": [Role.FINANCE_OFFICER, Role.PROJECT_MANAGER, Role.EXECUTIVE_DIRECTOR],
        "reopen": [Role.FINANCE_OFFICER, Role.PROJECT_MANAGER, Role.EXECUTIVE_DIRECTOR],
    }
    filterset_fields = ["grant", "status"]
    search_fields = ["name", "description", "grant__grant_title"]
    ordering_fields = ["start_date", "end_date", "status", "name"]
    
    def get_permissions(self):
        """Allow public read access, require auth for modifications"""
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated(), RoleBasedPermission()]

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        project = self.get_object()
        if project.status == Project.Status.COMPLETED:
            raise ValidationError("Completed projects cannot be activated without reopening first.")
        project.status = Project.Status.ACTIVE
        project.save(update_fields=["status"])
        self._write_audit_log("PROJECT_ACTIVATED", project)
        return Response(self.get_serializer(project).data)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        project = self.get_object()
        project.status = Project.Status.COMPLETED
        project.save(update_fields=["status"])
        self._write_audit_log("PROJECT_COMPLETED", project)
        return Response(self.get_serializer(project).data)

    @action(detail=True, methods=["post"], url_path="reopen")
    def reopen(self, request, pk=None):
        project = self.get_object()
        if project.status != Project.Status.COMPLETED:
            raise ValidationError("Only completed projects can be reopened.")
        project.status = Project.Status.ACTIVE
        project.save(update_fields=["status"])
        self._write_audit_log("PROJECT_REOPENED", project)
        return Response(self.get_serializer(project).data)


class BudgetLineViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = BudgetLine.objects.select_related("grant")
    serializer_class = BudgetLineSerializer
    allowed_roles = [Role.FINANCE_OFFICER, Role.PROJECT_MANAGER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_projects"]
    filterset_fields = ["grant"]
    search_fields = ["line_name", "grant__grant_title"]
    ordering_fields = ["allocated_amount", "spent_amount", "line_name"]
    
    def get_permissions(self):
        """Allow public read access"""
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated(), RoleBasedPermission()]


class ReallocationRequestViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ReallocationRequest.objects.select_related(
        "source_budget_line",
        "target_budget_line",
        "requested_by",
        "reviewed_by",
    )
    serializer_class = ReallocationRequestSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.PROJECT_MANAGER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_projects"]
    filterset_fields = ["source_budget_line", "target_budget_line", "requested_by", "status"]
    search_fields = ["reason", "source_budget_line__line_name", "target_budget_line__line_name"]
    ordering_fields = ["created_at", "amount", "status"]

    def perform_create(self, serializer):
        instance = serializer.save(requested_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        request_item = self.get_object()
        with db_transaction.atomic():
            request_item.refresh_from_db()
            source = request_item.source_budget_line
            target = request_item.target_budget_line
            if request_item.amount > source.remaining_amount:
                return Response({"detail": "Source budget line does not have enough remaining balance."}, status=400)
            source.allocated_amount -= request_item.amount
            target.allocated_amount += request_item.amount
            source.save(update_fields=["allocated_amount"])
            target.save(update_fields=["allocated_amount"])
            request_item.status = ReallocationRequest.Status.APPROVED
            request_item.reviewed_by = request.user
            request_item.reviewed_at = timezone.now()
            request_item.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        self._write_audit_log("REALLOCATION_APPROVED", request_item)
        return Response(self.get_serializer(request_item).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        request_item = self.get_object()
        request_item.status = ReallocationRequest.Status.REJECTED
        request_item.reviewed_by = request.user
        request_item.reviewed_at = timezone.now()
        request_item.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        self._write_audit_log("REALLOCATION_REJECTED", request_item)
        return Response(self.get_serializer(request_item).data)


class ProjectMemberViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ProjectMember.objects.select_related("project", "user")
    serializer_class = ProjectMemberSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.PROJECT_MANAGER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_projects"]
    filterset_fields = ["project", "user", "status", "member_role"]
    search_fields = ["member_role", "project__name", "user__full_name", "user__email"]
    ordering_fields = ["assigned_at", "status", "member_role"]

    def perform_create(self, serializer):
        instance = serializer.save()
        self._write_audit_log(self.audit_create_action, instance)
