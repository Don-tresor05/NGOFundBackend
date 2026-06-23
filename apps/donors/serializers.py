import csv
import io
from rest_framework import serializers

from apps.donors.models import Donor, DonorCommunication


class DonorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Donor
        fields = "__all__"
        read_only_fields = ["created_at"]


class DonorSelfServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Donor
        fields = [
            "organization_name",
            "contact_person",
            "contact_email",
            "country",
            "category",
        ]


class DonorCommunicationSerializer(serializers.ModelSerializer):
    donor = DonorSerializer(read_only=True)
    donor_id = serializers.PrimaryKeyRelatedField(
        queryset=Donor.objects.all(), source='donor', write_only=True
    )
    
    class Meta:
        model = DonorCommunication
        fields = [
            'id', 'donor', 'donor_id', 'created_by', 'channel', 'subject', 
            'message', 'communication_date', 'communication_type', 'reference', 
            'status', 'is_read'
        ]
        read_only_fields = ["created_by", "id"]


class DonorBulkImportSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, value):
        if not value.name.endswith('.csv'):
            raise serializers.ValidationError("Only CSV files are supported.")
        return value

    def create(self, validated_data):
        file = validated_data['file']
        content = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        
        required_cols = {'organization_name', 'contact_email'}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            raise serializers.ValidationError(f"CSV must contain: {', '.join(required_cols)}")
        
        donors = []
        for row in reader:
            if not row.get('organization_name') or not row.get('contact_email'):
                continue
            donors.append(Donor(
                organization_name=row['organization_name'],
                contact_person=row.get('contact_person', ''),
                contact_email=row['contact_email'],
                country=row.get('country', ''),
                category=row.get('category', ''),
                status=row.get('status', 'active'),
                notes=row.get('notes', ''),
            ))
        
        created = Donor.objects.bulk_create(donors, ignore_conflicts=True)
        return {'imported': len(created), 'total_rows': len(donors)}
