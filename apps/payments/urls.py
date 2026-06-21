from django.urls import path
from apps.payments import views

urlpatterns = [
    path("create-checkout-session/", views.create_checkout_session, name="create-checkout-session"),
    path("check-payment-status/", views.check_payment_status, name="check-payment-status"),
    path("webhook/stripe/", views.stripe_webhook, name="stripe-webhook"),
]
