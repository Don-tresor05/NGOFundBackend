from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, AllowAny

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.grants.models import Grant
from apps.grants.serializers import GrantSerializer


class GrantViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Grant.objects.select_related("donor")
    serializer_class = GrantSerializer
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR, Role.PROJECT_MANAGER]
    required_permissions = ["manage_projects"]
    filterset_fields = ["donor", "status", "currency"]
    search_fields = ["grant_title", "donor__organization_name", "compliance_notes"]
    ordering_fields = ["start_date", "end_date", "total_amount", "status"]
    
    def get_permissions(self):
        """Allow public read access"""
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated(), RoleBasedPermission()]
