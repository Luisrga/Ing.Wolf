import hashlib
import hmac
import json
import time

import pytest
import stripe

from billing.models import StripeEvent, Subscription

pytestmark = pytest.mark.django_db
SECRET = "whsec_test_secret"


def signed_post(client, payload: dict, secret=SECRET):
    body = json.dumps(payload)
    ts = int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return client.post(
        "/api/billing/webhook/", data=body, content_type="application/json",
        HTTP_STRIPE_SIGNATURE=f"t={ts},v1={sig}",
    )


def completed_event(user, event_id="evt_1"):
    return {
        "id": event_id, "object": "event", "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": str(user.pk), "customer": "cus_1", "subscription": "sub_1"}},
    }


@pytest.fixture
def stripe_settings(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    settings.STRIPE_PRICE_ID = "price_x"
    settings.STRIPE_WEBHOOK_SECRET = SECRET


def test_checkout_returns_stripe_url(auth, stripe_settings, monkeypatch):
    captured = {}

    class FakeSession:
        url = "https://checkout.stripe.test/session"

    def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeSession()

    monkeypatch.setattr(stripe.checkout.Session, "create", fake_create)
    resp = auth.post("/api/billing/checkout/")
    assert resp.status_code == 200 and resp.json()["url"] == FakeSession.url
    assert captured["mode"] == "subscription" and captured["customer_email"] == "ana@example.com"


def test_checkout_without_configuration_is_503(auth, settings):
    settings.STRIPE_SECRET_KEY = ""
    assert auth.post("/api/billing/checkout/").status_code == 503


def test_webhook_activates_subscription(api, auth, user, stripe_settings):
    assert signed_post(api, completed_event(user)).status_code == 200
    assert Subscription.objects.get(user=user).status == "active"
    assert auth.get("/api/billing/status/").json()["plan"] == "premium"


def test_webhook_rejects_bad_signature(api, user, stripe_settings):
    assert signed_post(api, completed_event(user), secret="wrong").status_code == 400
    assert not Subscription.objects.exists()


def test_webhook_is_idempotent(api, user, stripe_settings):
    assert signed_post(api, completed_event(user)).status_code == 200
    assert signed_post(api, completed_event(user)).status_code == 200
    assert StripeEvent.objects.count() == 1 and Subscription.objects.count() == 1


def test_cancellation_downgrades_user(api, auth, user, stripe_settings):
    signed_post(api, completed_event(user))
    cancel = {"id": "evt_2", "object": "event", "type": "customer.subscription.deleted",
              "data": {"object": {"id": "sub_1", "status": "canceled"}}}
    assert signed_post(api, cancel).status_code == 200
    assert auth.get("/api/billing/status/").json()["plan"] == "free"


def test_webhook_without_secret_is_503(api, settings):
    settings.STRIPE_WEBHOOK_SECRET = ""
    assert api.post("/api/billing/webhook/", data="{}", content_type="application/json").status_code == 503
