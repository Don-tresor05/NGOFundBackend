from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.donors.models import Donor, DonorCommunication
from apps.donors.serializers import DonorCommunicationSerializer, DonorSerializer


class DonorViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Donor.objects.all()
    serializer_class = DonorSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR, Role.DONOR_USER]
    filterset_fields = ["status", "category", "country"]
    search_fields = ["organization_name", "contact_person", "contact_email", "category"]
    ordering_fields = ["organization_name", "created_at", "status"]

    @action(detail=True, methods=["get"], url_path="engagement-summary")
    def engagement_summary(self, request, pk=None):
        donor = self.get_object()
        communications = donor.communications.order_by("-communication_date")
        last_contact = communications.first()
        return Response(
            {
                "donor_id": donor.pk,
                "communication_count": communications.count(),
                "last_contact_date": last_contact.communication_date if last_contact else None,
                "last_contact_subject": last_contact.subject if last_contact else None,
                "channels": list(communications.values_list("channel", flat=True).distinct()),
            }
        )

    @action(detail=True, methods=["post"], url_path="acknowledge")
    def acknowledge(self, request, pk=None):
        donor = self.get_object()
        communication = DonorCommunication.objects.create(
            donor=donor,
            created_by=request.user,
            channel=request.data.get("channel", "email"),
            subject=request.data.get("subject", "Thank you for your support"),
            message=request.data.get(
                "message",
                f"Thank you {donor.contact_person or donor.organization_name} for your continued support.",
            ),
            communication_date=timezone.now(),
        )
        self._write_audit_log("DONOR_ACKNOWLEDGED", donor)
        return Response(DonorCommunicationSerializer(communication).data, status=201)


class DonorCommunicationViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = DonorCommunication.objects.select_related("donor", "created_by")
    serializer_class = DonorCommunicationSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    filterset_fields = ["donor", "created_by", "channel"]
    search_fields = ["subject", "message", "channel"]
    ordering_fields = ["communication_date"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)
