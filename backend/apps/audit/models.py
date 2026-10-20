import uuid

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """One recorded administrative or security event.

    Rows are append-only: the database rejects UPDATE and DELETE (see the
    0002 migration), and there is no write API. Values in ``before`` and
    ``after`` are redacted before storage (apps.audit.services.redact).
    """

    class Outcome(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"
        DENIED = "denied", "Denied"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    # Snapshot of who acted, kept even if the user is later renamed.
    actor_label = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=64, db_index=True)
    category = models.CharField(max_length=32, db_index=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    target_label = models.CharField(max_length=200, blank=True)
    request_id = models.CharField(max_length=128, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    outcome = models.CharField(max_length=16, choices=Outcome.choices, default=Outcome.SUCCESS)
    reason = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["actor", "-occurred_at"], name="audit_actor_time_idx"),
            models.Index(fields=["target_type", "target_id"], name="audit_target_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.occurred_at:%Y-%m-%d %H:%M:%S} {self.action}"
