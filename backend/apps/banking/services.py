"""Treasury and statement reconciliation; financial effects use the posting service."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounting.models import Account, JournalLine
from apps.accounting.money import ZERO, money, strings
from apps.accounting.services.posting import (
    bank_position,
    build_lines,
    fingerprint,
    line_payload,
    post_journal,
)
from apps.accounting.services.setup import lock_company, rate_for
from apps.accounts.authorization import require
from apps.audit.services import record
from apps.core.exceptions import BusinessRuleViolation

from .models import (
    BankAccount,
    BankStatement,
    LedgerMatch,
    MatchGroup,
    Reconciliation,
    StatementLine,
    StatementMatch,
    TreasuryOperation,
)


@transaction.atomic
def save_account(request, data, pk=None):
    require(request.user, "accounting.manage")
    lock_company()
    obj = BankAccount.objects.filter(pk=pk).first() if pk else BankAccount()
    if obj is None:
        raise NotFound()
    if (
        pk
        and JournalLine.objects.filter(account=obj.gl_account, journal__status="posted").exists()
        and any(
            k in data and data[k] != getattr(obj, k) for k in ("currency", "gl_account_id", "kind")
        )
    ):
        raise BusinessRuleViolation(
            "Bank currency and ledger link are locked by financial history."
        )
    for k, v in data.items():
        setattr(obj, k, v)
    gl = Account.objects.select_for_update().filter(pk=obj.gl_account_id).first()
    if not gl or gl.account_type != "asset" or not gl.is_active or not gl.is_postable:
        raise ValidationError({"gl_account_id": "Select an active postable asset account."})
    if gl.currency and gl.currency != obj.currency:
        raise ValidationError({"currency": "The GL account has a different currency."})
    if gl.journal_lines.filter(journal__status="posted").exclude(currency=obj.currency).exists():
        raise ValidationError({"gl_account_id": "The ledger already contains other currencies."})
    money("0", obj.currency)
    gl.currency = obj.currency
    gl.save()
    obj.full_clean()
    obj.save()
    record(
        "banking.account_updated" if pk else "banking.account_created",
        request=request,
        target=obj,
        after={
            "name": obj.name,
            "currency": obj.currency,
            "is_active": obj.is_active,
            "identifier": "[masked]",
        },
    )
    return obj


def _bank(pk):
    obj = BankAccount.objects.select_for_update().filter(pk=pk, is_active=True).first()
    if not obj:
        raise ValidationError({"bank_account_id": "Select an active bank or cash account."})
    return obj


@transaction.atomic
def treasury(request, data, *, preview=False):
    require(request.user, "accounting.manage")
    company = lock_company()
    key = data["posting_key"]
    raw_fingerprint = fingerprint(
        {k: v for k, v in data.items() if k not in ("preview", "quote_fingerprint", "confirm_fx")}
    )
    existing = TreasuryOperation.objects.filter(reference=key).select_related("journal").first()
    if existing:
        if existing.fingerprint != raw_fingerprint:
            raise BusinessRuleViolation(
                "The posting key refers to different transaction details.",
                code="idempotency_conflict",
            )
        return existing.journal
    bank = _bank(data["bank_account_id"])
    on = data["posting_date"]
    amount = money(data["amount"], bank.currency)
    if amount <= 0:
        raise ValidationError({"amount": "Enter a positive amount."})
    kind = data["kind"]
    fx, src = rate_for(bank.currency, on, company.base_currency)
    bank_line = {
        "account_id": bank.gl_account_id,
        "currency": bank.currency,
        "exchange_rate": str(fx),
        "rate_source": src,
    }
    if kind == "transfer":
        dest = _bank(data["destination_id"])
        if dest.pk == bank.pk:
            raise ValidationError({"destination_id": "Choose a different destination."})
        received = (
            amount
            if bank.currency == dest.currency
            else money(data.get("received_amount"), dest.currency)
        )
        if received <= 0:
            raise ValidationError({"received_amount": "Enter the amount actually received."})
        raw = [
            {**bank_line, "credit": str(amount)},
            {"account_id": dest.gl_account_id, "currency": dest.currency, "debit": str(received)},
        ]
    else:
        if kind not in (
            "deposit",
            "withdrawal",
            "charge",
            "interest",
            "adjustment_in",
            "adjustment_out",
        ):
            raise ValidationError({"kind": "Unknown treasury operation."})
        incoming = kind in ("deposit", "interest", "adjustment_in")
        counter = Account.objects.filter(pk=data.get("counter_account_id")).first()
        if not counter or BankAccount.objects.filter(gl_account=counter).exists():
            raise ValidationError(
                {"counter_account_id": "Choose a non-bank offset. Use Transfer between banks."}
            )
        if kind == "charge" and counter.account_type != "expense":
            raise ValidationError(
                {"counter_account_id": "Bank charges require an expense account."}
            )
        if kind == "interest" and counter.account_type != "revenue":
            raise ValidationError({"counter_account_id": "Interest requires an income account."})
        from apps.accounting.money import convert

        base_amount = convert(amount, fx, company.base_currency)
        raw = [
            {**bank_line, "debit" if incoming else "credit": str(amount)},
            {
                "account_id": counter.pk,
                "currency": company.base_currency,
                "credit" if incoming else "debit": str(base_amount),
            },
        ]
    built = build_lines(raw, company, on)
    difference = sum((line.base_debit - line.base_credit for line in built), ZERO)
    extra = None
    if difference:
        control = "fx_gain" if difference > 0 else "fx_loss"
        extra = Account.objects.filter(control=control, is_active=True, is_postable=True).first()
        if not extra:
            raise BusinessRuleViolation(f"Configure an active {control} control account first.")
        raw.append(
            {
                "account_id": extra.pk,
                "currency": company.base_currency,
                "credit" if difference > 0 else "debit": str(abs(difference)),
                "description": "Explicit realized FX difference",
            }
        )
        built = build_lines(raw, company, on)
    result = strings(
        {
            "lines": [line_payload(line) for line in built],
            "fx_difference": difference,
            "fx_account": str(extra) if extra else None,
            "base_currency": company.base_currency,
        }
    )
    result["quote_fingerprint"] = fingerprint(result)
    if preview:
        return result
    if data.get("quote_fingerprint") and data["quote_fingerprint"] != result["quote_fingerprint"]:
        raise BusinessRuleViolation(
            "Rates or book values changed. Preview the transaction again.", code="stale_quote"
        )
    if difference and not data.get("confirm_fx"):
        raise ValidationError(
            {"confirm_fx": "Review the disclosed FX difference and confirm before posting."}
        )
    journal = post_journal(
        actor=request.user,
        request_context=request,
        posting_key=key,
        source_type="transfer" if kind == "transfer" else "bank_adjustment",
        source_id=key,
        source_action="post",
        posting_date=on,
        description=data["description"],
        lines=raw,
        reason=data.get("reason", ""),
    )
    TreasuryOperation.objects.create(
        reference=key, journal=journal, kind=kind, fingerprint=raw_fingerprint
    )
    record(
        "banking.transaction_recorded",
        request=request,
        target=journal,
        after={"kind": kind, "bank": bank.pk},
    )
    return journal


@transaction.atomic
def create_statement(request, data):
    require(request.user, "accounting.manage")
    lock_company()
    bank = _bank(data["bank_account_id"])
    start, end = data["start"], data["end"]
    if end < start:
        raise ValidationError({"end": "End precedes start."})
    if BankStatement.objects.filter(bank_account=bank, start__lte=end, end__gte=start).exists():
        raise BusinessRuleViolation("Statement ranges for this account cannot overlap.")
    opening = money(data["opening_balance"], bank.currency, signed=True)
    closing = money(data["closing_balance"], bank.currency, signed=True)
    previous = BankStatement.objects.filter(bank_account=bank).order_by("-end").first()
    expected = (
        previous.closing_balance
        if previous
        else bank_position(bank.gl_account_id, before=start - timezone.timedelta(days=1))[0]
    )
    if previous and start != previous.end + timezone.timedelta(days=1):
        raise ValidationError({"start": "Enter sequential, contiguous statement ranges."})
    if opening != expected:
        raise ValidationError(
            {
                "opening_balance": "Use the previous statement closing, or the initial "
                "ledger balance before this range."
            }
        )
    lines = []
    for i, line in enumerate(data["lines"], 1):
        amt = money(line["amount"], bank.currency, signed=True)
        if not start <= line["date"] <= end or amt == 0:
            raise ValidationError(
                {"lines": "Statement lines need nonzero amounts and dates inside the range."}
            )
        lines.append(
            StatementLine(
                position=i,
                date=line["date"],
                description=line["description"],
                reference=line.get("reference", ""),
                amount=amt,
            )
        )
    if opening + sum((line.amount for line in lines), ZERO) != closing:
        raise ValidationError(
            {"closing_balance": "Opening plus signed statement lines must equal closing."}
        )
    statement = BankStatement.objects.create(
        bank_account=bank,
        reference=data["reference"],
        start=start,
        end=end,
        opening_balance=opening,
        closing_balance=closing,
    )
    for line in lines:
        line.statement = statement
    StatementLine.objects.bulk_create(lines)
    obj = Reconciliation.objects.create(statement=statement)
    record(
        "banking.statement_created", request=request, target=statement, after={"lines": len(lines)}
    )
    return obj


def ledger_unmatched(rec):
    stmt = rec.statement
    baseline = (
        BankStatement.objects.filter(bank_account=stmt.bank_account).order_by("start").first().start
    )
    return (
        JournalLine.objects.filter(
            account=stmt.bank_account.gl_account,
            journal__status="posted",
            journal__posting_date__lte=stmt.end,
            journal__posting_date__gte=baseline,
        )
        .exclude(
            matches__is_active=True, matches__group__reconciliation__statement__end__lte=stmt.end
        )
        .select_related("journal")
        .order_by("journal__posting_date", "pk")
    )


@transaction.atomic
def match(request, pk, statement_ids, ledger_ids):
    require(request.user, "accounting.manage")
    lock_company()
    rec = Reconciliation.objects.select_for_update().get(pk=pk)
    if Reconciliation.objects.filter(
        statement__bank_account=rec.statement.bank_account,
        statement__end__lt=rec.statement.start,
        is_complete=False,
    ).exists():
        raise BusinessRuleViolation("Complete earlier statement reconciliations first.")
    if rec.is_complete:
        raise BusinessRuleViolation("Reopen this reconciliation before modifying matches.")
    ss = list(rec.statement.lines.filter(pk__in=statement_ids).exclude(matches__is_active=True))
    ll = list(ledger_unmatched(rec).filter(pk__in=ledger_ids))
    if not ss or not ll or len(ss) != len(set(statement_ids)) or len(ll) != len(set(ledger_ids)):
        raise ValidationError(
            {"lines": "Select unmatched lines belonging to this account and statement."}
        )
    if any(line.currency != rec.statement.bank_account.currency for line in ll):
        raise ValidationError({"currency": "Currencies differ."})
    if sum((s.amount for s in ss), ZERO) != sum((line.debit - line.credit for line in ll), ZERO):
        raise ValidationError({"lines": "Matched signed amounts must agree exactly."})
    group = MatchGroup.objects.create(reconciliation=rec, created_by=request.user)
    StatementMatch.objects.bulk_create([StatementMatch(group=group, line=s) for s in ss])
    LedgerMatch.objects.bulk_create([LedgerMatch(group=group, line=line) for line in ll])
    record(
        "banking.matched",
        request=request,
        target=group,
        after={"statement_lines": statement_ids, "ledger_lines": ledger_ids},
    )
    return group


@transaction.atomic
def unmatch(request, pk):
    require(request.user, "accounting.manage")
    lock_company()
    group = MatchGroup.objects.select_related("reconciliation").get(pk=pk)
    if group.reconciliation.is_complete:
        raise BusinessRuleViolation("Reopen the reconciliation first.")
    group.statement_members.update(is_active=False)
    group.ledger_members.update(is_active=False)
    group.is_active = False
    group.save()
    record("banking.unmatched", request=request, target=group)


@transaction.atomic
def auto_match(request, pk):
    require(request.user, "accounting.manage")
    lock_company()
    rec = Reconciliation.objects.get(pk=pk)
    n = 0
    for s in rec.statement.lines.exclude(matches__is_active=True):
        candidates = [
            line
            for line in ledger_unmatched(rec)
            if line.debit - line.credit == s.amount
            and abs((line.journal.posting_date - s.date).days) <= 5
        ]
        # Skip ambiguity on either side; don't pick a convenient equal amount.
        if len(candidates) == 1:
            line = candidates[0]
            similar = [
                x
                for x in rec.statement.lines.exclude(matches__is_active=True)
                if x.amount == s.amount and abs((line.journal.posting_date - x.date).days) <= 5
            ]
            if len(similar) == 1:
                match(request, pk, [s.pk], [line.pk])
                n += 1
    return n


def reconciliation_summary(rec):
    stmt = rec.statement
    native, base = bank_position(stmt.bank_account.gl_account_id, before=stmt.end)
    outstanding = list(ledger_unmatched(rec))
    outstanding_net = sum((line.debit - line.credit for line in outstanding), ZERO)
    unmatched = stmt.lines.exclude(matches__is_active=True).count()
    return strings(
        {
            "ledger_balance": native,
            "base_balance": base,
            "statement_balance": stmt.closing_balance,
            "outstanding_net": outstanding_net,
            "difference": native - stmt.closing_balance - outstanding_net,
            "unmatched_statement": unmatched,
            "unmatched_ledger": len(outstanding),
        }
    )


@transaction.atomic
def complete(request, pk, *, reopen=False, reason=""):
    require(request.user, "accounting.manage")
    lock_company()
    rec = Reconciliation.objects.select_for_update().get(pk=pk)
    if reopen:
        require(request.user, "accounting.periods.manage")
        if not reason.strip():
            raise ValidationError({"reason": "Explain reopening."})
        if Reconciliation.objects.filter(
            statement__bank_account=rec.statement.bank_account,
            statement__start__gt=rec.statement.end,
            is_complete=True,
        ).exists():
            raise BusinessRuleViolation("Reopen later reconciliations first.")
        rec.is_complete = False
    else:
        if Reconciliation.objects.filter(
            statement__bank_account=rec.statement.bank_account,
            statement__end__lt=rec.statement.start,
            is_complete=False,
        ).exists():
            raise BusinessRuleViolation("Complete earlier statement reconciliations first.")
        check = reconciliation_summary(rec)
        if (
            check["unmatched_statement"]
            or money(check["difference"], rec.statement.bank_account.currency, signed=True) != 0
        ):
            raise BusinessRuleViolation(
                "Resolve statement items and the reconciliation difference first."
            )
        rec.is_complete = True
        rec.completed_at = timezone.now()
        rec.completed_by = request.user
    rec.evidence = [
        *rec.evidence,
        {
            "action": "reopened" if reopen else "completed",
            "by": request.user.pk,
            "at": timezone.now().isoformat(),
            "reason": reason,
            "summary": reconciliation_summary(rec),
        },
    ]
    rec.save()
    record(
        "banking.reconciliation_reopened" if reopen else "banking.reconciliation_completed",
        request=request,
        target=rec,
        reason=reason,
    )
    return rec
