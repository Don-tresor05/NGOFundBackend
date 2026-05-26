from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.projects.models import BudgetLine, Project
from apps.projects.serializers import BudgetLineSerializer, ProjectSerializer


class ProjectViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Project.objects.select_related("grant")
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.PROJECT_MANAGER, Role.EXECUTIVE_DIRECTOR, Role.DONOR_USER]
    filterset_fields = ["grant", "status"]
    search_fields = ["name", "description", "grant__grant_title"]
    ordering_fields = ["start_date", "end_date", "status", "name"]


class BudgetLineViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = BudgetLine.objects.select_related("grant")
    serializer_class = BudgetLineSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.PROJECT_MANAGER, Role.EXECUTIVE_DIRECTOR]
    filterset_fields = ["grant"]
    search_fields = ["line_name", "grant__grant_title"]
    ordering_fields = ["allocated_amount", "spent_amount", "line_name"]
