from rest_framework import serializers

from apps.operations.models import StaffRequirement


class StaffRequirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffRequirement
        fields = "__all__"
        read_only_fields = ["captured_by", "signed_off_by", "signed_off_at", "created_at"]
