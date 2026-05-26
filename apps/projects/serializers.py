from rest_framework import serializers

from apps.projects.models import BudgetLine, Project


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
