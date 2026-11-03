from datetime import timedelta

import pytest
from celery.exceptions import Retry
from django.utils import timezone

from removals.models import Broker, RemovalRequest
from removals.tasks import MAX_RETRIES, process_removal_request, requeue_stale_requests

pytestmark = pytest.mark.django_db


def make(user, name="ok-broker", status="pending"):
    broker = Broker.objects.create(name=name, opt_out_url="https://example.com/x")
    return RemovalRequest.objects.create(user=user, broker=broker, status=status)


def test_success_marks_submitted(user):
    req = make(user)
    assert process_removal_request.delay(req.pk).get() == "submitted"
    req.refresh_from_db()
    assert req.status == "submitted" and req.attempts == 1 and req.submitted_at


def test_permanent_error_fails_without_retrying(user):
    req = make(user, "reject-broker")
    process_removal_request.delay(req.pk)
    req.refresh_from_db()
    assert req.status == "failed" and req.attempts == 1
    assert "rejected" in req.last_error


def test_temporary_error_goes_back_to_pending_and_is_retried(user):
    req = make(user, "flaky-broker")
    # In eager mode Celery surfaces the scheduled retry as a Retry exception;
    # a real worker re-queues the task with exponential backoff instead.
    with pytest.raises(Retry):
        process_removal_request.delay(req.pk)
    req.refresh_from_db()
    assert req.status == "pending" and req.attempts == 1
    assert "unavailable" in req.last_error


def test_gives_up_after_max_retries(user):
    req = make(user, "flaky-broker")
    result = process_removal_request.apply(args=[req.pk], retries=MAX_RETRIES)
    assert result.get() == "failed"
    req.refresh_from_db()
    assert req.status == "failed" and "Gave up" in req.last_error


def test_duplicate_delivery_is_skipped(user):
    req = make(user)
    assert process_removal_request.delay(req.pk).get() == "submitted"
    assert process_removal_request.delay(req.pk).get() == "skipped"
    req.refresh_from_db()
    assert req.attempts == 1


def test_missing_request_is_a_noop():
    assert process_removal_request.delay(999999).get() == "skipped"


def test_stale_processing_requests_are_recovered(user):
    req = make(user, status="processing")
    RemovalRequest.objects.filter(pk=req.pk).update(updated_at=timezone.now() - timedelta(hours=1))
    assert requeue_stale_requests.delay().get() == 1
    req.refresh_from_db()
    assert req.status == "submitted"


def test_fresh_processing_requests_are_left_alone(user):
    req = make(user, status="processing")
    assert requeue_stale_requests.delay().get() == 0
    req.refresh_from_db()
    assert req.status == "processing"
