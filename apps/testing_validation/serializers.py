from rest_framework import serializers

from apps.testing_validation.models import BugReport, ReleaseNote, TestCase, UATFeedback


class TestCaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestCase
        fields = "__all__"
        read_only_fields = ["created_by", "created_at"]

    def validate(self, attrs):
        status = attrs.get("status", getattr(self.instance, "status", TestCase.Status.TODO))
        current_status = getattr(self.instance, "status", TestCase.Status.TODO)
        allowed_transitions = {
            TestCase.Status.TODO: {
                TestCase.Status.TODO,
                TestCase.Status.IN_PROGRESS,
                TestCase.Status.IN_REVIEW,
            },
            TestCase.Status.IN_PROGRESS: {
                TestCase.Status.IN_PROGRESS,
                TestCase.Status.IN_REVIEW,
                TestCase.Status.APPROVED,
                TestCase.Status.REJECTED,
            },
            TestCase.Status.IN_REVIEW: {
                TestCase.Status.IN_REVIEW,
                TestCase.Status.APPROVED,
                TestCase.Status.REJECTED,
            },
            TestCase.Status.APPROVED: {TestCase.Status.APPROVED},
            TestCase.Status.REJECTED: {TestCase.Status.REJECTED},
        }
        if status not in allowed_transitions[current_status]:
            raise serializers.ValidationError("Invalid test case status transition.")
        return attrs


class UATFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = UATFeedback
        fields = "__all__"
        read_only_fields = ["submitted_by", "created_at"]

    def validate(self, attrs):
        status = attrs.get("status", getattr(self.instance, "status", UATFeedback.Status.OPEN))
        current_status = getattr(self.instance, "status", UATFeedback.Status.OPEN)
        allowed_transitions = {
            UATFeedback.Status.OPEN: {
                UATFeedback.Status.OPEN,
                UATFeedback.Status.IN_REVIEW,
                UATFeedback.Status.RESOLVED,
                UATFeedback.Status.CLOSED,
            },
            UATFeedback.Status.IN_REVIEW: {
                UATFeedback.Status.IN_REVIEW,
                UATFeedback.Status.RESOLVED,
                UATFeedback.Status.CLOSED,
            },
            UATFeedback.Status.RESOLVED: {UATFeedback.Status.CLOSED, UATFeedback.Status.RESOLVED},
            UATFeedback.Status.CLOSED: {UATFeedback.Status.CLOSED},
        }
        if status not in allowed_transitions[current_status]:
            raise serializers.ValidationError("Invalid UAT feedback status transition.")
        return attrs


class BugReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = BugReport
        fields = "__all__"
        read_only_fields = ["reported_by", "assigned_to", "resolved_at", "created_at"]


class ReleaseNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReleaseNote
        fields = "__all__"
        read_only_fields = ["created_by", "published_by", "published_at", "created_at"]
