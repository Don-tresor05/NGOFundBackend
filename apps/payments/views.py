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
from decimal import Decimal

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_donor_donations(request):
    """Get donation history for a donor"""
    donor_id = request.query_params.get("donor_id")
    
    if not donor_id:
        return Response({"error": "donor_id required"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        donations = StripeCheckoutSession.objects.filter(
            donor_id=donor_id,
            status="completed"
        ).order_by('-completed_at')
        
        total_amount = sum(d.amount for d in donations)
        
        return Response({
            "total_donations": float(total_amount),
            "donation_count": donations.count(),
            "donations": [{
                "id": d.id,
                "amount": float(d.amount),
                "date": d.completed_at,
                "project": d.project.name if d.project else "General Fund",
                "reference": d.session_id,
                "donation_type": d.donation_type
            } for d in donations]
        })
        
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def check_payment_status(request):
    """Check and process payment after redirect from Stripe"""
    session_id = request.query_params.get("session_id")
    
    if not session_id:
        return Response({"error": "Session ID required"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Retrieve session from Stripe
        stripe_session = stripe.checkout.Session.retrieve(session_id)
        
        # Get local record
        checkout_session = StripeCheckoutSession.objects.get(session_id=session_id)
        
        # If payment succeeded and not already processed
        if stripe_session.payment_status == "paid" and checkout_session.status == "pending":
            handle_checkout_completed(stripe_session)
            
        return Response({
            "status": checkout_session.status,
            "amount": str(checkout_session.amount),
            "transaction_id": checkout_session.transaction.id if checkout_session.transaction else None
        })
        
    except StripeCheckoutSession.DoesNotExist:
        return Response({"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
            "success_url": f"{settings.FRONTEND_BASE_URL}/app/donor-portal?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{settings.FRONTEND_BASE_URL}/app/donor-portal?payment=canceled",
            "client_reference_id": str(donor.id),
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
        
        print(f"DEBUG: Stripe session created")
        print(f"DEBUG: session.id = {session.id}")
        print(f"DEBUG: session.url = {session.url}")
        
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
        
        response_data = {
            "session_id": session.id,
            "checkout_url": session.url
        }
        print(f"DEBUG: Response data = {response_data}")
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
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
    
    # Handle payment failed
    elif event["type"] == "checkout.session.expired" or event["type"] == "payment_intent.payment_failed":
        session = event["data"]["object"]
        handle_checkout_failed(session, event["type"])
    
    # Handle invoice paid (for subscriptions)
    elif event["type"] == "invoice.paid":
        invoice = event["data"]["object"]
        handle_invoice_paid(invoice)
    
    return HttpResponse(status=200)


def handle_checkout_failed(session_data, event_type):
    """Handle failed payment"""
    try:
        from apps.accounts.models import User, Notification
        
        session_id = session_data.get("id")
        checkout_session = StripeCheckoutSession.objects.filter(session_id=session_id).first()
        
        if checkout_session and checkout_session.donor:
            donor = checkout_session.donor
            donor_user = User.objects.filter(email=donor.contact_email).first()
            
            # Create notification for donor user
            if donor_user:
                project_name = checkout_session.project.name if checkout_session.project else "General Fund"
                reason = "expired" if event_type == "checkout.session.expired" else "failed"
                
                Notification.objects.create(
                    user=donor_user,
                    type="payment_failed",
                    title="Payment Not Completed",
                    message=f"Your ${checkout_session.amount} donation to {project_name} was not completed (payment {reason}). Please try again."
                )
            
            # Update checkout session status
            checkout_session.status = "failed"
            checkout_session.save()
    
    except Exception as e:
        print(f"Error handling failed checkout: {e}")


def handle_checkout_completed(session):
    """Process completed checkout and create transaction"""
    try:
        from apps.projects.models import BudgetLine
        from apps.accounts.models import User, Notification
        
        checkout_session = StripeCheckoutSession.objects.get(session_id=session["id"])
        donor = checkout_session.donor
        
        # Get donor user account
        donor_user = User.objects.filter(email=donor.contact_email).first()
        
        # Get or create bank account
        bank_account, _ = BankAccount.objects.get_or_create(
            account_name="Stripe Donations",
            defaults={"account_number": "STRIPE001", "bank_name": "Stripe"}
        )
        
        # Get default budget line
        budget_line = checkout_session.project.budgetline_set.first() if checkout_session.project else BudgetLine.objects.first()
        
        # Get system user for processing
        system_user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        
        # Create transaction
        if budget_line and system_user:
            transaction = Transaction.objects.create(
                transaction_date=timezone.now().date(),
                amount=checkout_session.amount,
                bank_reference_number=session["payment_intent"] or session["id"],
                bank_account=bank_account,
                budget_line=budget_line,
                processed_by=system_user,
                status="cleared",
                currency="USD"
            )
            checkout_session.transaction = transaction
        
        # Update checkout session
        checkout_session.status = "completed"
        checkout_session.completed_at = timezone.now()
        checkout_session.save()
        
        # Create notification for donor user
        if donor_user:
            project_name = checkout_session.project.name if checkout_session.project else "General Fund"
            Notification.objects.create(
                user=donor_user,
                type="payment_success",
                title="Payment Successful",
                message=f"Your ${checkout_session.amount} donation to {project_name} was processed successfully. Thank you for your support!"
            )
        
        # Send acknowledgment email
        send_acknowledgment_email(
            donor=donor,
            amount=checkout_session.amount,
            date=timezone.now(),
            reference=session["payment_intent"] or session["id"],
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
            reference=session["payment_intent"] or session["id"],
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
