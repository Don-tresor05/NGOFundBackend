#!/usr/bin/env python
"""
Create notifications for existing completed payments
Run: python manage.py shell < create_past_payment_notifications.py
"""

from apps.payments.models import StripeCheckoutSession
from apps.accounts.models import User, Notification

# Get all completed payments that don't have notifications yet
completed_payments = StripeCheckoutSession.objects.filter(status='completed')

created_count = 0

for payment in completed_payments:
    donor = payment.donor
    if not donor:
        continue
    
    # Find donor's user account
    donor_user = User.objects.filter(email=donor.contact_email).first()
    
    if donor_user:
        # Check if notification already exists
        existing = Notification.objects.filter(
            user=donor_user,
            type='payment_success',
            message__contains=str(payment.amount)
        ).exists()
        
        if not existing:
            project_name = payment.project.name if payment.project else "General Fund"
            
            Notification.objects.create(
                user=donor_user,
                type='payment_success',
                title='Payment Successful',
                message=f'Your ${payment.amount} donation to {project_name} was processed successfully. Thank you for your support!',
                created_at=payment.completed_at or payment.created_at
            )
            created_count += 1
            print(f"✓ Created notification for ${payment.amount} donation to {project_name}")

print(f"\n✅ Created {created_count} notifications for past payments")
