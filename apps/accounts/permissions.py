from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role_id == Role.SUPER_ADMIN)


class RoleBasedPermission(BasePermission):
    """Checks view.allowed_roles or view.action_roles when present."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.role_id == Role.SUPER_ADMIN:
            return True

        action_roles = getattr(view, "action_roles", {})
        allowed_roles = action_roles.get(getattr(view, "action", None), getattr(view, "allowed_roles", None))
        if allowed_roles is None:
            return True
        return request.user.role_id in allowed_roles
