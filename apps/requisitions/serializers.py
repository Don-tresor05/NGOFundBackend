from rest_framework import serializers

from apps.requisitions.models import Requisition, RequisitionItem


class RequisitionSerializer(serializers.ModelSerializer):
    submitted_by_name = serializers.SerializerMethodField()
    budget_line_name = serializers.SerializerMethodField()

    class Meta:
        model = Requisition
        fields = "__all__"
        read_only_fields = ["submitted_by", "created_at"]

    def get_submitted_by_name(self, obj):
        return obj.submitted_by.full_name if obj.submitted_by_id else "—"

    def get_budget_line_name(self, obj):
        return obj.budget_line.line_name if obj.budget_line_id else "—"

    def validate(self, attrs):
        budget_line = attrs.get("budget_line", getattr(self.instance, "budget_line", None))
        amount = attrs.get("amount", getattr(self.instance, "amount", None))
        if budget_line and amount and amount > budget_line.remaining_amount:
            raise serializers.ValidationError("Requisition amount exceeds the remaining budget line balance.")
        return attrs


class RequisitionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = RequisitionItem
        fields = "__all__"
        read_only_fields = ["line_total"]
