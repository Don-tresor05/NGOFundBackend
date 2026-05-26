from rest_framework import serializers

from apps.testing_validation.models import TestCase, UATFeedback


class TestCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestCase
        fields = "__all__"
        read_only_fields = ["created_by", "created_at"]


class UATFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = UATFeedback
        fields = "__all__"
        read_only_fields = ["submitted_by", "created_at"]
