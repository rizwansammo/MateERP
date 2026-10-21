from datetime import date
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction
from rest_framework.exceptions import PermissionDenied

from apps.approvals import services as approvals
from apps.approvals.models import ApprovalPolicy
from apps.company.models import FinancialParty
from apps.core.exceptions import BusinessRuleViolation
from apps.founders.services import evidence
from apps.ownership.models import OwnershipProposal
from apps.ownership.services import register
from conftest import upload

pytestmark = pytest.mark.django_db


def documented(f, proposal, approver, *, external=None):
    for pk in proposal.snapshot["required_parties"]:
        participant = FinancialParty.objects.get(pk=pk)
        evidence.upload(
            f.request,
            {"proposal_id": proposal.pk, "party_id": pk, "title": f"Signed authorization {pk}"},
            upload(),
        )
    for pk in proposal.snapshot["required_parties"]:
        participant = FinancialParty.objects.get(pk=pk)
        ctx = SimpleNamespace(user=participant.user, META={}) if participant.user_id else f.request
        register.consent(
            ctx,
            proposal.pk,
            pk,
            "authenticated" if participant.user_id else "attestation",
            "Signed approval and authorized external record",
        )
    register.submit(f.request, proposal.pk)
    proposal.refresh_from_db()
    approvals.decide(approver, proposal.approval_id, approve=True)
    return register.confirm(f.request, proposal.pk)


def test_provisional_amendment_preserves_agreements_without_formal_shares(founder_books, make_user):
    f = founder_books
    independent = SimpleNamespace(user=make_user("ownership-reviewer", "administrator"), META={})
    first = register.propose(
        f.request,
        {
            "kind": "provisional",
            "title": "Original agreement",
            "effective_date": "2026-01-01",
            "rationale": "Founders agreement",
            "legal_reference": "AGR-01",
            "weights": {str(f.a.pk): "50", str(f.b.pk): "50"},
        },
        "agreement-original",
    )
    documented(f, first, independent)
    third = FinancialParty.objects.create(
        name="New partner", kind="individual", joined=date(2026, 3, 1), is_founder=True
    )
    second = register.propose(
        f.request,
        {
            "kind": "provisional",
            "title": "New partner amendment",
            "effective_date": "2026-03-01",
            "rationale": "All parties amend their agreement",
            "legal_reference": "AGR-02",
            "weights": {str(f.a.pk): "40", str(f.b.pk): "40", str(third.pk): "20"},
        },
        "agreement-amendment",
    )
    documented(f, second, independent)
    assert register.provisional(date(2026, 2, 1))["weights"] == {
        str(f.a.pk): "50",
        str(f.b.pk): "50",
    }
    assert register.provisional(date(2026, 3, 1))["weights"][str(third.pk)] == "20"
    assert register.holdings(date(2026, 4, 1)) == {}
    assert second.supersedes_id == first.pk


def formal_opening(f, independent):
    cls = register.save_class(
        f.request, {"name": "Ordinary", "currency": "BDT", "par_value": "100"}
    )
    obj = register.propose(
        f.request,
        {
            "kind": "opening",
            "title": "Documented register setup",
            "effective_date": "2026-01-01",
            "share_class_id": cls.pk,
            "rationale": "Existing legal register",
            "legal_reference": "REG-1",
            "lines": [
                {"recipient_id": f.a.pk, "units": 5000, "price": "100"},
                {"recipient_id": f.b.pk, "units": 5000, "price": "100"},
            ],
        },
        "opening-register",
    )
    documented(f, obj, independent)
    return cls


