"""The sole posting boundary used by manual journals and treasury adapters."""

import hashlib
import json
import uuid
from decimal import Decimal, localcontext
from types import SimpleNamespace

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.authorization import require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.company.services import get_business_settings, render_number
from apps.core.exceptions import BusinessRuleViolation

from ..models import (
    Account,
    AccountingPeriod,
    JournalEntry,
    JournalLine,
    JournalSequence,
    PostingIdentity,
    TaxRevision,
)
from ..money import ZERO, convert, decimal, money, strings
from .adapters import SUBLEDGER_CONTROLS, is_domain_source
from .setup import lock_company, rate_for


def fingerprint(payload):
    return hashlib.sha256(
        json.dumps(strings(payload), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def line_payload(line):
    return strings(
        {
            k: getattr(line, k)
            for k in (
                "account_id",
                "description",
                "currency",
                "debit",
                "credit",
                "exchange_rate",
                "rate_source",
                "base_debit",
                "base_credit",
                "valuation",
                "dimensions",
                "tax_revision_id",
            )
        }
    )


def snapshot(journal):
    return strings(
        {
            "journal_id": journal.pk,
            "revision": journal.revision,
            "posting_date": journal.posting_date,
            "journal_date": journal.journal_date,
            "description": journal.description,
            "reason": journal.reason,
            "kind": journal.kind,
            "source_type": journal.source_type,
            "source_id": journal.source_id,
            "source_action": journal.source_action,
            "reversal_of": journal.reversal_of_id,
            "adjustment_of": journal.adjustment_of_id,
            "lines": [line_payload(line) for line in journal.lines.all()],
        }
    )


def bank_position(account_id, *, before=None):
    qs = JournalLine.objects.filter(account_id=account_id, journal__status="posted")
    if before:
        qs = qs.filter(journal__posting_date__lte=before)
    agg = qs.aggregate(d=Sum("debit"), c=Sum("credit"), bd=Sum("base_debit"), bc=Sum("base_credit"))
    return (agg["d"] or ZERO) - (agg["c"] or ZERO), (agg["bd"] or ZERO) - (agg["bc"] or ZERO)


def build_lines(raw, company, on, *, trusted=False, reversal=False):
    if not isinstance(raw, list) or not 1 <= len(raw) <= 250:
        raise ValidationError({"lines": "Provide between 1 and 250 meaningful lines."})
    out, balances = [], {}
    from apps.banking.models import BankAccount

    for position, data in enumerate(raw, 1):
        account = Account.objects.select_for_update().filter(pk=data.get("account_id")).first()
        if not account or not account.is_active or not account.is_postable:
            raise ValidationError({"lines": f"Line {position}: choose an active posting account."})
        currency = data.get("currency") or company.base_currency
        if currency not in get_business_settings().enabled_currencies:
            raise ValidationError({"currency": f"{currency} is not enabled."})
        if account.currency and account.currency != currency:
            raise ValidationError(
                {"currency": f"Account {account.code} requires {account.currency}."}
            )
        debit = money(data.get("debit", "0"), currency, "debit")
        credit = money(data.get("credit", "0"), currency, "credit")
        if (debit > 0) == (credit > 0):
            raise ValidationError({"lines": f"Line {position}: enter a positive debit OR credit."})
        fx, source = (
            rate_for(currency, on, company.base_currency)
            if not data.get("exchange_rate")
            else (
                decimal(data["exchange_rate"], "exchange_rate", 12),
                str(data.get("rate_source", "")),
            )
        )
        if fx <= 0 or (currency == company.base_currency and fx != 1):
            raise ValidationError({"exchange_rate": "Invalid exchange rate."})
        if data.get("exchange_rate") and currency != company.base_currency and not source:
            raise ValidationError({"rate_source": "Explain the explicit rate override."})
        bd, bc = (
            convert(debit, fx, company.base_currency),
            convert(credit, fx, company.base_currency),
        )
        valuation = "spot"
        bank = BankAccount.objects.filter(gl_account=account).first()
        if bank and (not bank.is_active or bank.currency != currency):
            raise ValidationError(
                {"account_id": "Bank account is inactive or its currency differs."}
            )
        if bank and currency != company.base_currency and not reversal:
            # Backdating would change the carrying-value sequence of already posted outflows.
            if account.journal_lines.filter(
                journal__status="posted", journal__posting_date__gt=on
            ).exists():
                raise BusinessRuleViolation(
                    "Foreign-bank movements must be posted in chronological order."
                )
            if account.pk not in balances:
                balances[account.pk] = bank_position(account.pk)
            units, book = balances[account.pk]
            if credit:
                if units < credit or units <= 0:
                    raise BusinessRuleViolation(
                        "Insufficient foreign-currency units for book-value disposal."
                    )
                with localcontext() as ctx:
                    ctx.prec = 60
                    fx = book / units
                    bc = book if credit == units else convert(credit, fx, company.base_currency)
                    fx = fx.quantize(Decimal("0.000000000001"))
                source, valuation = "Historical weighted-average book value", "carrying"
            balances[account.pk] = (units + debit - credit, book + bd - bc)
        if trusted and ("base_debit" in data or "base_credit" in data):
            bd = money(data.get("base_debit", "0"), company.base_currency)
            bc = money(data.get("base_credit", "0"), company.base_currency)
            valuation = data.get("valuation", valuation)
        if (debit and bd == 0) or (credit and bc == 0):
            raise ValidationError({"lines": "Conversion rounded a nonzero line to zero."})
        dims = data.get("dimensions", {})
        tax_revision_id = data.get("tax_revision_id")
        if tax_revision_id:
            revision = TaxRevision.objects.filter(
                pk=tax_revision_id, effective_date__lte=on, tax_code__is_active=True
            ).first()
            if not revision or account.pk not in (
                revision.input_account_id,
                revision.output_account_id,
            ):
                raise ValidationError(
                    {"tax_revision_id": "Choose an effective tax revision mapped to this account."}
                )
        if not isinstance(dims, dict) or len(json.dumps(dims)) > 2000:
            raise ValidationError({"dimensions": "Use a small object of dimension references."})
        out.append(
            JournalLine(
                position=position,
                account=account,
                description=str(data.get("description", ""))[:300],
                currency=currency,
                debit=debit,
                credit=credit,
                exchange_rate=fx,
                rate_source=source,
                base_debit=bd,
                base_credit=bc,
                valuation=valuation,
                dimensions=dims,
                tax_revision_id=data.get("tax_revision_id"),
                account_snapshot={
                    "code": account.code,
                    "name": account.name,
                    "type": account.account_type,
                    "subtype": account.subtype,
                    "normal_side": account.normal_side,
                },
            )
        )
    return out


def _require_poster(request, authority):
    """Public callers need accounting.manage; domain adapters present their authority."""
    if authority is None:
        require(request.user, "accounting.manage")
    else:
        authority.verify(request.user)


def _owned_by_domain(journal):
    if is_domain_source(journal.source_type):
        return True
    original = journal.reversal_of
    return bool(original and is_domain_source(original.source_type))


@transaction.atomic
def save_draft(request, data, pk=None, *, trusted=False, authority=None):
    _require_poster(request, authority)
    company = lock_company()
    journal = JournalEntry.objects.select_for_update().filter(pk=pk).first() if pk else None
    if pk and journal is None:
        raise NotFound()
    if journal and journal.status == "posted":
        raise BusinessRuleViolation("Posted journals are immutable.")
    if journal and journal.status == "pending":
        if journal.approval.status == "pending":
            raise BusinessRuleViolation(
                "Withdraw or reject the request before editing its frozen draft."
            )
        journal.status = "draft"
        journal.approval = None
    if journal and data.get("revision") != journal.revision:
        raise BusinessRuleViolation(
            "This draft changed. Reload before saving.", code="stale_revision"
        )
    new = journal is None
    if new:
        kind = data.get("kind", "manual")
        if not trusted and kind not in ("manual", "opening", "adjustment"):
            raise ValidationError({"kind": "Unsupported manual journal kind."})
        journal = JournalEntry(
            created_by=request.user,
            base_currency=company.base_currency,
            kind=kind,
            source_type=data.get("source_type", kind) if trusted else kind,
            source_id=data.get("source_id", "initial" if kind == "opening" else str(uuid.uuid4()))
            if trusted
            else ("initial" if kind == "opening" else str(uuid.uuid4())),
            source_action=data.get("source_action", "post") if trusted else "post",
        )
    elif not trusted and journal.source_type not in ("manual", "opening", "adjustment"):
        raise BusinessRuleViolation("Edit this source through its owning workflow.")
    for key in ("posting_date", "description", "reason"):
        if key in data:
            setattr(journal, key, data[key])
    journal.journal_date = data.get("journal_date", journal.posting_date)
    if not journal.description.strip():
        raise ValidationError({"description": "Enter a narration."})
    if "adjustment_of" in data:
        if (
            data["adjustment_of"]
            and not JournalEntry.objects.filter(pk=data["adjustment_of"], status="posted").exists()
        ):
            raise ValidationError({"adjustment_of": "Select a posted original journal."})
        journal.adjustment_of_id = data["adjustment_of"]
    if trusted:
        journal.reversal_of_id = data.get("reversal_of")
    lines = build_lines(
        data["lines"],
        company,
        journal.posting_date,
        trusted=trusted,
        reversal=bool(journal.reversal_of_id),
    )
    if authority is None and any(line.account.control in SUBLEDGER_CONTROLS for line in lines):
        raise BusinessRuleViolation(
            "Receivable, payable and customer-credit control accounts accept postings only "
            "from Sales & Billing and Purchases.",
            code="subledger_control",
        )
    if not new:
        journal.revision += 1
    journal.save()
    journal.lines.all().delete()
    for line in lines:
        line.journal = journal
    JournalLine.objects.bulk_create(lines)
    record(
        "accounting.draft_created" if new else "accounting.draft_updated",
        request=request,
        target=journal,
        after={"revision": journal.revision, "lines": len(lines)},
    )
    return journal


def validation(journal):
    lines = list(journal.lines.all())
    debit = sum((line.base_debit for line in lines), ZERO)
    credit = sum((line.base_credit for line in lines), ZERO)
    errors = []
    if len(lines) < 2:
        errors.append("At least two meaningful lines are required.")
    if debit != credit or debit <= 0:
        errors.append("Base debits must equal base credits exactly and be positive.")
    period = AccountingPeriod.objects.filter(
        start__lte=journal.posting_date,
        end__gte=journal.posting_date,
        is_closed=False,
        fiscal_year__is_closed=False,
    ).first()
    if not period:
        errors.append("The posting date must belong to an open accounting period.")
    return strings(
        {
            "debit": debit,
            "credit": credit,
            "difference": debit - credit,
            "balanced": not errors,
            "errors": errors,
        }
    )


def _check_carrying(journal):
    if journal.reversal_of_id:
        company = lock_company()
        from apps.banking.models import BankAccount

        for account_id in BankAccount.objects.exclude(currency=company.base_currency).values_list(
            "gl_account_id", flat=True
        ):
            movements = journal.lines.filter(account_id=account_id)
            if not movements.exists():
                continue
            units, book = bank_position(account_id)
            units += sum((line.debit - line.credit for line in movements), ZERO)
            book += sum((line.base_debit - line.base_credit for line in movements), ZERO)
            if units < 0 or book < 0 or (units == 0 and book != 0):
                raise BusinessRuleViolation(
                    "This reversal would leave an unvalued foreign bank balance. "
                    "Reverse dependent movements first."
                )
        return
    company = lock_company()
    recomputed = build_lines(
        [line_payload(line) for line in journal.lines.all()], company, journal.posting_date
    )
    for old, current in zip(journal.lines.all(), recomputed, strict=True):
        if old.valuation == "carrying" and old.base_credit != current.base_credit:
            raise BusinessRuleViolation(
                "Book value changed since review. Re-save and resubmit this draft.",
                code="stale_valuation",
            )


def _finalize(request, journal):
    company = lock_company()
    from apps.banking.models import Reconciliation

    if Reconciliation.objects.filter(
        is_complete=True,
        statement__end__gte=journal.posting_date,
        statement__bank_account__gl_account_id__in=journal.lines.values("account_id"),
    ).exists():
        raise BusinessRuleViolation(
            "Reopen the affected bank reconciliation before posting into its history."
        )
    if journal.base_currency != company.base_currency:
        raise BusinessRuleViolation("The draft base currency changed. Recreate the draft.")
    check = validation(journal)
    if check["errors"]:
        raise ValidationError({"lines": check["errors"]})
    _check_carrying(journal)
    domain = _owned_by_domain(journal)
    for line in journal.lines.select_related("account"):
        if not line.account.is_active or not line.account.is_postable:
            raise BusinessRuleViolation("A journal account is no longer postable.")
        if not domain and line.account.control in SUBLEDGER_CONTROLS:
            raise BusinessRuleViolation(
                "Subledger control accounts accept postings only from their owning workflow.",
                code="subledger_control",
            )
    period = AccountingPeriod.objects.select_for_update().get(
        start__lte=journal.posting_date, end__gte=journal.posting_date
    )
    seq, _ = JournalSequence.objects.get_or_create(year=journal.posting_date.year)
    seq = JournalSequence.objects.select_for_update().get(pk=seq.pk)
    seq.last_value += 1
    seq.save()
    journal.number = render_number(
        get_business_settings().numbering["journal"], journal.posting_date, seq.last_value
    )
    journal.period = period
    journal.status = "posted"
    journal.posted_at = timezone.now()
    journal.posted_by = request.user
    journal.save()
    record(
        "accounting.journal_reversed" if journal.reversal_of_id else "accounting.journal_posted",
        request=request,
        target=journal,
        after={
            "number": journal.number,
            "source": journal.source_type,
            "reversal_of": str(journal.reversal_of_id) if journal.reversal_of_id else None,
        },
        reason=journal.reason,
    )
    return journal


@transaction.atomic
def post_draft(request, pk, key, *, authority=None):
    _require_poster(request, authority)
    lock_company()
    if not isinstance(key, str) or not 8 <= len(key) <= 160:
        raise ValidationError({"posting_key": "Supply a stable posting key of 8–160 characters."})
    journal = JournalEntry.objects.select_for_update().filter(pk=pk).first()
    if journal is None:
        raise NotFound()
    payload = snapshot(journal)
    digest = fingerprint(payload)
    identity = PostingIdentity.objects.filter(key=key).first()
    if identity:
        if identity.journal_id != journal.pk or identity.fingerprint != digest:
            raise BusinessRuleViolation(
                "The posting key was used for different content.", code="idempotency_conflict"
            )
        return journal, True
    if journal.status in ("posted", "pending"):
        PostingIdentity.objects.create(key=key, fingerprint=digest, journal=journal)
        return journal, True
    check = validation(journal)
    if check["errors"]:
        raise ValidationError({"lines": check["errors"]})
    _check_carrying(journal)
    # Domain adapters apply their own approval policy before posting.
    policy = None if authority else approvals.policy_for_action("accounting.post")
    needs = (
        policy
        and policy.in_force
        and (policy.amount_threshold is None or Decimal(check["debit"]) >= policy.amount_threshold)
    )
    if needs and journal.kind != "transfer":
        approval = approvals.submit(
            request,
            action="accounting.post",
            subject_key=str(journal.pk),
            title=f"Post journal — {journal.description}"[:200],
            payload=payload,
            reason=journal.reason,
        )
        journal.approval = approval
        journal.status = "pending"
        journal.save()
    else:
        _finalize(request, journal)
    PostingIdentity.objects.create(key=key, fingerprint=digest, journal=journal)
    return journal, False


def execute_approved(request, approval, approver):
    require(approver, "finance.view", "accounting.approve", "accounting.manage")
    # Requester must still be allowed to initiate the posting.
    require(approval.requested_by, "finance.view", "accounting.manage")
    if approval.requested_by.must_change_password:
        raise PermissionDenied("The requester must complete their required password change first.")
    lock_company()
    journal = JournalEntry.objects.select_for_update().get(pk=approval.payload["journal_id"])
    if fingerprint(snapshot(journal)) != fingerprint(approval.payload):
        raise BusinessRuleViolation("The journal no longer matches the approved snapshot.")
    _finalize(request, journal)
    return f"journal:{journal.pk}"


@transaction.atomic
def reverse(request, pk, on, reason, key, *, authority=None):
    _require_poster(request, authority)
    lock_company()
    original = JournalEntry.objects.filter(pk=pk, status="posted").first()
    if not original:
        raise NotFound()
    from apps.assets.models import Asset

    if Asset.objects.filter(source_line__journal=original, cancellation__isnull=True).exists():
        raise BusinessRuleViolation(
            "This acquisition has been capitalized. Use a documented asset "
            "correction/disposal before reversing its financial source."
        )
    if Asset.objects.filter(source_line__journal=original, cancellation__date__gt=on).exists():
        raise BusinessRuleViolation(
            "The acquisition reversal cannot precede its retained capitalization reversals."
        )
    if authority is None and is_domain_source(original.source_type):
        raise BusinessRuleViolation(
            "Reverse this entry through its owning workflow.", code="domain_owned"
        )
    if authority is not None:
        authority.verify(request.user, original.source_type)
    existing = JournalEntry.objects.filter(reversal_of=original).first()
    if existing:
        if existing.posting_date != on or existing.reason != reason:
            raise BusinessRuleViolation(
                "The reversal already exists with different details.", code="idempotency_conflict"
            )
        if existing.status == "pending" and existing.approval.status in ("rejected", "cancelled"):
            payload = snapshot(existing)
            existing = save_draft(
                request,
                {**payload, "reversal_of": original.pk},
                existing.pk,
                trusted=True,
                authority=authority,
            )
        return post_draft(request, existing.pk, key, authority=authority)[0]
    if not reason.strip():
        raise ValidationError({"reason": "Explain the reversal."})
    from apps.banking.models import LedgerMatch

    if LedgerMatch.objects.filter(
        line__journal=original, is_active=True, group__reconciliation__is_complete=True
    ).exists():
        raise BusinessRuleViolation(
            "Reopen and unmatch the completed bank reconciliation before reversal."
        )
    lines = []
    for line in original.lines.all():
        p = line_payload(line)
        p["debit"], p["credit"] = p["credit"], p["debit"]
        p["base_debit"], p["base_credit"] = p["base_credit"], p["base_debit"]
        p["valuation"] = "reversal"
        lines.append(p)
    journal = save_draft(
        request,
        {
            "posting_date": on,
            "description": f"Reversal: {original.number}",
            "kind": "reversal",
            "source_type": "reversal",
            "source_id": str(original.pk),
            "reversal_of": original.pk,
            "reason": reason,
            "lines": lines,
        },
        trusted=True,
        authority=authority,
    )
    return post_draft(request, journal.pk, key, authority=authority)[0]


def post_journal(
    *,
    actor,
    posting_key,
    source_type,
    source_id,
    source_action,
    posting_date,
    description,
    lines,
    journal_date=None,
    draft_id=None,
    reversal_of=None,
    adjustment_of=None,
    reason="",
    request_context=None,
    authority=None,
):
    """Internal adapter contract. No public endpoint accepts trusted source identities.

    Without ``authority`` the caller needs ``accounting.manage`` (Phase 3 behaviour).
    Domain adapters pass the ``PostingAuthority`` from ``adapters.authorize`` instead.
    """
    request = request_context or SimpleNamespace(user=actor, META={})
    with transaction.atomic():
        if authority is None:
            require(actor, "accounting.manage")
            if is_domain_source(source_type):
                raise PermissionDenied("Domain sources post through their owning workflow.")
        else:
            authority.verify(actor, source_type, source_action)
        lock_company()
        supplied = strings(
            {
                "source_type": source_type,
                "source_id": str(source_id),
                "source_action": source_action,
                "posting_date": posting_date,
                "description": description,
                "lines": lines,
                "reason": reason,
                "journal_date": journal_date or posting_date,
                "reversal_of": reversal_of,
                "adjustment_of": adjustment_of,
            }
        )
        existing = JournalEntry.objects.filter(
            source_type=source_type, source_id=str(source_id), source_action=source_action
        ).first()
        if draft_id is not None and (existing is None or str(existing.pk) != str(draft_id)):
            raise BusinessRuleViolation("Draft does not belong to this source identity.")
        # Retain the request fingerprint separately from the converted line amounts.
        if existing:
            first = existing.lines.first()
            if first and first.dimensions.get("_source_fingerprint") != fingerprint(supplied):
                raise BusinessRuleViolation(
                    "Source identity conflicts with the existing posting.",
                    code="idempotency_conflict",
                )
            return post_draft(request, existing.pk, posting_key, authority=authority)[0]
        raw = [
            {
                **line,
                "dimensions": {
                    **line.get("dimensions", {}),
                    "_source_fingerprint": fingerprint(supplied),
                },
            }
            for line in lines
        ]
        journal = save_draft(
            request,
            {
                **supplied,
                "source_id": str(source_id),
                "lines": raw,
                "kind": source_type,
                "journal_date": journal_date or posting_date,
                "reversal_of": reversal_of,
                "adjustment_of": adjustment_of,
            },
            trusted=True,
            authority=authority,
        )
        journal = post_draft(request, journal.pk, posting_key, authority=authority)[0]
        if authority is not None and journal.status != "posted":
            raise BusinessRuleViolation("The domain posting did not complete.")
        return journal


def balance_with_fx(raw, company, on):
    """Build lines and append the explicit realized FX difference line when needed.

    Returns ``(raw_lines, built_lines, difference, fx_account)``. Treasury and the
    settlement adapters share it so every realized FX line is derived the same way.
    """
    built = build_lines(raw, company, on, trusted=True)
    difference = sum((line.base_debit - line.base_credit for line in built), ZERO)
    extra = None
    if difference:
        control = "fx_gain" if difference > 0 else "fx_loss"
        extra = Account.objects.filter(control=control, is_active=True, is_postable=True).first()
        if not extra:
            raise BusinessRuleViolation(f"Configure an active {control} control account first.")
        raw = [
            *raw,
            {
                "account_id": extra.pk,
                "currency": company.base_currency,
                "credit" if difference > 0 else "debit": str(abs(difference)),
                "description": "Explicit realized FX difference",
            },
        ]
        built = build_lines(raw, company, on, trusted=True)
    return raw, built, difference, extra
