from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    SUPER_ADMIN = "SUPER_ADMIN", "Super Administrator"
    FINANCE_OFFICER = "FINANCE_OFFICER", "Finance Officer"
    PROJECT_MANAGER = "PROJECT_MANAGER", "Project Manager"
    EXECUTIVE_DIRECTOR = "EXECUTIVE_DIRECTOR", "Executive Director"
    FIELD_STAFF = "FIELD_STAFF", "Field Staff"
    EXTERNAL_AUDITOR = "EXTERNAL_AUDITOR", "External Auditor"
    DONOR_USER = "DONOR_USER", "Donor User"


class User(AbstractUser):
    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=40, choices=Role.choices)
    phone = models.CharField(max_length=40, blank=True)
    department = models.CharField(max_length=120, blank=True)
    location = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "full_name", "role"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.get_role_display()})"


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

    def __str__(self) -> str:
        return self.title
