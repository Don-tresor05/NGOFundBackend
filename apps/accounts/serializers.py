from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Notification, Permission, PasswordResetRequest, Role, RolePermission, SignupOtp, SystemSetting

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)
    role = serializers.CharField(source="role_id")

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "full_name",
            "email",
            "password",
            "role",
            "phone",
            "department",
            "location",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"username": {"required": False}}

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        validated_data.setdefault("username", validated_data["email"])
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = "__all__"


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = "__all__"


class RolePermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RolePermission
        fields = "__all__"


class RegisterSerializer(UserSerializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta(UserSerializer.Meta):
        extra_kwargs = {**UserSerializer.Meta.extra_kwargs, "email": {"validators": []}}

    def create(self, validated_data):
        validated_data["is_active"] = False
        return super().create(validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"],
            password=attrs["password"],
        )
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive. Complete OTP verification to continue.")

        refresh = RefreshToken.for_user(user)
        attrs["user"] = user
        attrs["refresh"] = str(refresh)
        attrs["access"] = str(refresh.access_token)
        return attrs


class SystemSettingSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemSetting
        fields = "__all__"
        read_only_fields = ["updated_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"
        read_only_fields = ["created_at"]


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)


class SignupOtpVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(min_length=6, max_length=6)


class SignupOtpResendSerializer(serializers.Serializer):
    email = serializers.EmailField()


class SignupOtpResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    email = serializers.EmailField()
    verification_required = serializers.BooleanField()
    expires_in_minutes = serializers.IntegerField()


class SignupOtpRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignupOtp
        fields = "__all__"
        read_only_fields = ["user", "expires_at", "is_used", "used_at", "created_at"]


class PasswordResetRequestModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = PasswordResetRequest
        fields = "__all__"
        read_only_fields = ["user", "expires_at", "is_used", "used_at", "created_at"]


class NotificationSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    unread = serializers.IntegerField()
    read = serializers.IntegerField()


class SystemSettingSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    groups = serializers.DictField(child=serializers.IntegerField())
    access_timeout_minutes = serializers.IntegerField()


class SystemSettingBulkUpdateItemSerializer(serializers.Serializer):
    setting_key = serializers.CharField()
    label = serializers.CharField(required=False)
    setting_value = serializers.CharField()
    setting_group = serializers.CharField(required=False)
