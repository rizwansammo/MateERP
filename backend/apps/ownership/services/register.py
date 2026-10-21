"""Provisional agreements and formal register events, consent and quorum."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounting.money import decimal, strings
from apps.accounting.services.posting import fingerprint
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.core.exceptions import BusinessRuleViolation
from apps.founders.services.common import enabled, exact_weights, on_date, party

from ..models import OwnershipConsent, OwnershipLine, ShareClass
from ..models import OwnershipProposal as Proposal


def provisional(on):
    obj = (
        Proposal.objects.filter(kind="provisional", status="confirmed", effective_date__lte=on)
        .order_by("-effective_date", "-pk")
        .first()
    )
    return {
        "proposal_id": obj.pk if obj else None,
        "weights": obj.weights if obj else {},
        "effective_date": obj.effective_date if obj else None,
    }


def holdings(on, *, share_class=None, candidate=None):
    """Replay effective events; never infer holdings from cash contributed."""
    qs = Proposal.objects.filter(status="confirmed").exclude(kind="provisional")
    if share_class is not None:
        qs = qs.filter(share_class_id=share_class)
    events = list(qs.prefetch_related("lines").order_by("effective_date", "pk"))
    if candidate:
        events.append(candidate)
        events.sort(key=lambda p: (p.effective_date, p.pk or 0))
    balances, output = {}, {}
    for event in events:
        for line in event.lines.all():
            source = (event.share_class_id, line.transferor_id)
            dest = (event.share_class_id, line.recipient_id)
            if event.kind == "transfer":
                balances[source] = balances.get(source, 0) - line.units
                if balances[source] < 0:
                    raise BusinessRuleViolation(
                        "This event would over-transfer shares, including a later effective event.",
                        code="insufficient_shares",
                    )
            balances[dest] = balances.get(dest, 0) + line.units
        if event.effective_date <= on:
            output = dict(balances)
    classes = {}
    for (class_id, owner), units in output.items():
        if units:
            classes.setdefault(str(class_id), {})[str(owner)] = units
    return {
        key: {
            "units": rows,
            "total": sum(rows.values()),
            "percentages": {p: str(Decimal(n) * 100 / sum(rows.values())) for p, n in rows.items()},
        }
        for key, rows in classes.items()
    }


def weights_on(basis, on):
    if basis == "provisional":
        values = provisional(on)["weights"]
        if not values:
            raise BusinessRuleViolation("No confirmed provisional agreement applies on this date.")
        return values
    classes = holdings(on)
    if len(classes) != 1:
        raise BusinessRuleViolation(
            "Ownership sharing requires exactly one formal share class; "
            "unlike class rights cannot be combined."
        )
    return next(iter(classes.values()))["units"]


@transaction.atomic
def save_class(request, data):
    enabled("ownership")
    require(request.user, "ownership.manage")
    lock_company()
    obj = ShareClass(**data)
    if obj.par_value is not None:
        obj.par_value = decimal(obj.par_value)
    obj.full_clean()
    obj.save()
    record("ownership.class_created", request=request, target=obj, after=data)
    return obj


def _required_parties(obj):
    if obj.kind == "provisional":
        previous = (
            Proposal.objects.filter(
                kind="provisional", status="confirmed", effective_date__lte=obj.effective_date
            )
            .order_by("-effective_date", "-pk")
            .first()
        )
        return set(map(int, obj.weights)) | (set(map(int, previous.weights)) if previous else set())
    if obj.kind == "transfer":
        return set(obj.lines.values_list("transferor_id", flat=True))
    return set(obj.lines.values_list("recipient_id", flat=True))


@transaction.atomic
def propose(request, data, key):
    enabled("ownership")
    require(request.user, "ownership.manage")
    lock_company()
    identity = fingerprint(strings(data))
    old = Proposal.objects.filter(client_key=key).first()
    if old:
        if old.fingerprint != identity:
            raise BusinessRuleViolation(
                "This key is already bound to another ownership proposal.",
                code="idempotency_conflict",
            )
        return old
    kind = data["kind"]
    on = on_date(data["effective_date"])
    obj = Proposal(
        kind=kind,
        title=data["title"],
        effective_date=on,
        rationale=data["rationale"],
        legal_reference=data.get("legal_reference", ""),
        created_by=request.user,
        client_key=key,
        fingerprint=identity,
    )
    if kind == "provisional":
        values = exact_weights(data.get("weights"), percentages=True)
        for pk in values:
            party(pk, on=on)
        obj.weights = strings(values)
        obj.supersedes = (
            Proposal.objects.filter(kind=kind, status="confirmed", effective_date__lt=on)
            .order_by("-effective_date", "-pk")
            .first()
        )
    else:
        obj.share_class = ShareClass.objects.filter(
            pk=data.get("share_class_id"), is_active=True
        ).first()
        if not obj.share_class:
            raise ValidationError({"share_class_id": "Select an active share class."})
    obj.full_clean()
    obj.save()
    if kind != "provisional":
        rows = data.get("lines") or []
        if not 1 <= len(rows) <= 100:
            raise ValidationError({"lines": "Enter between 1 and 100 event lines."})
        current = holdings(on, share_class=obj.share_class_id).get(
            str(obj.share_class_id), {"units": {}, "total": 0}
        )
        for row in rows:
            source = party(row["transferor_id"], on=on) if kind == "transfer" else None
            target = party(row["recipient_id"], on=on)
            units = row.get("units")
            if row.get("percentage_points") is not None:
                exact = decimal(row["percentage_points"]) * current["total"] / 100
                if exact != exact.to_integral_value():
                    raise ValidationError(
                        {
                            "percentage_points": "This share count cannot express "
                            "the requested percentage points exactly."
                        }
                    )
                units = int(exact)
            if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
                raise ValidationError({"units": "Enter a positive whole share count."})
            line = OwnershipLine(
                proposal=obj,
                transferor=source,
                recipient=target,
                units=units,
                price=decimal(row.get("price", "0")),
            )
            if (
                kind in {"issuance", "opening"}
                and obj.share_class.par_value is not None
                and line.price < obj.share_class.par_value
            ):
                raise ValidationError(
                    {"price": "Issue price cannot be below the configured par value."}
                )
            line.full_clean()
            line.save()
        holdings(on, share_class=obj.share_class_id, candidate=obj)
        if (
            kind == "opening"
            and Proposal.objects.filter(status="confirmed", share_class=obj.share_class).exists()
        ):
            raise BusinessRuleViolation(
                "Opening register setup is available only before confirmed events."
            )
        # Pending transfer reservations prevent incompatible competing proposals.
        if kind == "transfer":
            for source in set(obj.lines.values_list("transferor_id", flat=True)):
                reserved = sum(
                    OwnershipLine.objects.filter(
                        transferor_id=source,
                        proposal__share_class=obj.share_class,
                        proposal__kind="transfer",
                        proposal__status__in=["draft", "pending", "approved"],
                    ).values_list("units", flat=True)
                )
                if reserved > current["units"].get(str(source), 0):
                    raise BusinessRuleViolation(
                        "Other pending transfers reserve these shares.", code="shares_reserved"
                    )
    obj.snapshot = strings(
        {
            "required_parties": sorted(_required_parties(obj)),
            "before": provisional(on)
            if kind == "provisional"
            else holdings(on, share_class=obj.share_class_id),
            "after": {"weights": obj.weights}
            if kind == "provisional"
            else holdings(on, share_class=obj.share_class_id, candidate=obj),
        }
    )
    obj.save(update_fields=["snapshot"])
    record(
        "ownership.proposed",
        request=request,
        target=obj,
        after={"kind": kind, "effective": str(on)},
    )
    return obj


@transaction.atomic
def consent(request, pk, party_id, mode, reference):
    enabled("ownership")
    lock_company()
    obj = Proposal.objects.select_for_update().get(pk=pk)
    if obj.status != "draft" or int(party_id) not in obj.snapshot["required_parties"]:
        raise BusinessRuleViolation("Consent must cover an affected party on a draft proposal.")
    participant = party(party_id)
    if mode == "authenticated":
        require(request.user, "ownership.consent")
        if participant.user_id != request.user.pk:
            raise PermissionDenied("Only the linked shareholder can give authenticated consent.")
    elif mode == "attestation":
        require(request.user, "ownership.attest")
        if participant.user_id:
            raise BusinessRuleViolation(
                "This shareholder has an ERP account and must consent as themselves."
            )
        if not obj.evidence.filter(party=participant).exists() or not reference.strip():
            raise ValidationError(
                {
                    "reference": "Attach this participant's authorization evidence "
                    "and describe your authority."
                }
            )
    else:
        raise ValidationError({"mode": "Select authenticated consent or authorized attestation."})
    result, _ = OwnershipConsent.objects.get_or_create(
        proposal=obj,
        party=participant,
        defaults={
            "actor": request.user,
            "mode": mode,
            "reference": reference,
            "proposal_fingerprint": obj.fingerprint,
        },
    )
    record(
        "ownership.consent_recorded",
        request=request,
        target=obj,
        after={"party": participant.pk, "mode": mode, "actor": request.user.pk},
    )
    return result


def _consents(obj):
    required = set(obj.snapshot["required_parties"])
    # A backdated agreement cannot bypass a later-added affected participant.
    if not _required_parties(obj) <= required:
        raise BusinessRuleViolation(
            "Affected parties changed. Create a fresh proposal and consents."
        )
    found = set()
    for c in obj.consents.select_related("party", "actor"):
        if c.proposal_fingerprint != obj.fingerprint:
            continue
        if c.mode == "authenticated" and c.party.user_id != c.actor_id:
            continue
        if c.mode == "attestation" and not obj.evidence.filter(party=c.party).exists():
            continue
        found.add(c.party_id)
    if not required <= found:
        raise BusinessRuleViolation(
            "Authorization from every affected participant is required.",
            code="shareholder_consent_required",
        )


@transaction.atomic
def submit(request, pk):
    enabled("ownership")
    require(request.user, "ownership.manage")
    lock_company()
    obj = Proposal.objects.select_for_update().get(pk=pk)
    if obj.status != "draft":
        raise BusinessRuleViolation("Only draft proposals can be submitted.")
    _consents(obj)
    if not obj.legal_reference.strip() or not obj.evidence.exists():
        raise BusinessRuleViolation(
            "Attach the agreement/reference and supporting evidence before review."
        )
    obj.approval = approvals.submit(
        request,
        action="ownership.review",
        title=obj.title,
        payload={"proposal_id": obj.pk, "fingerprint": obj.fingerprint},
        subject_key=str(obj.pk),
    )
    obj.status = "pending"
    obj.save(update_fields=["approval", "status"])
    return obj


def declined(request, approval):
    obj = Proposal.objects.select_for_update().get(pk=approval.payload["proposal_id"])
    if obj.approval_id != approval.pk or obj.status != "pending":
        raise BusinessRuleViolation("The approval no longer belongs to this proposal.")
    obj.status = "rejected"
    obj.save(update_fields=["status"])
    record(
        "ownership.rejected",
        request=request,
        target=obj,
        reason=approval.decision_reason or "Review withdrawn",
    )


def execute_review(request, approval, approver):
    obj = Proposal.objects.select_for_update().get(pk=approval.payload["proposal_id"])
    require(obj.created_by, "ownership.manage")
    require(approval.requested_by, "ownership.manage")
    if obj.created_by.must_change_password or approval.requested_by.must_change_password:
        raise PermissionDenied("The proposer must complete account security requirements first.")
    enabled("ownership")
    if obj.status != "pending" or obj.fingerprint != approval.payload["fingerprint"]:
        raise BusinessRuleViolation("The proposal no longer matches the reviewed request.")
    _consents(obj)
    obj.status = "approved"
    obj.save(update_fields=["status"])
    return f"ownership:{obj.pk}"


@transaction.atomic
def confirm(request, pk):
    enabled("ownership")
    require(request.user, "ownership.manage")
    lock_company()
    obj = Proposal.objects.select_for_update().get(pk=pk)
    require(obj.created_by, "ownership.manage")
    if obj.created_by.must_change_password:
        raise PermissionDenied("The proposer must complete account security requirements first.")
    if obj.status == "confirmed":
        return obj
    if obj.status != "approved" or obj.approval.status != "approved":
        raise BusinessRuleViolation("A documented approved proposal is required.")
    require(obj.approval.requested_by, "ownership.manage")
    if obj.approval.requested_by.must_change_password:
        raise PermissionDenied("The requester must complete account security requirements first.")
    if len(approvals.eligible_votes(obj.approval)) < approvals.approval_quorum(obj.approval):
        raise BusinessRuleViolation("The required independent approvers are no longer eligible.")
    _consents(obj)
    for pk in _required_parties(obj):
        party(pk, on=obj.effective_date)
    if obj.kind == "provisional":
        if Proposal.objects.filter(
            kind="provisional", status="confirmed", effective_date=obj.effective_date
        ).exists():
            raise BusinessRuleViolation("An agreement already takes effect on this date.")
        # Previously confirmed later versions stay frozen. A correction is an
        # explicitly documented amendment, not an edit of their snapshots.
        before = provisional(obj.effective_date)
        if before["proposal_id"] != obj.snapshot["before"]["proposal_id"]:
            raise BusinessRuleViolation(
                "The effective agreement changed; propose a fresh amendment."
            )
    else:
        before = holdings(obj.effective_date, share_class=obj.share_class_id)
        if before != obj.snapshot["before"]:
            raise BusinessRuleViolation(
                "The register changed; preview and approve a fresh proposal."
            )
        holdings(obj.effective_date, share_class=obj.share_class_id, candidate=obj)
    obj.status, obj.confirmed_by, obj.confirmed_at = "confirmed", request.user, timezone.now()
    obj.save(update_fields=["status", "confirmed_by", "confirmed_at"])
    record(
        "ownership.agreement_amended" if obj.kind == "provisional" else "ownership.confirmed",
        request=request,
        target=obj,
        after=obj.snapshot,
    )
    return obj


@transaction.atomic
def cancel(request, pk, reason):
    require(request.user, "ownership.manage")
    lock_company()
    obj = Proposal.objects.select_for_update().get(pk=pk)
    if obj.status not in {"draft", "pending", "approved"} or not reason.strip():
        raise BusinessRuleViolation(
            "Confirmed history cannot be deleted; provide a reason for cancelling a proposal."
        )
    if obj.approval_id and obj.approval.status == "pending":
        raise BusinessRuleViolation("Withdraw or reject the pending approval first.")
    obj.status = "cancelled"
    obj.save(update_fields=["status"])
    record("ownership.cancelled", request=request, target=obj, reason=reason)
    return obj
