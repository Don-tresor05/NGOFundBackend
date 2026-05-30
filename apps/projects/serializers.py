from rest_framework import serializers

from apps.projects.models import BudgetLine, Project, ReallocationRequest


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = "__all__"


class BudgetLineSerializer(serializers.ModelSerializer):
    remaining_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = BudgetLine
        fields = "__all__"
        read_only_fields = ["remaining_amount"]


class ReallocationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReallocationRequest
        fields = "__all__"
        read_only_fields = ["requested_by", "reviewed_by", "reviewed_at", "created_at", "status"]

    def validate(self, attrs):
        source = attrs.get("source_budget_line", getattr(self.instance, "source_budget_line", None))
        target = attrs.get("target_budget_line", getattr(self.instance, "target_budget_line", None))
        amount = attrs.get("amount", getattr(self.instance, "amount", None))
        if source and target and source.pk == target.pk:
            raise serializers.ValidationError("Source and target budget lines must be different.")
        if source and amount and amount > source.remaining_amount:
            raise serializers.ValidationError("Reallocation amount exceeds the source budget line balance.")
        return attrs
