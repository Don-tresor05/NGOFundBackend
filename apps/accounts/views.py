from datetime import timedelta
import secrets

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models import Count
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Notification, PasswordResetRequest, Permission, Role, RolePermission, SignupOtp, SystemSetting
from apps.accounts.permissions import IsSuperAdmin, RoleBasedPermission
from apps.accounts.serializers import (
    LoginSerializer,
    NotificationSerializer,
    NotificationSummarySerializer,
    PermissionSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestModelSerializer,
    PasswordResetRequestSerializer,
    SignupOtpResponseSerializer,
    SignupOtpResendSerializer,
    SignupOtpVerifySerializer,
    RegisterSerializer,
    RolePermissionSerializer,
    RoleSerializer,
    SystemSettingSerializer,
    SystemSettingBulkUpdateItemSerializer,
    SystemSettingSummarySerializer,
    UserSerializer,
)

User = get_user_model()


def issue_signup_otp(user):
    otp = f"{secrets.randbelow(900000) + 100000}"
    verification_token = secrets.token_hex(32)
    signup_otp = SignupOtp.objects.create(
        user=user,
        otp=otp,
        verification_token=verification_token,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    verification_link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/verify-account?token={verification_token}"
    send_mail(
        subject="Your NGO Fund Platform verification code",
        message=(
            f"Hello {user.full_name},\n\n"
            "Use the link below to verify your account:\n"
            f"{verification_link}\n\n"
            f"Or enter this verification code manually: {otp}\n"
            "It expires in 15 minutes.\n\n"
            "If you did not request this account, you can ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=not settings.DEBUG,
    )
    return signup_otp


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
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data
        
        # Restrict self-registration to DONOR_USER role only
        role = Role.objects.filter(role_key=validated_data["role"]).first()
        if role and role.role_key != 'DONOR_USER':
            return Response(
                {
                    "detail": "Self-registration is only available for donors. Staff accounts must be created by administrators.",
                    "role_restricted": True,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        
        email = validated_data["email"].lower()

        existing_user = User.objects.filter(email__iexact=email).first()
        if existing_user and existing_user.is_active:
            return Response(
                {
                    "detail": "An active account with this email already exists. Sign in or reset the password instead.",
                    "email": email,
                    "conflict": True,
                },
                status=status.HTTP_409_CONFLICT,
            )

        if existing_user:
            user = existing_user
            user.full_name = validated_data["full_name"]
            user.email = email
            user.username = validated_data.get("username") or email
            user.role_id = validated_data["role_id"]
            user.phone = validated_data.get("phone", "")
            user.department = validated_data.get("department", "")
            user.location = validated_data.get("location", "")
            user.is_active = False
            user.set_password(validated_data["password"])
            user.save()
            user.signup_otps.all().update(is_used=True, used_at=timezone.now())
        else:
            user = serializer.save()
            user.is_active = False
            user.save(update_fields=["is_active"])

        issue_signup_otp(user)
        payload = SignupOtpResponseSerializer(
            {
                "detail": "A verification link and verification code have been sent to the registered email address.",
                "email": user.email,
                "verification_required": True,
                "expires_in_minutes": 15,
            }
        ).data
        return Response(payload, status=status.HTTP_201_CREATED)


class SignupOtpVerifyView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = SignupOtpVerifySerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token_value = serializer.validated_data.get("token")
        if token_value:
            otp_record = (
                SignupOtp.objects.select_related("user")
                .filter(verification_token=token_value, is_used=False, expires_at__gte=timezone.now())
                .first()
            )
            if not otp_record:
                return Response({"detail": "Invalid or expired verification link."}, status=status.HTTP_400_BAD_REQUEST)
            user = otp_record.user
        else:
            email = serializer.validated_data["email"].lower()
            otp_value = serializer.validated_data["otp"]
            user = User.objects.filter(email__iexact=email).first()
            if not user:
                raise ValidationError({"email": "No account is waiting for verification for this email."})

            otp_record = (
                SignupOtp.objects.select_related("user")
                .filter(user=user, otp=otp_value, is_used=False, expires_at__gte=timezone.now())
                .first()
            )
        if not otp_record:
            return Response({"detail": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

        otp_record.is_used = True
        otp_record.used_at = timezone.now()
        otp_record.save(update_fields=["is_used", "used_at"])

        user.is_active = True
        user.save(update_fields=["is_active"])

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "detail": "Account verified successfully.",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            }
        )


class SignupOtpResendView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = SignupOtpResendSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower()

        user = User.objects.filter(email__iexact=email).first()
        if not user or user.is_active:
            return Response(
                {"detail": "If the account is pending verification, a new verification code has been issued."},
                status=status.HTTP_200_OK,
            )

        user.signup_otps.all().update(is_used=True, used_at=timezone.now())
        issue_signup_otp(user)
        return Response({"detail": "If the account is pending verification, a new verification code has been issued."}, status=status.HTTP_200_OK)


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
    required_permissions = ["manage_users"]
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
        email = serializer.validated_data["email"]
        user = User.objects.filter(email=email).first()
        if user:
            reset_request = PasswordResetRequest.objects.create(
                user=user,
                token=secrets.token_hex(32),
                expires_at=timezone.now() + timedelta(hours=2),
            )
            payload = {"detail": "If the account exists, a password reset token has been issued."}
            if settings.DEBUG:
                payload["token"] = reset_request.token
            return Response(payload, status=status.HTTP_200_OK)
        return Response({"detail": "If the account exists, a password reset token has been issued."}, status=status.HTTP_200_OK)

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
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN]
    required_permissions = ["manage_settings"]
    search_fields = ["setting_key", "label", "setting_group"]

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        qs = self.get_queryset()
        groups = {
            row["setting_group"]: row["total"]
            for row in qs.values("setting_group").annotate(total=Count("id")).order_by("setting_group")
        }
        access_timeout = qs.filter(setting_key="session_timeout_minutes").first()
        return Response(
            SystemSettingSummarySerializer(
                {
                    "total": qs.count(),
                    "groups": groups,
                    "access_timeout_minutes": int(access_timeout.setting_value) if access_timeout else 60,
                }
            ).data
        )

    @action(detail=False, methods=["post"], url_path="bulk-update")
    def bulk_update(self, request):
        serializer = SystemSettingBulkUpdateItemSerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        updated = []
        for item in serializer.validated_data:
            obj, _ = SystemSetting.objects.update_or_create(
                setting_key=item["setting_key"],
                defaults={
                    "label": item.get("label", item["setting_key"].replace("_", " ").title()),
                    "setting_value": item["setting_value"],
                    "setting_group": item.get("setting_group", SystemSetting.SettingGroup.ACCESS),
                    "updated_by": request.user,
                },
            )
            updated.append(obj)
        return Response(self.get_serializer(updated, many=True).data)


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

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(self.get_serializer(notification).data)

    @action(detail=True, methods=["post"], url_path="mark-unread")
    def mark_unread(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = False
        notification.save(update_fields=["is_read"])
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request):
        qs = self.get_queryset()
        return Response(
            NotificationSummarySerializer(
                {
                    "total": qs.count(),
                    "unread": qs.filter(is_read=False).count(),
                    "read": qs.filter(is_read=True).count(),
                }
            ).data
        )


class RoleViewSet(viewsets.ModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN]
    required_permissions = ["manage_roles"]
    search_fields = ["role_key", "role_name"]
    ordering_fields = ["role_key", "role_name", "is_active"]


class PermissionViewSet(viewsets.ModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN]
    required_permissions = ["manage_permissions"]
    search_fields = ["permission_key", "permission_name"]
    ordering_fields = ["permission_key", "permission_name"]


class RolePermissionViewSet(viewsets.ModelViewSet):
    queryset = RolePermission.objects.select_related("role", "permission")
    serializer_class = RolePermissionSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN]
    required_permissions = ["manage_permissions"]
    search_fields = ["role__role_name", "permission__permission_name"]
    ordering_fields = ["granted_at", "role__role_name", "permission__permission_name"]
