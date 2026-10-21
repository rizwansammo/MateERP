"""Documented agreements and confirmed share units are separate record contexts."""

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.accounting.models import amount as money_field
from apps.core.models import IdentifiedRecord

USER = settings.AUTH_USER_MODEL
PARTY = "company.FinancialParty"


class ShareClass(IdentifiedRecord):
    name = models.CharField(max_length=80, unique=True)
    currency = models.CharField(max_length=3)
    par_value = money_field(null=True, blank=True)
    rights = models.CharField(max_length=2000, blank=True)
    is_active = models.BooleanField(default=True)


class OwnershipProposal(IdentifiedRecord):
    kind = models.CharField(
        max_length=16,
        choices=[(x, x.title()) for x in ("provisional", "transfer", "issuance", "opening")],
    )
    title = models.CharField(max_length=200)
    effective_date = models.DateField()
    share_class = models.ForeignKey(
        ShareClass, null=True, blank=True, on_delete=models.PROTECT, related_name="proposals"
    )
    status = models.CharField(max_length=16, default="draft")
    revision = models.PositiveIntegerField(default=1)
    rationale = models.CharField(max_length=2000)
    legal_reference = models.CharField(max_length=500, blank=True)
    weights = models.JSONField(default=dict, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    client_key = models.CharField(max_length=160, unique=True)
    fingerprint = models.CharField(max_length=64)
    approval = models.OneToOneField(
        "approvals.ApprovalRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ownership_proposal",
    )
    supersedes = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="amendments"
    )
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    confirmed_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="confirmed")
                | Q(confirmed_at__isnull=False, confirmed_by__isnull=False),
                name="ownership_confirmed_metadata",
            ),
            models.CheckConstraint(
                condition=Q(kind="provisional", share_class__isnull=True)
                | Q(kind__in=["transfer", "issuance", "opening"], share_class__isnull=False),
                name="ownership_context_consistent",
            ),
        ]


class OwnershipLine(IdentifiedRecord):
    proposal = models.ForeignKey(OwnershipProposal, on_delete=models.PROTECT, related_name="lines")
    transferor = models.ForeignKey(
        PARTY, null=True, blank=True, on_delete=models.PROTECT, related_name="transfers_out"
    )
    recipient = models.ForeignKey(
        PARTY, on_delete=models.PROTECT, related_name="ownership_receipts"
    )
    units = models.PositiveBigIntegerField()
    price = money_field(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(units__gt=0, price__gte=0)
                & (~Q(transferor=F("recipient")) | Q(transferor__isnull=True)),
                name="ownership_line_valid",
            )
        ]


class OwnershipConsent(IdentifiedRecord):
    proposal = models.ForeignKey(
        OwnershipProposal, on_delete=models.PROTECT, related_name="consents"
    )
    party = models.ForeignKey(PARTY, on_delete=models.PROTECT)
    actor = models.ForeignKey(USER, on_delete=models.PROTECT)
    proposal_fingerprint = models.CharField(max_length=64)
    mode = models.CharField(max_length=16)
    reference = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["proposal", "party"], name="ownership_party_consent_once"
            )
        ]


class OwnershipEvidence(IdentifiedRecord):
    proposal = models.ForeignKey(
        OwnershipProposal, on_delete=models.PROTECT, related_name="evidence"
    )
    party = models.ForeignKey(PARTY, null=True, blank=True, on_delete=models.PROTECT)
    file = models.OneToOneField(
        "files.StoredFile", on_delete=models.PROTECT, related_name="ownership_evidence"
    )
    title = models.CharField(max_length=200)
    uploaded_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
