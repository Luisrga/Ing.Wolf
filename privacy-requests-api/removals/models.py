from django.conf import settings
from django.db import models
from django.db.models import Q


class Broker(models.Model):
    """A data broker that accepts opt-out (removal) requests."""

    name = models.CharField(max_length=120, unique=True)
    opt_out_url = models.URLField()
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class RemovalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SUBMITTED = "submitted", "Submitted"
        FAILED = "failed", "Failed"

    ACTIVE_STATUSES = (Status.PENDING, Status.PROCESSING, Status.SUBMITTED)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="removal_requests")
    broker = models.ForeignKey(Broker, on_delete=models.PROTECT, related_name="requests")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # At most one active request per (user, broker). Enforced in the
            # database, so concurrent requests cannot create duplicates.
            models.UniqueConstraint(
                fields=["user", "broker"],
                condition=Q(status__in=["pending", "processing", "submitted"]),
                name="uniq_active_request_per_user_broker",
            )
        ]
        indexes = [models.Index(fields=["status", "updated_at"])]

    def __str__(self):
        return f"{self.user_id} -> {self.broker_id} [{self.status}]"
