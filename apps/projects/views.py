from django.db import transaction as db_transaction
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from apps.accounts.models import Notification, Role, User
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.donors.models import Donor
from apps.projects.models import BudgetLine, Project, ProjectMember, ReallocationRequest
from apps.projects.serializers import (
    PROJECT_ARCHIVE_ROLES,
    PROJECT_EDIT_ROLES,
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

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)
        self._notify_donors_of_new_project(instance)

    def _can_edit(self, project):
        """The creator can edit their own project; managers can edit any project."""
        user = self.request.user
        if user.is_superuser or user.role_id == Role.SUPER_ADMIN:
            return True
        return user.role_id in PROJECT_EDIT_ROLES or (
            project.created_by_id is not None and project.created_by_id == user.id
        )

    def _can_archive(self, project):
        """Only Finance Officer / Executive Director can archive or delete projects."""
        user = self.request.user
        if user.is_superuser or user.role_id == Role.SUPER_ADMIN:
            return True
        return user.role_id in PROJECT_ARCHIVE_ROLES

    def update(self, request, *args, **kwargs):
        project = self.get_object()
        if project.status == Project.Status.CANCELLED:
            return Response({"detail": "Trashed projects cannot be edited. Restore the project first."}, status=400)
        if not self._can_edit(project):
            return Response({"detail": "You don't have permission to edit this project."}, status=403)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        project = self.get_object()
        if project.status == Project.Status.CANCELLED:
            return Response({"detail": "Trashed projects cannot be edited. Restore the project first."}, status=400)
        if not self._can_edit(project):
            return Response({"detail": "You don't have permission to edit this project."}, status=403)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Soft delete — archive the project instead of removing the record."""
        project = self.get_object()
        if not self._can_archive(project):
            return Response({"detail": "You don't have permission to delete this project."}, status=403)
        project.archived_from_status = project.status
        project.status = Project.Status.CANCELLED
        project.save(update_fields=["status", "archived_from_status"])
        self._write_audit_log("PROJECT_ARCHIVED", project)
        return Response(status=204)

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        project = self.get_object()
        if not self._can_archive(project):
            return Response({"detail": "You don't have permission to move this project to the trash."}, status=403)
        if project.status == Project.Status.CANCELLED:
            return Response({"detail": "Project is already in the trash."}, status=400)
        project.archived_from_status = project.status
        project.status = Project.Status.CANCELLED
        project.save(update_fields=["status", "archived_from_status"])
        self._write_audit_log("PROJECT_ARCHIVED", project)
        return Response(self.get_serializer(project).data)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        project = self.get_object()
        if not self._can_archive(project):
            return Response({"detail": "You don't have permission to restore this project."}, status=403)
        if project.status != Project.Status.CANCELLED:
            return Response({"detail": "Only projects in the trash can be restored."}, status=400)
        project.status = project.archived_from_status or Project.Status.ACTIVE
        project.archived_from_status = None
        project.save(update_fields=["status", "archived_from_status"])
        self._write_audit_log("PROJECT_RESTORED", project)
        return Response(self.get_serializer(project).data)

    @action(detail=True, methods=["post"], url_path="delete-permanently")
    def delete_permanently(self, request, pk=None):
        project = self.get_object()
        if not self._can_archive(project):
            return Response({"detail": "You don't have permission to permanently delete this project."}, status=403)
        if project.status != Project.Status.CANCELLED:
            return Response({"detail": "Only projects in the trash can be permanently deleted."}, status=400)
        self._write_audit_log("PROJECT_DELETED", project)
        project.delete()
        return Response(status=204)

    def _notify_donors_of_new_project(self, project):
        """Notify donor portal users when a new project is launched."""
        donor_emails = list(
            Donor.objects.filter(status=Donor.Status.ACTIVE).values_list("contact_email", flat=True)
        )
        if not donor_emails:
            return
        grant_title = project.grant.grant_title if project.grant else "General Fund"
        donor_users = User.objects.filter(email__in=donor_emails, is_active=True).exclude(
            pk=self.request.user.pk
        )
        if not donor_users.exists():
            return
        Notification.objects.bulk_create(
            [
                Notification(
                    user=donor_user,
                    type="new_project",
                    title="New Project Launched",
                    message=(
                        f'Great news — a new project "{project.name}" is now running under the '
                        f"{grant_title} grant. Visit the Projects page to explore it and see the "
                        f"impact your support makes possible!"
                    ),
                )
                for donor_user in donor_users
            ]
        )

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
        if request_item.status != ReallocationRequest.Status.PENDING:
            return Response({"detail": "This request has already been reviewed."}, status=400)
        with db_transaction.atomic():
            request_item = ReallocationRequest.objects.select_for_update().get(pk=request_item.pk)
            if request_item.status != ReallocationRequest.Status.PENDING:
                return Response({"detail": "This request has already been reviewed."}, status=400)
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
        if request_item.status != ReallocationRequest.Status.PENDING:
            return Response({"detail": "This request has already been reviewed."}, status=400)
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
