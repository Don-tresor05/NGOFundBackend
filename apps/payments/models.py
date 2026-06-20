from django.db import models


class StripeCheckoutSession(models.Model):
    """Track Stripe checkout sessions for donations"""
    session_id = models.CharField(max_length=255, unique=True)
    donor = models.ForeignKey("donors.Donor", on_delete=models.CASCADE, related_name="checkout_sessions")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    project = models.ForeignKey("projects.Project", on_delete=models.SET_NULL, null=True, blank=True)
    donation_type = models.CharField(max_length=20, default="one-time")  # one-time, recurring
    frequency = models.CharField(max_length=20, blank=True)  # monthly, quarterly, annually
    status = models.CharField(max_length=50, default="pending")
    transaction = models.ForeignKey("finance.Transaction", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "stripe_checkout_sessions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.session_id} - {self.amount} {self.currency}"


class StripeSubscription(models.Model):
    """Track Stripe subscriptions for recurring donations"""
    subscription_id = models.CharField(max_length=255, unique=True)
    donor = models.ForeignKey("donors.Donor", on_delete=models.CASCADE, related_name="subscriptions")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    project = models.ForeignKey("projects.Project", on_delete=models.SET_NULL, null=True, blank=True)
    frequency = models.CharField(max_length=20)  # monthly, quarterly, annually
    status = models.CharField(max_length=50, default="active")  # active, canceled, paused
    start_date = models.DateField()
    next_payment_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "stripe_subscriptions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subscription_id} - {self.amount} {self.currency}/{self.frequency}"
