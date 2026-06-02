from django.contrib import admin

from apps.requisitions.models import Requisition, RequisitionItem

admin.site.register(Requisition)
admin.site.register(RequisitionItem)
