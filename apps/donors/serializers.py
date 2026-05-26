from rest_framework import serializers

from apps.donors.models import Donor, DonorCommunication


class DonorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Donor
        fields = "__all__"
        read_only_fields = ["created_at"]


class DonorCommunicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DonorCommunication
        fields = "__all__"
