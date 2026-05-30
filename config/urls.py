from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import (
    LoginView,
    NotificationViewSet,
    ProfileView,
    RegisterView,
    SystemSettingViewSet,
    UserViewSet,
)
from apps.audit.views import AuditLogViewSet, DocumentViewSet
from apps.compliance.views import ComplianceItemViewSet
from apps.donors.views import DonorCommunicationViewSet, DonorViewSet
from apps.finance.views import ExpenseApprovalViewSet, TransactionViewSet
from apps.grants.views import GrantViewSet
from apps.operations.views import ProcessDocumentViewSet, StaffRequirementViewSet
from apps.projects.views import BudgetLineViewSet, ProjectViewSet, ReallocationRequestViewSet
from apps.reports.views import ReportScheduleViewSet, ReportViewSet
from apps.requisitions.views import RequisitionViewSet
from apps.testing_validation.views import BugReportViewSet, ReleaseNoteViewSet, TestCaseViewSet, UATFeedbackViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="users")
router.register("system-settings", SystemSettingViewSet, basename="system-settings")
router.register("notifications", NotificationViewSet, basename="notifications")
router.register("donors", DonorViewSet, basename="donors")
router.register("donor-communications", DonorCommunicationViewSet, basename="donor-communications")
router.register("grants", GrantViewSet, basename="grants")
router.register("projects", ProjectViewSet, basename="projects")
router.register("budget-lines", BudgetLineViewSet, basename="budget-lines")
router.register("reallocation-requests", ReallocationRequestViewSet, basename="reallocation-requests")
router.register("requisitions", RequisitionViewSet, basename="requisitions")
router.register("expense-approvals", ExpenseApprovalViewSet, basename="expense-approvals")
router.register("transactions", TransactionViewSet, basename="transactions")
router.register("reports", ReportViewSet, basename="reports")
router.register("report-schedules", ReportScheduleViewSet, basename="report-schedules")
router.register("audit-logs", AuditLogViewSet, basename="audit-logs")
router.register("documents", DocumentViewSet, basename="documents")
router.register("compliance-items", ComplianceItemViewSet, basename="compliance-items")
router.register("staff-requirements", StaffRequirementViewSet, basename="staff-requirements")
router.register("process-documents", ProcessDocumentViewSet, basename="process-documents")
router.register("test-cases", TestCaseViewSet, basename="test-cases")
router.register("uat-feedback", UATFeedbackViewSet, basename="uat-feedback")
router.register("bug-reports", BugReportViewSet, basename="bug-reports")
router.register("release-notes", ReleaseNoteViewSet, basename="release-notes")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/login/", LoginView.as_view(), name="login"),
    path("api/auth/register/", RegisterView.as_view(), name="register"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/profile/", ProfileView.as_view(), name="profile"),
    path("api/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
