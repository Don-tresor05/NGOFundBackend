from django.contrib import admin

from apps.donors.models import Donor, DonorCommunication

admin.site.register(Donor)
admin.site.register(DonorCommunication)
