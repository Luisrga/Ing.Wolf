import pytest
from django.db import IntegrityError, transaction
from rest_framework.authtoken.models import Token

from billing.models import Subscription
from removals.models import RemovalRequest

pytestmark = pytest.mark.django_db


def ids(brokers):
    return [b.pk for b in brokers]


def test_register_returns_token(api):
    resp = api.post("/api/auth/register/", {"username": "luis", "email": "l@example.com", "password": "Another-Str0ng-pass"})
    assert resp.status_code == 201
    assert Token.objects.filter(key=resp.json()["token"]).exists()


def test_register_rejects_weak_password(api):
    resp = api.post("/api/auth/register/", {"username": "luis", "password": "12345678"})
    assert resp.status_code == 400


def test_endpoints_require_authentication(api):
    assert api.get("/api/requests/").status_code == 401
    assert api.get("/api/brokers/").status_code == 401


def test_created_requests_are_processed(auth, brokers, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        resp = auth.post("/api/requests/", {"broker_ids": ids(brokers[:2])}, format="json")
    assert resp.status_code == 201
    assert resp.json()["created"] == 2
    statuses = set(RemovalRequest.objects.values_list("status", flat=True))
    assert statuses == {"submitted"}


def test_duplicate_active_requests_are_ignored(auth, brokers, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        auth.post("/api/requests/", {"broker_ids": ids(brokers[:2])}, format="json")
        again = auth.post("/api/requests/", {"broker_ids": ids(brokers[:2])}, format="json")
    assert again.status_code == 201
    assert again.json()["created"] == 0
    assert RemovalRequest.objects.count() == 2


def test_free_plan_limit_returns_402_and_creates_nothing(auth, brokers):
    resp = auth.post("/api/requests/", {"broker_ids": ids(brokers[:4])}, format="json")
    assert resp.status_code == 402
    assert resp.json()["limit"] == 3
    assert RemovalRequest.objects.count() == 0


def test_active_subscription_lifts_the_limit(auth, user, brokers, django_capture_on_commit_callbacks):
    Subscription.objects.create(user=user, status="active")
    with django_capture_on_commit_callbacks(execute=True):
        resp = auth.post("/api/requests/", {"all_brokers": True}, format="json")
    assert resp.status_code == 201
    assert resp.json()["created"] == 5


def test_users_only_see_their_own_requests(auth, brokers, django_user_model, django_capture_on_commit_callbacks):
    other = django_user_model.objects.create_user("bob", password="Another-Str0ng-pass")
    RemovalRequest.objects.create(user=other, broker=brokers[0])
    with django_capture_on_commit_callbacks(execute=True):
        auth.post("/api/requests/", {"broker_ids": [brokers[1].pk]}, format="json")
    listing = auth.get("/api/requests/").json()
    assert listing["count"] == 1
    assert listing["results"][0]["broker"]["id"] == brokers[1].pk
    foreign = RemovalRequest.objects.get(user=other)
    assert auth.get(f"/api/requests/{foreign.pk}/").status_code == 404


@pytest.mark.parametrize("body", [{}, {"broker_ids": [1], "all_brokers": True}, {"broker_ids": []}])
def test_requires_exactly_one_selector(auth, brokers, body):
    assert auth.post("/api/requests/", body, format="json").status_code == 400


def test_status_filter(auth, user, brokers):
    RemovalRequest.objects.create(user=user, broker=brokers[0], status="failed")
    RemovalRequest.objects.create(user=user, broker=brokers[1], status="submitted")
    assert auth.get("/api/requests/?status=failed").json()["count"] == 1


def test_database_rejects_a_second_active_request_for_the_same_broker(user, brokers):
    RemovalRequest.objects.create(user=user, broker=brokers[0])
    with pytest.raises(IntegrityError), transaction.atomic():
        RemovalRequest.objects.create(user=user, broker=brokers[0])
    # Once the first one is finished, a new request is allowed again.
    RemovalRequest.objects.update(status="failed")
    RemovalRequest.objects.create(user=user, broker=brokers[0])
