from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role_id == Role.SUPER_ADMIN)


class RoleBasedPermission(BasePermission):
    """Checks view.required_permissions, view.allowed_roles, or action-scoped variants when present."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.role_id == Role.SUPER_ADMIN:
            return True

        action_permissions = getattr(view, "action_permissions", {})
        required_permissions = action_permissions.get(
            getattr(view, "action", None),
            getattr(view, "required_permissions", None),
        )
        if required_permissions:
            if isinstance(required_permissions, str):
                required_permissions = [required_permissions]
            return any(request.user.has_permission(permission_key) for permission_key in required_permissions)

        action_roles = getattr(view, "action_roles", {})
        allowed_roles = action_roles.get(getattr(view, "action", None), getattr(view, "allowed_roles", None))
        if allowed_roles is None:
            return True
        return request.user.role_id in allowed_roles
