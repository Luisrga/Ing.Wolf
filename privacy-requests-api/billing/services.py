import stripe
from django.conf import settings
from django.contrib.auth import get_user_model

from .models import Subscription


class BillingNotConfigured(Exception):
    pass


def has_active_subscription(user) -> bool:
    return Subscription.objects.filter(user=user, status__in=Subscription.ACTIVE_STATUSES).exists()


def create_checkout_session(user) -> str:
    """Create a Stripe Checkout Session (subscription mode) and return its URL."""
    if not (settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_ID):
        raise BillingNotConfigured("Stripe is not configured.")

    stripe.api_key = settings.STRIPE_SECRET_KEY
    params = {
        "mode": "subscription",
        "line_items": [{"price": settings.STRIPE_PRICE_ID, "quantity": 1}],
        "client_reference_id": str(user.pk),
        "success_url": f"{settings.SITE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{settings.SITE_URL}/billing/cancel",
    }
    existing = Subscription.objects.filter(user=user).exclude(stripe_customer_id="").first()
    if existing:
        params["customer"] = existing.stripe_customer_id
    elif user.email:
        params["customer_email"] = user.email

    session = stripe.checkout.Session.create(**params)
    return session.url


def handle_event(event) -> None:
    """Apply a verified Stripe event to our database."""
    kind = event["type"]
    obj = event["data"]["object"]

    if kind == "checkout.session.completed":
        user_id = obj.get("client_reference_id")
        user = get_user_model().objects.filter(pk=user_id).first() if user_id else None
        if user is None:
            return
        Subscription.objects.update_or_create(
            user=user,
            defaults={
                "stripe_customer_id": obj.get("customer") or "",
                "stripe_subscription_id": obj.get("subscription") or "",
                "status": "active",
            },
        )
    elif kind in ("customer.subscription.updated", "customer.subscription.deleted"):
        status = "canceled" if kind.endswith("deleted") else obj.get("status", "inactive")
        Subscription.objects.filter(stripe_subscription_id=obj.get("id")).update(status=status)
