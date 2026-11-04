from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction

from billing.services import has_active_subscription

from .models import Broker, RemovalRequest
from .tasks import process_removal_request


class PlanLimitExceeded(Exception):
    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"The free plan allows {limit} active removal requests.")


def active_request_count(user) -> int:
    return RemovalRequest.objects.filter(user=user, status__in=RemovalRequest.ACTIVE_STATUSES).count()


def create_requests(user, brokers) -> list[RemovalRequest]:
    """Create removal requests for ``brokers`` and enqueue processing.

    - Brokers that already have an active request for this user are skipped
      (the call is idempotent).
    - Free users are capped at ``FREE_PLAN_ACTIVE_LIMIT`` active requests.
    - The user row is locked so two concurrent calls cannot both pass the
      limit check (a no-op on SQLite, effective on PostgreSQL).
    """
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)

        already = set(
            RemovalRequest.objects.filter(
                user=user, status__in=RemovalRequest.ACTIVE_STATUSES
            ).values_list("broker_id", flat=True)
        )
        wanted = [b for b in brokers if b.pk not in already]

        if wanted and not has_active_subscription(user):
            limit = settings.FREE_PLAN_ACTIVE_LIMIT
            if len(already) + len(wanted) > limit:
                raise PlanLimitExceeded(limit)

        created = [RemovalRequest.objects.create(user=user, broker=b) for b in wanted]
        ids = [r.pk for r in created]
        # Enqueue only after the transaction commits, otherwise a worker could
        # pick the task up before the rows are visible.
        transaction.on_commit(lambda: [process_removal_request.delay(i) for i in ids])
    return created


def brokers_for(broker_ids=None, all_brokers=False):
    qs = Broker.objects.filter(active=True)
    if not all_brokers:
        qs = qs.filter(pk__in=broker_ids or [])
    return list(qs)
