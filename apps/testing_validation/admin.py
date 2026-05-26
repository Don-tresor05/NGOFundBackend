from django.contrib import admin

from apps.testing_validation.models import TestCase, UATFeedback

admin.site.register(TestCase)
admin.site.register(UATFeedback)
