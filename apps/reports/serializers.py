from rest_framework import serializers

from apps.reports.models import Report, ReportDelivery, ReportSchedule


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = Report
        fields = "__all__"
        read_only_fields = ["created_at", "generated_by"]


class ReportScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportSchedule
        fields = "__all__"
        read_only_fields = ["created_by", "created_at", "last_run_at"]

    def validate_recipient_emails(self, value):
        recipients = [email.strip() for email in value.split(",") if email.strip()]
        if not recipients:
            raise serializers.ValidationError("At least one recipient email is required.")
        if len(set(recipients)) != len(recipients):
            raise serializers.ValidationError("Recipient emails must be unique.")
        return ", ".join(recipients)


class ReportDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportDelivery
        fields = "__all__"
        read_only_fields = ["created_by", "sent_at", "created_at"]
