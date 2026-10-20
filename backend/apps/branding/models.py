from django.conf import settings
from django.db import models
from django.db.models import Q

SINGLETON_ID = 1


class BrandingDraft(models.Model):
    """The editable branding configuration (one per installation).

    Editing the draft never affects documents; only publishing does.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=SINGLETON_ID, editable=False)
    config = models.JSONField(default=dict)
    signature = models.ForeignKey(
        "files.StoredFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    seal_image = models.ForeignKey(
        "files.StoredFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(id=SINGLETON_ID), name="branding_draft_singleton"),
        ]

    def __str__(self) -> str:
        return "Branding draft"


class BrandingVersion(models.Model):
    """A published, immutable branding configuration.

    Each version freezes the configuration, the company identity, the number
    formats and the exact asset files in use at publication. Future invoices
    and receipts (Phase 4) reference the version they were issued with, so
    their appearance never changes. The database rejects UPDATE and DELETE.
    """

    number = models.PositiveIntegerField(unique=True)
    label = models.CharField(max_length=80, blank=True)
    config = models.JSONField()
    company = models.JSONField()
    numbering = models.JSONField()
    logo = models.ForeignKey(
        "files.StoredFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    signature = models.ForeignKey(
        "files.StoredFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    seal_image = models.ForeignKey(
        "files.StoredFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    published_at = models.DateTimeField(auto_now_add=True)
    restored_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    approval_request = models.ForeignKey(
        "approvals.ApprovalRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.CheckConstraint(condition=Q(number__gte=1), name="branding_version_positive"),
        ]

    def __str__(self) -> str:
        return f"Version {self.number}" + (f" · {self.label}" if self.label else "")
