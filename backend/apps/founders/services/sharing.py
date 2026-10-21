"""Effective policies and bilateral personal settlement; deliberately no ledger calls."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounting.money import strings
from apps.accounting.services.posting import fingerprint
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import get_permission_codes, require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.core.exceptions import BusinessRuleViolation
from apps.purchasing.models import Expense

from ..models import (
    CorporateTransaction,
    FounderObligation,
    PersonalAllocation,
    PersonalConfirmation,
    PersonalObligation,
    PersonalSettlement,
    SharedExpense,
    SharingPolicy,
)
from .common import enabled, exact_weights, on_date, party, positive, split, total


def visible_settlements(user):
    qs = PersonalSettlement.objects.all()
    if "founder.attest" in get_permission_codes(user):
        return qs
    return qs.filter(Q(payer__user=user) | Q(recipient__user=user))


def weights_on(policy, on):
    from apps.ownership.services.register import weights_on as ownership_weights

    values = (
        ownership_weights(policy.basis, on)
        if policy.basis in {"provisional", "formal"}
        else policy.weights
    )
    values = exact_weights(values)
    for pk in values:
        party(pk, on=on, founder=True)
    return strings(values)


def policy_on(on, category=None):
    qs = SharingPolicy.objects.filter(status="active", effective_from__lte=on).filter(
        Q(effective_until__isnull=True) | Q(effective_until__gte=on)
    )
    obj = qs.filter(category_id=category).first() if category else None
    obj = obj or qs.filter(category__isnull=True).first()
    if not obj:
        raise BusinessRuleViolation(
            "No active sharing policy covers this date/category.", code="sharing_policy_required"
        )
    return obj


@transaction.atomic
def save_policy(request, data):
    enabled()
    require(request.user, "founder.planning.manage")
    lock_company()
    basis = data["basis"]
    if basis not in {"equal", "custom", "provisional", "formal"}:
        raise ValidationError(
            {"basis": "Choose equal, custom, provisional ownership or formal ownership."}
        )
    values = (
        {}
        if basis in {"provisional", "formal"}
        else exact_weights(data.get("weights"), percentages=basis == "custom")
    )
    if basis == "equal":
        values = {key: "1" for key in values}
    obj = SharingPolicy(
        name=data["name"],
        effective_from=on_date(data["effective_from"]),
        effective_until=on_date(data["effective_until"]) if data.get("effective_until") else None,
        basis=basis,
        category_id=data.get("category_id"),
        weights=strings(values),
        created_by=request.user,
    )
    obj.full_clean()
    obj.save()
    weights_on(obj, obj.effective_from)
    record(
        "founder.policy_created",
        request=request,
        target=obj,
        after={"basis": basis, "effective": str(obj.effective_from)},
    )
    return obj


def _activate(request, obj):
    weights = weights_on(obj, obj.effective_from)
    prior = (
        SharingPolicy.objects.select_for_update()
        .filter(status="active", category_id=obj.category_id)
        .filter(Q(effective_until__isnull=True) | Q(effective_until__gte=obj.effective_from))
    )
    if obj.effective_until:
        prior = prior.filter(effective_from__lte=obj.effective_until)
    for previous in prior:
        if previous.effective_from >= obj.effective_from or previous.effective_until:
            raise BusinessRuleViolation("Sharing-policy effective intervals must not overlap.")
        if SharedExpense.objects.filter(policy=previous, date__gte=obj.effective_from).exists():
            raise BusinessRuleViolation(
                "The new effective date would reinterpret already allocated expenses."
            )
        previous.effective_until = obj.effective_from - timedelta(days=1)
        previous.save(update_fields=["effective_until"])
        record(
            "founder.policy_superseded",
            request=request,
            target=previous,
            after={"effective_until": str(previous.effective_until)},
        )
    obj.status = "active"
    obj.snapshot = strings(
        {
            "basis": obj.basis,
            "weights_at_activation": weights,
            "effective_from": obj.effective_from,
            "category": obj.category_id,
        }
    )
    obj.save(update_fields=["status", "snapshot"])
    record("founder.policy_activated", request=request, target=obj, after=obj.snapshot)


@transaction.atomic
def activate(request, pk):
    enabled()
    require(request.user, "founder.planning.manage")
    lock_company()
    obj = SharingPolicy.objects.select_for_update().get(pk=pk)
    if obj.status != "draft":
        raise BusinessRuleViolation("Only draft policies can be activated.")
    if approvals.approval_required("founder.policy"):
        obj.approval = approvals.submit(
            request,
            action="founder.policy",
            title=f"Activate sharing policy: {obj.name}",
            payload={"policy_id": obj.pk, "fingerprint": policy_identity(obj)},
            subject_key=str(obj.pk),
        )
        obj.status = "pending"
        obj.save(update_fields=["approval", "status"])
    else:
        _activate(request, obj)
    return obj


def policy_identity(obj):
    return fingerprint(
        strings(
            {
                key: getattr(obj, key)
                for key in (
                    "name",
                    "basis",
                    "weights",
                    "effective_from",
                    "effective_until",
                    "category_id",
                )
            }
        )
    )


def declined_policy(request, approval):
    obj = SharingPolicy.objects.select_for_update().get(pk=approval.payload["policy_id"])
    if obj.status != "pending" or obj.approval_id != approval.pk:
        raise BusinessRuleViolation("This review no longer belongs to the pending policy.")
    obj.status = "draft"
    obj.save(update_fields=["status"])
    record(
        "founder.policy_review_declined",
        request=request,
        target=obj,
        after={"status": "draft"},
        reason=approval.decision_reason or "Review withdrawn",
    )


def execute_policy(request, approval, approver):
    enabled()
    obj = SharingPolicy.objects.select_for_update().get(pk=approval.payload["policy_id"])
    require(obj.created_by, "founder.planning.manage")
    require(approval.requested_by, "founder.planning.manage")
    if (
        obj.status != "pending"
        or obj.approval_id != approval.pk
        or policy_identity(obj) != approval.payload.get("fingerprint")
        or obj.created_by.must_change_password
        or approval.requested_by.must_change_password
    ):
        raise BusinessRuleViolation("The policy changed or is no longer eligible for this review.")
    _activate(request, obj)
    return f"sharing_policy:{obj.pk}"


@transaction.atomic
def allocate_expense(request, data):
    enabled()
    require(request.user, "founder.settlements.manage", "founder.personal.view")
    lock_company()
    source = None
    payment = None
    if data.get("expense_id"):
        source = (
            Expense.objects.select_for_update()
            .filter(pk=data["expense_id"], payment_mode="founder", status="paid")
            .first()
        )
        if not source or not hasattr(source, "founder_funding"):
            raise ValidationError({"expense_id": "Select a posted founder-funded expense."})
        payment = source.founder_funding
        if SharedExpense.objects.filter(expense=source).exists():
            return SharedExpense.objects.get(expense=source)
        on, currency, value, payer, description = (
            source.expense_date,
            source.currency,
            source.total,
            payment.party,
            source.description,
        )
    elif data.get("founder_payment_id"):
        payment = (
            CorporateTransaction.objects.select_for_update()
            .filter(pk=data["founder_payment_id"], kind="vendor_payment", status="posted")
            .first()
        )
        if not payment:
            raise ValidationError(
                {"founder_payment_id": "Select a posted personally funded vendor payment."}
            )
        if SharedExpense.objects.filter(founder_payment=payment).exists():
            return SharedExpense.objects.get(founder_payment=payment)
        on, currency, value, payer, description = (
            payment.date,
            payment.currency,
            payment.amount,
            payment.party,
            payment.reference or "Founder-paid vendor cost",
        )
    else:
        on, currency = on_date(data["date"]), data["currency"]
        value, payer, description = (
            positive(data["amount"], currency),
            party(data["payer_id"], on=on, founder=True),
            data["description"],
        )
    policy = policy_on(on, source.account_id if source else data.get("category_id"))
    weights = weights_on(policy, on)
    if str(payer.pk) not in weights:
        raise BusinessRuleViolation("The payer must participate in this sharing policy.")
    amounts = split(value, currency, weights)
    obj = SharedExpense.objects.create(
        expense=source,
        founder_payment=payment,
        payer=payer,
        date=on,
        currency=currency,
        amount=value,
        description=description,
        policy=policy,
        snapshot=strings(
            {
                "weights": weights,
                "amounts": amounts,
                "policy": policy.name,
                "basis": policy.basis,
                "personal_only": source is None and payment is None,
            }
        ),
        created_by=request.user,
    )
    for pk, amount in amounts.items():
        if int(pk) != payer.pk and amount:
            PersonalObligation.objects.create(
                sharing=obj, debtor_id=int(pk), creditor=payer, amount=amount
            )
    record("founder.personal_allocation_created", request=request, target=obj, after=obj.snapshot)
    return obj


def settled(obligation):
    rows = obligation.allocations.filter(settlement__status="confirmed")
    return total(rows.filter(settlement__is_return=False)) - total(
        rows.filter(settlement__is_return=True)
    )


@transaction.atomic
def record_settlement(request, data, key):
    enabled()
    require(request.user, "founder.settlements.manage", "founder.personal.view")
    lock_company()
    from .corporate import _key

    _key(key)
    identity = fingerprint(strings(data))
    existing = PersonalSettlement.objects.filter(client_key=key).first()
    if existing:
        if existing.fingerprint != identity:
            raise BusinessRuleViolation(
                "The settlement key belongs to another request.", code="idempotency_conflict"
            )
        if not visible_settlements(request.user).filter(pk=existing.pk).exists():
            raise PermissionDenied()
        return existing
    on, currency = on_date(data["date"]), data["currency"]
    payer, recipient = (
        party(data["payer_id"], on=on, founder=True),
        party(data["recipient_id"], on=on, founder=True),
    )
    if "founder.attest" not in get_permission_codes(request.user) and request.user.pk not in {
        payer.user_id,
        recipient.user_id,
    }:
        raise PermissionDenied(
            "Only the parties or an authorized attestor can record this transfer."
        )
    original = (
        PersonalSettlement.objects.filter(
            pk=data.get("returns_id"), status="confirmed", is_return=False
        ).first()
        if data.get("returns_id")
        else None
    )
    if data.get("returns_id") and (
        not original
        or original.payer_id != recipient.pk
        or original.recipient_id != payer.pk
        or original.currency != currency
    ):
        raise ValidationError(
            {"returns_id": "A return must reverse the original transfer's parties and currency."}
        )
    obj = PersonalSettlement(
        payer=payer,
        recipient=recipient,
        date=on,
        currency=currency,
        amount=positive(data["amount"], currency),
        reference=data.get("reference", ""),
        notes=data.get("notes", ""),
        returns=original,
        is_return=bool(original),
        created_by=request.user,
        client_key=key,
        fingerprint=identity,
    )
    obj.full_clean()
    obj.save()
    rows, seen = data.get("allocations") or [], set()
    for row in rows:
        obligation = get_object_or_404(
            PersonalObligation.objects.select_for_update(), pk=row["obligation_id"]
        )
        if obligation.pk in seen or obligation.sharing.currency != currency:
            raise ValidationError(
                {"allocations": "Select each obligation once in the settlement currency."}
            )
        seen.add(obligation.pk)
        if (obligation.debtor_id, obligation.creditor_id) != (
            (recipient.pk, payer.pk) if original else (payer.pk, recipient.pk)
        ):
            raise ValidationError({"allocations": "This obligation belongs to different parties."})
        if original and not original.allocations.filter(obligation=obligation).exists():
            raise ValidationError({"allocations": "Returns must reference original allocations."})
        value = positive(row["amount"], currency)
        PersonalAllocation.objects.create(settlement=obj, obligation=obligation, amount=value)
    if not rows or total(obj.allocations.all()) != obj.amount:
        raise ValidationError({"allocations": "Allocate the full personal transfer."})
    _validate_settlement(obj)
    record(
        "founder.personal_settlement_recorded",
        request=request,
        target=obj,
        after={"amount": obj.amount, "currency": currency, "return": obj.is_return},
    )
    return obj


def _validate_settlement(obj):
    for allocation in obj.allocations.select_related("obligation"):
        obligation = allocation.obligation
        if obj.is_return:
            original = obj.returns.allocations.get(obligation=obligation).amount
            refunded = total(
                PersonalAllocation.objects.filter(
                    obligation=obligation,
                    settlement__returns=obj.returns,
                    settlement__status="confirmed",
                ).exclude(settlement=obj)
            )
            available = original - refunded
        else:
            available = obligation.amount - settled(obligation)
        if allocation.amount > available:
            raise BusinessRuleViolation(
                "The personal transfer exceeds the remaining allocated amount.",
                code="personal_overallocation",
            )


@transaction.atomic
def confirm_settlement(request, pk, party_id, mode, reference):
    enabled()
    lock_company()
    obj = PersonalSettlement.objects.select_for_update().get(pk=pk)
    if obj.status != "recorded":
        raise BusinessRuleViolation("Only recorded transfers can be confirmed.")
    participant = party(party_id)
    if participant.pk not in {obj.payer_id, obj.recipient_id}:
        raise PermissionDenied()
    if mode == "authenticated":
        require(request.user, "founder.personal.confirm")
        if participant.user_id != request.user.pk:
            raise PermissionDenied("You can confirm only for your linked participant.")
    elif mode == "attestation":
        require(request.user, "founder.attest")
        if (
            participant.user_id
            or not reference.strip()
            or not obj.evidence.filter(party=participant).exists()
        ):
            raise BusinessRuleViolation(
                "External-party attestation needs participant-specific evidence and a reference; "
                "account holders confirm themselves."
            )
    else:
        raise ValidationError(
            {"mode": "Select authenticated confirmation or authorized attestation."}
        )
    _validate_settlement(obj)
    PersonalConfirmation.objects.get_or_create(
        settlement=obj,
        party=participant,
        defaults={"actor": request.user, "mode": mode, "reference": reference},
    )
    if obj.confirmations.count() == 2:
        # Reserve/verify every source again while holding the same mutex as
        # company reimbursements. Confirming never writes a company liability.
        if not obj.is_return:
            for allocation in obj.allocations.select_related("obligation__sharing"):
                sharing = allocation.obligation.sharing
                liabilities = (
                    FounderObligation.objects.filter(original_expense_id=sharing.expense_id)
                    if sharing.expense_id
                    else FounderObligation.objects.filter(origin_id=sharing.founder_payment_id)
                ).filter(party_id=obj.recipient_id, origin__status="posted")
                for liability in liabilities:
                    from .corporate import assert_recovery_safe

                    assert_recovery_safe(liability, allocation.amount)
        obj.status = "confirmed"
        obj.save(update_fields=["status"])
    record(
        "founder.personal_settlement_confirmed",
        request=request,
        target=obj,
        after={"party": participant.pk, "mode": mode, "status": obj.status},
    )
    return obj


@transaction.atomic
def dispute(request, pk, reason):
    lock_company()
    obj = visible_settlements(request.user).select_for_update().get(pk=pk)
    require(request.user, "founder.personal.view")
    if not reason.strip() or obj.status != "recorded":
        raise BusinessRuleViolation(
            "Dispute or reject an unconfirmed transfer with a reason. "
            "Confirmed transfers require a documented return."
        )
    obj.status = "disputed"
    obj.save(update_fields=["status"])
    record("founder.personal_settlement_disputed", request=request, target=obj, reason=reason)
    return obj
