import json

import stripe
from django.conf import settings
from django.db import IntegrityError, transaction
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import StripeEvent
from .services import BillingNotConfigured, create_checkout_session, handle_event, has_active_subscription


@api_view(["POST"])
def checkout(request):
    try:
        url = create_checkout_session(request.user)
    except BillingNotConfigured:
        return Response({"detail": "Billing is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except stripe.StripeError:
        return Response({"detail": "Could not reach the payment provider."}, status=status.HTTP_502_BAD_GATEWAY)
    return Response({"url": url})


@api_view(["GET"])
def billing_status(request):
    premium = has_active_subscription(request.user)
    return Response({"plan": "premium" if premium else "free", "active_request_limit": None if premium else settings.FREE_PLAN_ACTIVE_LIMIT})


@csrf_exempt
@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def webhook(request):
    """Stripe webhook. The body is only trusted after the signature is verified."""
    secret = settings.STRIPE_WEBHOOK_SECRET
    if not secret:
        return Response({"detail": "Webhook not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    try:
        stripe.Webhook.construct_event(request.body, request.META.get("HTTP_STRIPE_SIGNATURE", ""), secret)
    except (ValueError, stripe.SignatureVerificationError):
        return Response({"detail": "Invalid payload or signature."}, status=status.HTTP_400_BAD_REQUEST)
    # The signature covers exactly these bytes, so parsing them as a plain dict
    # is safe (and avoids depending on the SDK's object type, which changed
    # between stripe-python versions).
    event = json.loads(request.body)

    try:
        # Recording the event id and applying it share one transaction, so a
        # failure while applying it also rolls the id back and Stripe's retry works.
        with transaction.atomic():
            StripeEvent.objects.create(event_id=event["id"], event_type=event["type"])
            handle_event(event)
    except IntegrityError:
        pass  # duplicate delivery: already processed, acknowledge it
    return Response({"received": True})
