from django.db import models


class AuditLog(models.Model):
    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="audit_logs")
    action_type = models.CharField(max_length=100)
    target_entity_id = models.PositiveBigIntegerField()
    target_entity_type = models.CharField(max_length=100)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.action_type} on {self.target_entity_type}:{self.target_entity_id}"


class Document(models.Model):
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="uploaded_documents")
    related_entity_type = models.CharField(max_length=100)
    related_entity_id = models.PositiveBigIntegerField()
    document_type = models.CharField(max_length=80)
    file = models.FileField(upload_to="documents/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return f"{self.document_type} for {self.related_entity_type}:{self.related_entity_id}"
