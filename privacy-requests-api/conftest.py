import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from removals.models import Broker


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user("ana", "ana@example.com", "S3cure-pass-123")


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def auth(api, user):
    token, _ = Token.objects.get_or_create(user=user)
    api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api


@pytest.fixture
def brokers(db):
    return [Broker.objects.create(name=f"broker-{i}", opt_out_url=f"https://example.com/{i}") for i in range(1, 6)]
