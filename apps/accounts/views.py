from datetime import timedelta
import secrets

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Notification, PasswordResetRequest, Permission, Role, RolePermission, SystemSetting
from apps.accounts.permissions import IsSuperAdmin, RoleBasedPermission
from apps.accounts.serializers import (
    LoginSerializer,
    NotificationSerializer,
    PermissionSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestModelSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    RolePermissionSerializer,
    RoleSerializer,
    SystemSettingSerializer,
    UserSerializer,
)

User = get_user_model()


class LoginView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        return Response(
            {
                "access": serializer.validated_data["access"],
                "refresh": serializer.validated_data["refresh"],
                "user": UserSerializer(user).data,
            }
        )


class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer
    queryset = User.objects.all()

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        user = User.objects.get(id=response.data["id"])
        login_serializer = LoginSerializer(
            data={"email": user.email, "password": request.data.get("password")},
            context={"request": request},
        )
        login_serializer.is_valid(raise_exception=True)
        response.data["access"] = login_serializer.validated_data["access"]
        response.data["refresh"] = login_serializer.validated_data["refresh"]
        return response


class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related("role").order_by("-created_at")
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN]
    search_fields = ["full_name", "email", "role__role_name", "role_id"]
    ordering_fields = ["created_at", "full_name", "email", "role_id"]

    @action(detail=False, methods=["get"], url_path="security-summary")
    def security_summary(self, request):
        timeout_setting = SystemSetting.objects.filter(setting_key="session_timeout_minutes").first()
        reset_requests = PasswordResetRequest.objects.count()
        inactive_users = User.objects.filter(is_active=False).count()
        return Response(
            {
                "session_timeout_minutes": int(timeout_setting.setting_value) if timeout_setting else 60,
                "password_reset_requests": reset_requests,
                "inactive_users": inactive_users,
            }
        )

    @action(detail=False, methods=["post"], url_path="password-reset-request")
    def password_reset_request(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = User.objects.get(email=serializer.validated_data["email"])
        except User.DoesNotExist:
            return Response({"detail": "No account exists for that email address."}, status=status.HTTP_404_NOT_FOUND)
        reset_request = PasswordResetRequest.objects.create(
            user=user,
            token=secrets.token_hex(32),
            expires_at=timezone.now() + timedelta(hours=2),
        )
        return Response(PasswordResetRequestModelSerializer(reset_request).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="password-reset-confirm")
    def password_reset_confirm(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            reset_request = PasswordResetRequest.objects.select_related("user").get(token=serializer.validated_data["token"])
        except PasswordResetRequest.DoesNotExist:
            return Response({"detail": "Invalid reset token."}, status=status.HTTP_400_BAD_REQUEST)

        if reset_request.is_used or reset_request.expires_at < timezone.now():
            return Response({"detail": "Reset token has expired or already been used."}, status=status.HTTP_400_BAD_REQUEST)

        reset_request.user.set_password(serializer.validated_data["new_password"])
        reset_request.user.save(update_fields=["password"])
        reset_request.is_used = True
        reset_request.used_at = timezone.now()
        reset_request.save(update_fields=["is_used", "used_at"])
        return Response({"detail": "Password updated successfully."})


class SystemSettingViewSet(viewsets.ModelViewSet):
    queryset = SystemSetting.objects.order_by("setting_group", "label")
    serializer_class = SystemSettingSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    search_fields = ["setting_key", "label", "setting_group"]

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.none()
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["title", "message", "type"]
    ordering_fields = ["created_at", "is_read"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Notification.objects.none()
        if self.request.user.role_id == Role.SUPER_ADMIN:
            return Notification.objects.all()
        return Notification.objects.filter(user=self.request.user)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        self.get_queryset().update(is_read=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    search_fields = ["role_key", "role_name"]
    ordering_fields = ["role_key", "role_name", "is_active"]


class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    search_fields = ["permission_key", "permission_name"]
    ordering_fields = ["permission_key", "permission_name"]


class RolePermissionViewSet(viewsets.ModelViewSet):
    queryset = RolePermission.objects.select_related("role", "permission")
    serializer_class = RolePermissionSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    search_fields = ["role__role_name", "permission__permission_name"]
    ordering_fields = ["granted_at", "role__role_name", "permission__permission_name"]
