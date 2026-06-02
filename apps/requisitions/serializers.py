from rest_framework import serializers

from apps.requisitions.models import Requisition, RequisitionItem


class RequisitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Requisition
        fields = "__all__"
        read_only_fields = ["submitted_by", "created_at"]

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
