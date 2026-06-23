import csv
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Count, Max
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import RoleBasedPermission
from apps.audit.mixins import AuditLogMixin
from apps.donors.models import Donor, DonorCommunication
from apps.donors.serializers import (
    DonorCommunicationSerializer,
    DonorSelfServiceSerializer,
    DonorSerializer,
    DonorBulkImportSerializer,
)


class DonorViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = Donor.objects.all()
    serializer_class = DonorSerializer
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR, Role.DONOR_USER]
    required_permissions = ["manage_donors"]
    filterset_fields = ["status", "category", "country"]
    search_fields = ["organization_name", "contact_person", "contact_email", "category"]
    ordering_fields = ["organization_name", "created_at", "status"]
    
    def get_permissions(self):
        """Allow public read access"""
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated(), RoleBasedPermission()]

    def _linked_donor(self, user):
        normalized_email = user.email.strip().lower()
        normalized_name = user.full_name.strip().lower()
        return (
            Donor.objects.filter(contact_email__iexact=normalized_email).first()
            or Donor.objects.filter(contact_person__iexact=normalized_name).first()
        )

    @action(detail=False, methods=["get"], url_path="engagement-dashboard")
    def engagement_dashboard(self, request):
        donors = self.get_queryset().prefetch_related("communications")
        donor_rows = []
        total_communications = 0
        channel_totals = {}
        for donor in donors:
            communications = donor.communications.order_by("-communication_date")
            count = communications.count()
            total_communications += count
            for channel in communications.values_list("channel", flat=True):
                channel_totals[channel] = channel_totals.get(channel, 0) + 1
            donor_rows.append(
                {
                    "donor_id": donor.pk,
                    "organization_name": donor.organization_name,
                    "status": donor.status,
                    "communication_count": count,
                    "last_contact_date": communications.first().communication_date if count else None,
                    "engagement_score": min(100, count * 20 + (10 if donor.status == Donor.Status.ACTIVE else 0)),
                }
            )
        donor_rows.sort(key=lambda row: (-row["communication_count"], row["organization_name"]))
        return Response(
            {
                "total_donors": donors.count(),
                "active_donors": donors.filter(status=Donor.Status.ACTIVE).count(),
                "inactive_donors": donors.filter(status=Donor.Status.INACTIVE).count(),
                "total_communications": total_communications,
                "channel_totals": channel_totals,
                "top_donors": donor_rows[:5],
            }
        )

    @action(detail=True, methods=["get"], url_path="engagement-summary")
    def engagement_summary(self, request, pk=None):
        donor = self.get_object()
        communications = donor.communications.order_by("-communication_date")
        last_contact = communications.first()
        return Response(
            {
                "donor_id": donor.pk,
                "organization_name": donor.organization_name,
                "status": donor.status,
                "communication_count": communications.count(),
                "last_contact_date": last_contact.communication_date if last_contact else None,
                "last_contact_subject": last_contact.subject if last_contact else None,
                "channels": list(communications.values_list("channel", flat=True).distinct()),
                "recent_communications": DonorCommunicationSerializer(communications[:5], many=True).data,
                "engagement_score": min(100, communications.count() * 20 + (10 if donor.status == Donor.Status.ACTIVE else 0)),
                "next_action": "Schedule follow-up" if communications.count() < 3 else "Maintain relationship",
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

    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        donor = self._linked_donor(request.user)
        if not donor:
            return Response({"detail": "No donor profile is linked to this account."}, status=404)

        if request.method == "PATCH":
            serializer = DonorSelfServiceSerializer(instance=donor, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            self._write_audit_log("DONOR_PROFILE_UPDATED", donor)

        return Response(DonorSerializer(donor).data)

    @action(detail=False, methods=["post"], url_path="bulk-import")
    def bulk_import(self, request):
        serializer = DonorBulkImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        self._write_audit_log("DONORS_BULK_IMPORTED", None, extra_data=result)
        return Response(result, status=201)

    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        donors = self.filter_queryset(self.get_queryset())
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="donors_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        
        writer = csv.writer(response)
        writer.writerow(['organization_name', 'contact_person', 'contact_email', 'country', 'category', 'status', 'notes'])
        
        for donor in donors:
            writer.writerow([
                donor.organization_name,
                donor.contact_person,
                donor.contact_email,
                donor.country,
                donor.category,
                donor.status,
                donor.notes,
            ])
        
        return response


class DonorCommunicationViewSet(AuditLogMixin, viewsets.ModelViewSet):
    queryset = DonorCommunication.objects.select_related("donor", "created_by")
    serializer_class = DonorCommunicationSerializer
    permission_classes = [IsAuthenticated, RoleBasedPermission]
    allowed_roles = [Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
    required_permissions = ["manage_donors"]
    filterset_fields = ["donor", "created_by", "channel"]
    search_fields = ["subject", "message", "channel"]
    ordering_fields = ["communication_date"]

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        self._write_audit_log(self.audit_create_action, instance)
        
        # Notify Finance Officers & Executive Directors when donor sends message via portal
        if instance.channel == 'donor_portal':
            from apps.accounts.models import User, Notification, Role as RoleModel
            
            finance_exec_roles = RoleModel.objects.filter(
                role_key__in=[Role.FINANCE_OFFICER, Role.EXECUTIVE_DIRECTOR]
            )
            finance_and_exec = User.objects.filter(role__in=finance_exec_roles)
            
            for user in finance_and_exec:
                Notification.objects.create(
                    user=user,
                    type='donor_message',
                    title='New Donor Message',
                    message=f'{instance.donor.organization_name} sent a message via Donor Portal: "{instance.message[:100]}..."'
                )
        
        # Notify donor users when staff replies
        if instance.channel == 'staff_reply':
            from apps.accounts.models import User, Notification
            
            donor_user = User.objects.filter(email=instance.donor.contact_email).first()
            
            if donor_user:
                Notification.objects.create(
                    user=donor_user,
                    type='staff_reply',
                    title='New Message from Staff',
                    message=f'Staff replied to your message: "{instance.message[:100]}..."'
                )
