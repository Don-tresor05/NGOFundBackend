from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.accounts.models import Notification, Permission, Role, RolePermission, SignupOtp, SystemSetting, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ("email", "full_name", "role", "is_active", "created_at")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "full_name", "username")
    ordering = ("email",)
    fieldsets = UserAdmin.fieldsets + (
        ("NGO Fund Profile", {"fields": ("full_name", "role", "phone", "department", "location")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("NGO Fund Profile", {"fields": ("email", "full_name", "role", "phone", "department", "location")}),
    )


admin.site.register(SystemSetting)
admin.site.register(Notification)
admin.site.register(Role)
admin.site.register(Permission)
admin.site.register(RolePermission)
admin.site.register(SignupOtp)
