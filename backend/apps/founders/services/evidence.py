"""Private founder/ownership evidence never enters client or vendor filing."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import get_permission_codes, require
from apps.audit.services import record
from apps.files.services import store_document
from apps.ownership.models import OwnershipEvidence, OwnershipProposal

from ..models import CorporateTransaction, FounderEvidence, FounderLoan
from .common import enabled, party
from .sharing import visible_settlements


def can_view_proposal(user, proposal):
    codes = get_permission_codes(user)
    if {"ownership.view", "ownership.manage", "ownership.approve"} & codes:
        return True
    return "ownership.consent" in codes and any(
        str(pk) == str(getattr(getattr(user, "financial_party", None), "pk", ""))
        for pk in proposal.snapshot.get("required_parties", [])
    )


def can_read(user, stored):
    codes = get_permission_codes(user)
    if stored.purpose == "ownership_evidence":
        ref = OwnershipEvidence.objects.select_related("proposal").filter(file=stored).first()
        return bool(ref and can_view_proposal(user, ref.proposal))
    ref = FounderEvidence.objects.select_related("settlement").filter(file=stored).first()
    if ref is None:
        return False
    if ref.settlement_id:
        return (
            "founder.personal.view" in codes
            and visible_settlements(user).filter(pk=ref.settlement_id).exists()
        )
    return "founder.view" in codes


@transaction.atomic
def upload(request, data, uploaded):
    lock_company()
    if (
        sum(
            bool(data.get(key))
            for key in ("proposal_id", "transaction_id", "settlement_id", "loan_id")
        )
        > 1
    ):
        raise ValidationError({"target": "Select exactly one source record for this evidence."})
    title = str(data.get("title", ""))[:200]
    if not title.strip() or uploaded is None:
        raise ValidationError({"file": "Provide a title and a PDF or image."})
    participant = party(data["party_id"]) if data.get("party_id") else None
    if data.get("proposal_id"):
        enabled("ownership")
        require(request.user, "ownership.manage")
        proposal = get_object_or_404(
            OwnershipProposal.objects.select_for_update(), pk=data["proposal_id"]
        )
        if proposal.status != "draft" or proposal.consents.exists():
            raise ValidationError(
                {"proposal_id": "Attach all evidence before shareholder consents and submission."}
            )
        stored = store_document(uploaded, purpose="ownership_evidence", user=request.user)
        obj = OwnershipEvidence.objects.create(
            proposal=proposal, party=participant, file=stored, title=title, uploaded_by=request.user
        )
    else:
        enabled()
        if data.get("settlement_id"):
            require(request.user, "founder.personal.view", "founder.settlements.manage")
            settlement = (
                visible_settlements(request.user)
                .select_for_update()
                .filter(pk=data["settlement_id"])
                .first()
            )
            if settlement is None:
                raise NotFound()
            if settlement.status != "recorded" or settlement.confirmations.exists():
                raise ValidationError({"settlement_id": "Attach evidence before confirmations."})
            target = {"settlement": settlement}
            purpose = "personal_evidence"
        else:
            require(request.user, "founder.transactions.manage", "founder.view")
            if data.get("transaction_id"):
                target = {
                    "transaction": get_object_or_404(
                        CorporateTransaction, pk=data["transaction_id"]
                    )
                }
            elif data.get("loan_id"):
                target = {"loan": get_object_or_404(FounderLoan, pk=data["loan_id"])}
            elif participant:
                target = {}
            else:
                raise ValidationError(
                    {"target": "Select a founder, loan, transaction or personal settlement."}
                )
            purpose = "founder_evidence"
        stored = store_document(uploaded, purpose=purpose, user=request.user)
        obj = FounderEvidence.objects.create(
            **target, party=participant, file=stored, title=title, uploaded_by=request.user
        )
    record(
        "founder.evidence_uploaded",
        request=request,
        target=obj,
        after={"file_id": str(stored.pk), "purpose": stored.purpose},
    )
    return obj
