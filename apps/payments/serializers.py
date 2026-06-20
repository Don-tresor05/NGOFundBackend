from rest_framework import serializers
from apps.payments.models import StripeCheckoutSession, StripeSubscription


class CreateCheckoutSessionSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    donation_type = serializers.ChoiceField(choices=["one-time", "recurring"], default="one-time")
    frequency = serializers.ChoiceField(choices=["monthly", "quarterly", "annually"], required=False)
    donor_id = serializers.IntegerField()


class StripeCheckoutSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StripeCheckoutSession
        fields = "__all__"


class StripeSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StripeSubscription
        fields = "__all__"
