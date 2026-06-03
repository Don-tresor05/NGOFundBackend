from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.Model):
    SUPER_ADMIN = "SUPER_ADMIN"
    FINANCE_OFFICER = "FINANCE_OFFICER"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    EXECUTIVE_DIRECTOR = "EXECUTIVE_DIRECTOR"
    FIELD_STAFF = "FIELD_STAFF"
    EXTERNAL_AUDITOR = "EXTERNAL_AUDITOR"
    DONOR_USER = "DONOR_USER"

    role_key = models.CharField(max_length=40, primary_key=True)
    role_name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["role_name"]
        db_table = "roles"

    def __str__(self) -> str:
        return self.role_name

    def has_permission(self, permission_key: str) -> bool:
        return self.role_permissions.filter(permission__permission_key=permission_key).exists()


class Permission(models.Model):
    permission_key = models.CharField(max_length=80, unique=True)
    permission_name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["permission_name"]
        db_table = "permissions"

    def __str__(self) -> str:
        return self.permission_name


class RolePermission(models.Model):
    role = models.ForeignKey("accounts.Role", on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey("accounts.Permission", on_delete=models.CASCADE, related_name="role_permissions")
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "role_permissions"
        constraints = [
            models.UniqueConstraint(fields=["role", "permission"], name="unique_role_permission")
        ]

    def __str__(self) -> str:
        return f"{self.role.role_name} -> {self.permission.permission_name}"


class User(AbstractUser):
    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    role = models.ForeignKey("accounts.Role", on_delete=models.PROTECT, related_name="users")
    phone = models.CharField(max_length=40, blank=True)
    department = models.CharField(max_length=120, blank=True)
    location = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "full_name", "role"]

    class Meta:
        db_table = "users"

    def __str__(self) -> str:
        return f"{self.full_name} ({self.role_id})"

    @property
    def role_code(self) -> str:
        return self.role_id

    def has_permission(self, permission_key: str) -> bool:
        if self.is_superuser or self.role_id == Role.SUPER_ADMIN:
            return True
        return self.role.has_permission(permission_key)


class SystemSetting(models.Model):
    class SettingGroup(models.TextChoices):
        ACCESS = "access", "Access"
        FINANCE = "finance", "Finance"
        NOTIFICATIONS = "notifications", "Notifications"

    setting_key = models.CharField(max_length=100, unique=True)
    label = models.CharField(max_length=150)
    setting_value = models.CharField(max_length=255)
    setting_group = models.CharField(max_length=40, choices=SettingGroup.choices)
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_settings",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "system_settings"

    def __str__(self) -> str:
        return self.label


class Notification(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=80)
    title = models.CharField(max_length=150)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "notifications"

    def __str__(self) -> str:
        return self.title


class PasswordResetRequest(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="password_reset_requests")
    token = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "password_reset_requests"

    def __str__(self) -> str:
        return f"Password reset for {self.user.email}"
