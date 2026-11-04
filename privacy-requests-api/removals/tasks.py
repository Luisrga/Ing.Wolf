from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import F
from django.utils import timezone

from .brokers import PermanentBrokerError, TemporaryBrokerError, get_broker_client
from .models import RemovalRequest

Status = RemovalRequest.Status
MAX_RETRIES = 5


def _finish(request_id, status, error="", submitted=False):
    now = timezone.now()
    RemovalRequest.objects.filter(pk=request_id).update(
        status=status,
        last_error=error,
        updated_at=now,
        submitted_at=now if submitted else None,
    )


@shared_task(
    bind=True,
    name="removals.process_removal_request",
    autoretry_for=(TemporaryBrokerError,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=MAX_RETRIES,
    acks_late=True,
)
def process_removal_request(self, request_id: int):
    """Submit one removal request to its broker.

    Safe to run more than once for the same request: the first run atomically
    claims the row (PENDING -> PROCESSING); any duplicate delivery finds it
    already claimed and exits. The network call happens outside any database
    transaction so a slow broker never holds a lock.
    """
    claimed = RemovalRequest.objects.filter(pk=request_id, status=Status.PENDING).update(
        status=Status.PROCESSING, attempts=F("attempts") + 1, updated_at=timezone.now()
    )
    if not claimed:
        return "skipped"

    request = RemovalRequest.objects.select_related("broker").get(pk=request_id)
    try:
        get_broker_client().submit_opt_out(request)
    except PermanentBrokerError as exc:
        _finish(request_id, Status.FAILED, str(exc))
        return "failed"
    except TemporaryBrokerError as exc:
        if self.request.retries >= MAX_RETRIES:
            _finish(request_id, Status.FAILED, f"Gave up after {MAX_RETRIES} retries: {exc}")
            return "failed"
        # Back to PENDING so the retry can claim it again.
        RemovalRequest.objects.filter(pk=request_id).update(
            status=Status.PENDING, last_error=str(exc), updated_at=timezone.now()
        )
        raise

    _finish(request_id, Status.SUBMITTED, submitted=True)
    return "submitted"


@shared_task(name="removals.requeue_stale_requests")
def requeue_stale_requests():
    """Recover work lost to worker crashes or dropped messages.

    - PROCESSING rows untouched for a while belong to a dead worker: reset them.
    - PENDING rows untouched for a while may have lost their message: re-enqueue.
    Both are safe because ``process_removal_request`` is idempotent.
    """
    now = timezone.now()
    cutoff = now - timedelta(minutes=settings.STALE_REQUEST_MINUTES)

    stale_pending = set(
        RemovalRequest.objects.filter(status=Status.PENDING, updated_at__lt=cutoff).values_list("pk", flat=True)
    )
    stale_processing = set(
        RemovalRequest.objects.filter(status=Status.PROCESSING, updated_at__lt=cutoff).values_list("pk", flat=True)
    )
    # Only reset rows that are still PROCESSING, in case a worker just finished one.
    RemovalRequest.objects.filter(pk__in=stale_processing, status=Status.PROCESSING).update(
        status=Status.PENDING, updated_at=now
    )

    ids = stale_pending | stale_processing
    for request_id in ids:
        process_removal_request.delay(request_id)
    return len(ids)
