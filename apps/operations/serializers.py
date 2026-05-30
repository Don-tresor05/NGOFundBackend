from rest_framework import serializers

from apps.operations.models import ProcessDocument, StaffRequirement


class StaffRequirementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffRequirement
        fields = "__all__"
        read_only_fields = ["captured_by", "signed_off_by", "signed_off_at", "created_at"]

    def validate(self, attrs):
        validation_status = attrs.get(
            "validation_status",
            getattr(self.instance, "validation_status", StaffRequirement.ValidationStatus.PENDING),
        )
        current_status = getattr(self.instance, "validation_status", StaffRequirement.ValidationStatus.PENDING)
        allowed_transitions = {
            StaffRequirement.ValidationStatus.PENDING: {
                StaffRequirement.ValidationStatus.PENDING,
                StaffRequirement.ValidationStatus.IN_REVIEW,
                StaffRequirement.ValidationStatus.APPROVED,
                StaffRequirement.ValidationStatus.REJECTED,
            },
            StaffRequirement.ValidationStatus.IN_REVIEW: {
                StaffRequirement.ValidationStatus.IN_REVIEW,
                StaffRequirement.ValidationStatus.APPROVED,
                StaffRequirement.ValidationStatus.REJECTED,
            },
            StaffRequirement.ValidationStatus.APPROVED: {
                StaffRequirement.ValidationStatus.APPROVED,
            },
            StaffRequirement.ValidationStatus.REJECTED: {
                StaffRequirement.ValidationStatus.REJECTED,
            },
        }
        if validation_status not in allowed_transitions[current_status]:
            raise serializers.ValidationError("Invalid staff requirement status transition.")

        signed_off_by = attrs.get("signed_off_by", getattr(self.instance, "signed_off_by", None))
        signed_off_at = attrs.get("signed_off_at", getattr(self.instance, "signed_off_at", None))
        if validation_status == StaffRequirement.ValidationStatus.APPROVED and not (signed_off_by and signed_off_at):
            raise serializers.ValidationError("Approved staff requirements must be signed off through the sign-off workflow.")
        if validation_status == StaffRequirement.ValidationStatus.REJECTED and (signed_off_by or signed_off_at):
            raise serializers.ValidationError("Rejected staff requirements cannot carry sign-off metadata.")
        return attrs


class ProcessDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessDocument
        fields = "__all__"
        read_only_fields = ["created_by", "approved_by", "created_at", "updated_at"]
