from apps.audit.models import AuditLog


class AuditLogMixin:
    audit_create_action = "CREATED"
    audit_update_action = "UPDATED"
    audit_delete_action = "DELETED"

    def _client_ip(self):
        forwarded_for = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return self.request.META.get("REMOTE_ADDR")

    def _write_audit_log(self, action_type, instance):
        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            return

        AuditLog.objects.create(
            user=user,
            action_type=action_type,
            target_entity_id=instance.pk,
            target_entity_type=instance._meta.model_name,
            ip_address=self._client_ip(),
            details=f"{action_type} {instance._meta.verbose_name} through API.",
        )

    def perform_create(self, serializer):
        instance = serializer.save()
        self._write_audit_log(self.audit_create_action, instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self._write_audit_log(self.audit_update_action, instance)

    def perform_destroy(self, instance):
        self._write_audit_log(self.audit_delete_action, instance)
        instance.delete()