def test_atomic_two_transfer_group(founder_books, make_user):
    f = founder_books
    independent = SimpleNamespace(user=make_user("share-reviewer", "administrator"), META={})
    cls = formal_opening(f, independent)
    third = FinancialParty.objects.create(
        name="Investor", kind="organization", joined=date(2026, 1, 1), is_shareholder=True
    )
    proposal = register.propose(
        f.request,
        {
            "kind": "transfer",
            "title": "Ten points from each founder",
            "effective_date": "2026-03-01",
            "share_class_id": cls.pk,
            "rationale": "Documented transfer group",
            "legal_reference": "TR-1",
            "lines": [
                {"transferor_id": f.a.pk, "recipient_id": third.pk, "percentage_points": "10"},
                {"transferor_id": f.b.pk, "recipient_id": third.pk, "percentage_points": "10"},
            ],
        },
        "transfer-two-points",
    )
    assert register.holdings(date(2026, 3, 1))[str(cls.pk)]["total"] == 10000
    documented(f, proposal, independent)
    after = register.holdings(date(2026, 3, 1))[str(cls.pk)]
    assert after["units"] == {str(f.a.pk): 4000, str(f.b.pk): 4000, str(third.pk): 2000}
    assert register.holdings(date(2026, 2, 1))[str(cls.pk)]["units"][str(f.a.pk)] == 5000
    with pytest.raises(IntegrityError), transaction.atomic():
        OwnershipProposal.objects.filter(pk=proposal.pk).update(weights={"1": "100"})


def test_owner_cannot_impersonate_transferor_or_confirm_without_consent(founder_books, make_user):
    f = founder_books
    independent = SimpleNamespace(user=make_user("consent-reviewer", "administrator"), META={})
    cls = formal_opening(f, independent)
    proposal = register.propose(
        f.request,
        {
            "kind": "transfer",
            "title": "Transfer requiring B authorization",
            "effective_date": "2026-03-01",
            "share_class_id": cls.pk,
            "rationale": "Proposed only",
            "legal_reference": "TR-2",
            "lines": [{"transferor_id": f.b.pk, "recipient_id": f.a.pk, "units": 1000}],
        },
        "unauthorized-transfer",
    )
    with pytest.raises(PermissionDenied):
        register.consent(f.request, proposal.pk, f.b.pk, "authenticated", "Pretend to be B")
    with pytest.raises(BusinessRuleViolation):
        register.consent(
            f.request, proposal.pk, f.b.pk, "attestation", "B already has an ERP account"
        )
    with pytest.raises(BusinessRuleViolation):
        register.submit(f.request, proposal.pk)
    assert register.holdings(date(2026, 3, 1))[str(cls.pk)]["units"][str(f.b.pk)] == 5000


def test_distinct_quorum_and_frozen_governance(founder_books, make_user):
    f = founder_books
    independent = SimpleNamespace(user=make_user("quorum-reviewer", "administrator"), META={})
    policy = ApprovalPolicy.objects.get(category="ownership_changes")
    approvals.update_policy(f.request, policy, {"required_approvals": 2})
    obj = register.propose(
        f.request,
        {
            "kind": "provisional",
            "title": "Quorum agreement",
            "effective_date": "2026-01-01",
            "rationale": "Both consent",
            "legal_reference": "QA-1",
            "weights": {str(f.a.pk): "50", str(f.b.pk): "50"},
        },
        "quorum-agreement",
    )
    for _participant in (f.a, f.b):
        evidence.upload(f.request, {"proposal_id": obj.pk, "title": "Agreement"}, upload())
    register.consent(f.request, obj.pk, f.a.pk, "authenticated", "Agreed")
    register.consent(f.reviewer, obj.pk, f.b.pk, "authenticated", "Agreed")
    obj = register.submit(f.request, obj.pk)
    approvals.decide(f.reviewer, obj.approval_id, approve=True)
    obj.refresh_from_db()
    assert obj.status == "pending"
    with pytest.raises(PermissionDenied):
        approvals.decide(f.reviewer, obj.approval_id, approve=True)
    approvals.update_policy(f.request, policy, {"required_approvals": 1})
    assert approvals.approval_quorum(obj.approval) == 2
    approvals.decide(independent, obj.approval_id, approve=True)
    register.confirm(f.request, obj.pk)
    assert register.provisional(date(2026, 1, 2))["proposal_id"] == obj.pk
