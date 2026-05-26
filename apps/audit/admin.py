from django.contrib import admin

from apps.audit.models import AuditLog, Document

admin.site.register(AuditLog)
admin.site.register(Document)
