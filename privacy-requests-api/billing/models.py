from django.conf import settings
from django.db import models


class Subscription(models.Model):
    ACTIVE_STATUSES = ("active", "trialing")

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscription")
    stripe_customer_id = models.CharField(max_length=64, blank=True)
    stripe_subscription_id = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(max_length=32, default="inactive")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user_id}: {self.status}"


class StripeEvent(models.Model):
    """Every processed webhook event id. Stripe retries deliveries and can send
    the same event twice, so handlers must be idempotent."""

    event_id = models.CharField(max_length=80, unique=True)
    event_type = models.CharField(max_length=80)
    received_at = models.DateTimeField(auto_now_add=True)
