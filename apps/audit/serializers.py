from rest_framework import serializers

from apps.audit.models import AuditLog, Document


class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = AuditLog
        fields = ['id', 'user', 'user_name', 'user_email', 'action_type', 'target_entity_id', 
                  'target_entity_type', 'timestamp', 'ip_address', 'details']
        read_only_fields = ["timestamp"]


class DocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.full_name', read_only=True)

    class Meta:
        model = Document
        fields = "__all__"
        read_only_fields = ["uploaded_by", "uploaded_at"]
