from django.contrib import admin

from apps.projects.models import BudgetLine, Project

admin.site.register(Project)
admin.site.register(BudgetLine)
