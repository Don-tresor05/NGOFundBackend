from rest_framework import serializers

from apps.finance.models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = "__all__"
        read_only_fields = ["created_at", "processed_by"]
