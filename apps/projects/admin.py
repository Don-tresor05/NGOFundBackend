from django.contrib import admin

from apps.projects.models import BudgetLine, Project, ProjectMember

admin.site.register(Project)
admin.site.register(BudgetLine)
admin.site.register(ProjectMember)
