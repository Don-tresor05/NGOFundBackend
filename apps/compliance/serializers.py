from rest_framework import serializers

from apps.compliance.models import ComplianceItem


class ComplianceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceItem
        fields = "__all__"
        read_only_fields = ["verified_by", "verified_at"]
