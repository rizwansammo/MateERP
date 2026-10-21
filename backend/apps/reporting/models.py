from django.conf import settings
from django.db import models


class CashFlowReview(models.Model):
    """Append-only reporting classification. Does not post or edit a journal."""

    journal = models.ForeignKey(
        "accounting.JournalEntry", on_delete=models.PROTECT, related_name="cash_flow_reviews"
    )
    version = models.PositiveIntegerField()
    allocations = models.JSONField()
    reason = models.CharField(max_length=1000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["journal", "version"], name="cash_flow_review_version")
        ]

    def __str__(self):
        return f"{self.journal_id}: cash classification v{self.version}"
