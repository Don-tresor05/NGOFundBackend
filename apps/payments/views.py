import stripe
from datetime import datetime
from decimal import Decimal
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.donors.models import Donor, DonorCommunication
from apps.projects.models import Project
from apps.finance.models import Transaction, BankAccount
from apps.payments.models import StripeCheckoutSession
from apps.payments.serializers import CreateCheckoutSessionSerializer

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_checkout_session(request):
    """Create Stripe Checkout Session for donation"""
    serializer = CreateCheckoutSessionSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    data = serializer.validated_data
    
    try:
        donor = Donor.objects.get(id=data["donor_id"])
        project = None
        if data.get("project_id"):
            project = Project.objects.get(id=data["project_id"])
        
        # Create Stripe Checkout Session
        session_params = {
            "payment_method_types": ["card"],
            "line_items": [
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"Donation to {project.name if project else 'General Fund'}",
                            "description": f"Thank you for supporting our mission",
                        },
                        "unit_amount": int(data["amount"] * 100),  # Convert to cents
                    },
                    "quantity": 1,
                }
            ],
            "mode": "subscription" if data["donation_type"] == "recurring" else "payment",
            "success_url": f"{settings.FRONTEND_BASE_URL}/app/donor-portal?payment=success",
            "cancel_url": f"{settings.FRONTEND_BASE_URL}/app/donor-portal?payment=canceled",
            "client_reference_id": str(donor.donor_id),
            "customer_email": donor.contact_email,
        }
        
        # Add recurring interval if needed
        if data["donation_type"] == "recurring":
            interval_map = {"monthly": "month", "quarterly": "month", "annually": "year"}
            session_params["line_items"][0]["price_data"]["recurring"] = {
                "interval": interval_map.get(data.get("frequency", "monthly")),
                "interval_count": 3 if data.get("frequency") == "quarterly" else 1
            }
        
        session = stripe.checkout.Session.create(**session_params)
        
        # Save checkout session to database
        checkout_session = StripeCheckoutSession.objects.create(
            session_id=session.id,
            donor=donor,
            amount=data["amount"],
            project=project,
            donation_type=data["donation_type"],
            frequency=data.get("frequency", ""),
            status="pending"
        )
        
        return Response({
            "session_id": session.id,
            "url": session.url
        }, status=status.HTTP_201_CREATED)
        
    except Donor.DoesNotExist:
        return Response({"error": "Donor not found"}, status=status.HTTP_404_NOT_FOUND)
    except Project.DoesNotExist:
        return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
@api_view(["POST"])
def stripe_webhook(request):
    """Handle Stripe webhooks for payment events"""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        return HttpResponse(status=400)
    
    # Handle checkout session completed
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        handle_checkout_completed(session)
    
    # Handle invoice paid (for subscriptions)
    elif event["type"] == "invoice.paid":
        invoice = event["data"]["object"]
        handle_invoice_paid(invoice)
    
    return HttpResponse(status=200)


def handle_checkout_completed(session):
    """Process completed checkout and create transaction"""
    try:
        checkout_session = StripeCheckoutSession.objects.get(session_id=session["id"])
        donor = checkout_session.donor
        
        # Get or create bank account for donations
        bank_account, _ = BankAccount.objects.get_or_create(
            account_name="Stripe Donations",
            defaults={
                "account_number": "STRIPE001",
                "bank_name": "Stripe",
                "balance": Decimal("0.00")
            }
        )
        
        # Create transaction record
        transaction = Transaction.objects.create(
            transaction_date=timezone.now().date(),
            amount=checkout_session.amount,
            transaction_type="receipt",
            description=f"Donation from {donor.organization_name}",
            bank_reference_number=session["payment_intent"] or session["id"],
            bank_account=bank_account,
            budget_line=checkout_session.project.budgetline_set.first() if checkout_session.project else None,
            status="cleared"
        )
        
        # Update checkout session
        checkout_session.transaction = transaction
        checkout_session.status = "completed"
        checkout_session.completed_at = timezone.now()
        checkout_session.save()
        
        # Send acknowledgment email
        send_acknowledgment_email(
            donor=donor,
            amount=checkout_session.amount,
            date=timezone.now(),
            reference=transaction.bank_reference_number,
            project=checkout_session.project
        )
        
        # Create communication record
        DonorCommunication.objects.create(
            donor=donor,
            channel="email",
            subject="Thank You for Your Donation",
            message=f"Automated acknowledgment for ${checkout_session.amount} donation",
            communication_date=timezone.now(),
            communication_type="acknowledgment",
            reference=transaction.bank_reference_number,
            status="sent"
        )
        
    except StripeCheckoutSession.DoesNotExist:
        pass


def handle_invoice_paid(invoice):
    """Handle recurring subscription payments"""
    # Implementation for recurring donations
    pass


def send_acknowledgment_email(donor, amount, date, reference, project=None):
    """Send thank you email to donor"""
    try:
        subject = f"Thank You for Your ${amount} Donation"
        
        context = {
            "donor_name": donor.organization_name,
            "amount": amount,
            "date": date.strftime("%B %d, %Y"),
            "reference": reference,
            "project_name": project.name if project else None,
            "organization_name": "Rwanda Paediatric Association"
        }
        
        # Render email template
        html_message = f"""
        <html>
        <body>
            <h2>Thank You for Your Donation</h2>
            <p>Dear {context['donor_name']},</p>
            
            <p>Thank you for your generous donation of <strong>${context['amount']}</strong> on {context['date']}.</p>
            
            {'<p>Your contribution to <strong>' + context['project_name'] + '</strong> is making a real difference.</p>' if context['project_name'] else '<p>Your contribution is making a real difference in our mission.</p>'}
            
            <h3>Donation Details:</h3>
            <ul>
                <li>Amount: ${context['amount']}</li>
                <li>Date: {context['date']}</li>
                <li>Reference: {context['reference']}</li>
                {'<li>Project: ' + context['project_name'] + '</li>' if context['project_name'] else ''}
            </ul>
            
            <p>A receipt has been sent to your email for tax purposes.</p>
            
            <p>With gratitude,<br>{context['organization_name']}</p>
            
            <hr>
            <p style="font-size: 12px; color: gray;">This is an automated acknowledgment. Please do not reply to this email.</p>
        </body>
        </html>
        """
        
        # Send email
        email = EmailMessage(
            subject=subject,
            body=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[donor.contact_email]
        )
        email.content_subtype = "html"
        email.send()
        
        return True
    except Exception as e:
        print(f"Error sending acknowledgment email: {e}")
        return False
