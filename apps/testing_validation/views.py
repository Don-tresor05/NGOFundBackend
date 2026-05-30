from rest_framework import viewsets
from rest_framework.decorators import action
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.testing_validation.models import BugReport, ReleaseNote, TestCase, UATFeedback
from apps.testing_validation.serializers import BugReportSerializer, ReleaseNoteSerializer, TestCaseSerializer, UATFeedbackSerializer


class TestCaseViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = TestCase.objects.select_related("created_by")
    serializer_class = TestCaseSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN, Role.EXTERNAL_AUDITOR, Role.EXECUTIVE_DIRECTOR]
    filterset_fields = ["created_by", "environment", "status", "priority"]
    search_fields = ["title", "scenario", "environment"]
    ordering_fields = ["created_at", "status", "priority"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, pk=None):
        test_case = self.get_object()
        test_case.status = TestCase.Status.IN_PROGRESS
        test_case.save(update_fields=["status"])
        self._write_audit_log("TEST_CASE_STARTED", test_case)
        return Response(self.get_serializer(test_case).data)

    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, pk=None):
        test_case = self.get_object()
        test_case.status = TestCase.Status.IN_REVIEW
        test_case.save(update_fields=["status"])
        self._write_audit_log("TEST_CASE_REVIEWED", test_case)
        return Response(self.get_serializer(test_case).data)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request, pk=None):
        test_case = self.get_object()
        test_case.status = TestCase.Status.APPROVED
        test_case.save(update_fields=["status"])
        self._write_audit_log("TEST_CASE_APPROVED", test_case)
        return Response(self.get_serializer(test_case).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request, pk=None):
        test_case = self.get_object()
        test_case.status = TestCase.Status.REJECTED
        test_case.save(update_fields=["status"])
        self._write_audit_log("TEST_CASE_REJECTED", test_case)
        return Response(self.get_serializer(test_case).data)


class UATFeedbackViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = UATFeedback.objects.select_related("test_case", "submitted_by")
    serializer_class = UATFeedbackSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN, Role.EXTERNAL_AUDITOR, Role.EXECUTIVE_DIRECTOR]
    filterset_fields = ["test_case", "submitted_by", "status"]
    search_fields = ["feedback", "test_case__title"]
    ordering_fields = ["created_at", "status"]

    def perform_create(self, serializer):
        instance = serializer.save(submitted_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        feedback = self.get_object()
        feedback.status = UATFeedback.Status.RESOLVED
        feedback.save(update_fields=["status"])
        self._write_audit_log("UAT_FEEDBACK_RESOLVED", feedback)
        return Response(self.get_serializer(feedback).data)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        feedback = self.get_object()
        feedback.status = UATFeedback.Status.CLOSED
        feedback.save(update_fields=["status"])
        self._write_audit_log("UAT_FEEDBACK_CLOSED", feedback)
        return Response(self.get_serializer(feedback).data)


class BugReportViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = BugReport.objects.select_related("reported_by", "assigned_to")
    serializer_class = BugReportSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN, Role.EXTERNAL_AUDITOR, Role.EXECUTIVE_DIRECTOR, Role.PROJECT_MANAGER]
    filterset_fields = ["reported_by", "assigned_to", "status", "severity", "environment"]
    search_fields = ["title", "description", "reproduction_steps", "environment"]
    ordering_fields = ["created_at", "resolved_at", "status", "severity"]

    def perform_create(self, serializer):
        instance = serializer.save(reported_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="triage")
    def triage(self, request, pk=None):
        bug = self.get_object()
        bug.status = BugReport.Status.TRIAGED
        bug.assigned_to = request.user
        bug.save(update_fields=["status", "assigned_to"])
        self._write_audit_log("BUG_TRIAGED", bug)
        return Response(self.get_serializer(bug).data)

    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, pk=None):
        bug = self.get_object()
        bug.status = BugReport.Status.IN_PROGRESS
        bug.assigned_to = request.user
        bug.save(update_fields=["status", "assigned_to"])
        self._write_audit_log("BUG_STARTED", bug)
        return Response(self.get_serializer(bug).data)

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        bug = self.get_object()
        bug.status = BugReport.Status.RESOLVED
        bug.assigned_to = request.user
        bug.resolved_at = timezone.now()
        bug.save(update_fields=["status", "assigned_to", "resolved_at"])
        self._write_audit_log("BUG_RESOLVED", bug)
        return Response(self.get_serializer(bug).data)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        bug = self.get_object()
        bug.status = BugReport.Status.CLOSED
        bug.resolved_at = bug.resolved_at or timezone.now()
        bug.save(update_fields=["status", "resolved_at"])
        self._write_audit_log("BUG_CLOSED", bug)
        return Response(self.get_serializer(bug).data)


class ReleaseNoteViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = ReleaseNote.objects.select_related("created_by", "published_by")
    serializer_class = ReleaseNoteSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.SUPER_ADMIN, Role.EXECUTIVE_DIRECTOR, Role.EXTERNAL_AUDITOR]
    filterset_fields = ["created_by", "published_by", "status", "environment", "version"]
    search_fields = ["title", "summary", "changelog", "version"]
    ordering_fields = ["created_at", "published_at", "version", "status"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)

    @action(detail=True, methods=["post"], url_path="publish")
    def publish(self, request, pk=None):
        note = self.get_object()
        note.status = ReleaseNote.Status.PUBLISHED
        note.published_by = request.user
        note.published_at = timezone.now()
        note.save(update_fields=["status", "published_by", "published_at"])
        self._write_audit_log("RELEASE_NOTE_PUBLISHED", note)
        return Response(self.get_serializer(note).data)

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, pk=None):
        note = self.get_object()
        note.status = ReleaseNote.Status.ARCHIVED
        note.save(update_fields=["status"])
        self._write_audit_log("RELEASE_NOTE_ARCHIVED", note)
        return Response(self.get_serializer(note).data)
