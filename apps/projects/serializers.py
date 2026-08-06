from rest_framework import serializers

from apps.projects.models import BudgetLine, Project, ProjectMember, ReallocationRequest


class ProjectSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = "__all__"

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get("request")
        url = obj.image.url
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class BudgetLineSerializer(serializers.ModelSerializer):
    remaining_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = BudgetLine
        fields = "__all__"
        read_only_fields = ["remaining_amount"]


class ReallocationRequestSerializer(serializers.ModelSerializer):
    source_budget_line_name = serializers.SerializerMethodField()
    target_budget_line_name = serializers.SerializerMethodField()

    class Meta:
        model = ReallocationRequest
        fields = "__all__"
        read_only_fields = ["requested_by", "reviewed_by", "reviewed_at", "created_at", "status"]

    def get_source_budget_line_name(self, obj):
        return obj.source_budget_line.line_name if obj.source_budget_line_id else "—"

    def get_target_budget_line_name(self, obj):
        return obj.target_budget_line.line_name if obj.target_budget_line_id else "—"

    def validate(self, attrs):
        source = attrs.get("source_budget_line", getattr(self.instance, "source_budget_line", None))
        target = attrs.get("target_budget_line", getattr(self.instance, "target_budget_line", None))
        amount = attrs.get("amount", getattr(self.instance, "amount", None))
        if source and target and source.pk == target.pk:
            raise serializers.ValidationError("Source and target budget lines must be different.")
        if source and amount and amount > source.remaining_amount:
            raise serializers.ValidationError("Reallocation amount exceeds the source budget line balance.")
        return attrs


class ProjectMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMember
        fields = "__all__"
