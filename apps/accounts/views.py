from django.contrib.auth import get_user_model
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Notification, Role, SystemSetting
from apps.accounts.permissions import IsSuperAdmin, RoleBasedPermission
from apps.accounts.serializers import (
    LoginSerializer,
    NotificationSerializer,
    RegisterSerializer,
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
    queryset = User.objects.order_by("-created_at")
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN]
    search_fields = ["full_name", "email", "role"]
    ordering_fields = ["created_at", "full_name", "email", "role"]


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
        if self.request.user.role == Role.SUPER_ADMIN:
            return Notification.objects.all()
        return Notification.objects.filter(user=self.request.user)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        self.get_queryset().update(is_read=True)
        return Response(status=status.HTTP_204_NO_CONTENT)
