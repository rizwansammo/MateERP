"""Source-linked assets, prospective estimates and immutable actual depreciation."""

import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext

from django.db import transaction
from django.db.models import CharField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError

from apps.accounting.models import Account, JournalLine
from apps.accounting.money import ZERO, money, quantum, strings
from apps.accounting.services.adapters import authorize
from apps.accounting.services.posting import post_journal
from apps.accounting.services.setup import lock_company
from apps.accounts.authorization import get_permission_codes, require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.company.services import is_module_enabled
from apps.core.exceptions import BusinessRuleViolation
from apps.inventory.services import control, fingerprint
from apps.sales.services import _get

from .models import (
    Asset,
    AssetAction,
    AssetDisposal,
    AssetEstimate,
    AssetEvidence,
    CapitalizationReversal,
    DepreciationCharge,
)


def on_date(value):
    return date.fromisoformat(value) if isinstance(value, str) else value


def month_start(on):
    return on.replace(day=1)


def month_end(on):
    return on.replace(day=calendar.monthrange(on.year, on.month)[1])


def add_months(on, n):
    year, month = divmod(on.year * 12 + on.month - 1 + n, 12)
    return date(year, month + 1, min(on.day, calendar.monthrange(year, month + 1)[1]))


def accumulated(asset):
    return asset.charges.aggregate(v=Sum("amount"))["v"] or ZERO


def _expense_account(pk):
    obj = _get(Account, pk)
    if obj.control or obj.account_type != "expense" or not obj.is_active or not obj.is_postable:
        raise ValidationError({"account_id": "Choose an active, unprotected expense account."})
    return obj


def acquisition_lines(user):
    from apps.founders.models import CorporateTransaction
    from apps.purchasing.models import Expense, VendorBill

    qs = JournalLine.objects.filter(
        journal__status="posted",
        base_debit__gt=0,
        journal__source_type__in=["vendor_bill", "expense", "founder_transaction"],
        account__control="",
        account__account_type__in=["asset", "expense"],
        journal__reversed_by__isnull=True,
    )
    if "founder.view" not in get_permission_codes(user):
        qs = qs.exclude(journal__source_type="founder_transaction")
    return qs.annotate(
        source_reference=Coalesce(
            Subquery(
                VendorBill.objects.filter(journal_id=OuterRef("journal_id")).values(
                    "vendor_reference"
                )[:1]
            ),
            Subquery(
                Expense.objects.filter(journal_id=OuterRef("journal_id")).values("reference")[:1]
            ),
            Subquery(
                CorporateTransaction.objects.filter(journal_id=OuterRef("journal_id")).values(
                    "reference"
                )[:1]
            ),
            Value(""),
            output_field=CharField(),
        )
    ).select_related("journal", "account")


def available_acquisition(line):
    claimed = (
        line.capitalizations.filter(cancellation__isnull=True).aggregate(v=Sum("cost"))["v"] or ZERO
    )
    return line.base_debit - line.base_credit - claimed


def _journal(request, action, on, description, raw, original_date=None):
    return post_journal(
        actor=request.user,
        authority=authorize(request.user, "asset_event", "post"),
        request_context=request,
        source_type="asset_event",
        source_id=action.pk,
        source_action="post",
        posting_key=f"asset:{action.key}",
        posting_date=on,
        journal_date=original_date or on,
        description=description[:500],
        lines=raw,
    )


def _line(account_id, base, value, description=""):
    return {
        "account_id": account_id,
        "currency": base,
        "debit" if value > 0 else "credit": str(abs(value)),
        "description": description[:300],
    }


def _capitalize(request, action):
    data = action.payload
    company = lock_company()
    line = acquisition_lines(request.user).filter(pk=data["source_line_id"]).first()
    if line is None:
        raise ValidationError(
            {
                "source_line_id": "Choose a posted, unreversed purchasing or founder debit, "
                "excluding inventory and recoverable tax."
            }
        )
    cost = money(data["cost"], company.base_currency)
    if cost <= 0 or cost > available_acquisition(line):
        raise BusinessRuleViolation(
            "Capitalization exceeds the unclaimed historical acquisition cost."
        )
    from apps.sales.calculation import allocate

    claimed_native = ZERO
    for previous in line.capitalizations.filter(cancellation__isnull=True):
        if "claimed_native_cost" not in previous.source_snapshot:
            raise BusinessRuleViolation(
                "Review the remaining native cost of this older source before "
                "another partial capitalization."
            )
        claimed_native += Decimal(previous.source_snapshot["claimed_native_cost"])
    native_remaining = line.debit - claimed_native
    base_remaining = available_acquisition(line)
    native_cost = allocate(native_remaining, [cost, base_remaining - cost], line.currency)[0]
    if line.account.account_type == "expense":
        require(request.user, "accounting.manage")
    recognition = on_date(data["recognition_date"])
    latest_release = (
        CapitalizationReversal.objects.filter(asset__source_line=line)
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )
    if latest_release and recognition < latest_release:
        raise BusinessRuleViolation(
            "A replacement capitalization cannot precede the retained source-claim reversal."
        )
    acquired = line.journal.journal_date
    service = on_date(data["in_service_date"])
    if recognition < line.journal.posting_date or service < acquired:
        raise ValidationError(
            {
                "recognition_date": "Recognition cannot precede its posted acquisition; "
                "service cannot precede acquisition."
            }
        )
    expense = _expense_account(data["depreciation_account_id"])
    residual = money(data["residual"], company.base_currency)
    if residual < 0 or residual > cost:
        raise ValidationError({"residual": "Residual must be between zero and historical cost."})
    journal = _journal(
        request,
        action,
        recognition,
        f"Capitalize {data['tag']}: {data['reason']}",
        [
            _line(control("fixed_assets").pk, company.base_currency, cost),
            _line(line.account_id, company.base_currency, -cost),
        ],
        acquired,
    )
    asset = Asset(
        source_line=line,
        acquisition_date=acquired,
        recognition_date=recognition,
        in_service_date=service,
        cost=cost,
        depreciation_account=expense,
        journal=journal,
        source_snapshot=strings(
            {
                "journal_id": line.journal_id,
                "journal_number": line.journal.number,
                "source_type": line.journal.source_type,
                "account_code": line.account.code,
                "currency": line.currency,
                "exchange_rate": line.exchange_rate,
                "original_debit": line.debit,
                "original_base_debit": line.base_debit,
                "claimed_native_cost": native_cost,
                "depreciation_method": "straight_line",
                "reclassification_reason": data["reason"],
            }
        ),
        created_by=request.user,
        **{
            k: data.get(k, "")
            for k in (
                "tag",
                "name",
                "category",
                "description",
                "serial_number",
                "location",
                "custodian_reference",
            )
        },
    )
    asset.tag = asset.tag.strip().upper()
    asset.full_clean()
    asset.save()
    estimate = AssetEstimate(
        asset=asset,
        version=1,
        effective_date=service,
        remaining_months=data["useful_life_months"],
        residual=residual,
        carrying_basis=cost,
        reason=data["reason"],
        created_by=request.user,
    )
    estimate.full_clean()
    estimate.save()
    record(
        "asset.capitalized",
        request=request,
        target=asset,
        after={"cost": cost, "source_line": line.pk, "journal": journal.pk},
        reason=data["reason"],
    )
    return str(asset.pk)


def schedule(asset):
    from apps.company.models import CompanyProfile

    if CapitalizationReversal.objects.filter(asset=asset).exists():
        return []

    base = CompanyProfile.objects.get(pk=1).base_currency
    estimates = list(asset.estimates.order_by("version"))
    actual = {c.month: c for c in asset.charges.all()}
    out = []
    for index, estimate in enumerate(estimates):
        stop = estimates[index + 1].effective_date if index + 1 < len(estimates) else None
        total = estimate.carrying_basis - estimate.residual
        partial = estimate.effective_date.day != 1
        months = estimate.remaining_months + int(partial)
        left = total
        with localcontext() as ctx:
            ctx.prec = 60
            monthly = total / estimate.remaining_months
            for n in range(months):
                first = add_months(month_start(estimate.effective_date), n)
                if stop and first >= stop:
                    break
                amount = monthly
                if n == 0 and partial:
                    amount *= Decimal(
                        (month_end(first) - estimate.effective_date).days + 1
                    ) / Decimal(calendar.monthrange(first.year, first.month)[1])
                amount = (
                    min(left, amount.quantize(quantum(base), rounding=ROUND_HALF_UP))
                    if n < months - 1
                    else left
                )
                left -= amount
                posted = actual.get(first)
                out.append(
                    {
                        "month": first,
                        "scheduled": amount,
                        "posted": posted.amount if posted else ZERO,
                        "recognition_date": posted.recognition_date if posted else None,
                        "journal_id": posted.journal_id if posted else None,
                        "estimate_id": estimate.pk,
                        "version": estimate.version,
                    }
                )
    return out


def _active(asset):
    if CapitalizationReversal.objects.filter(asset=asset).exists():
        raise BusinessRuleViolation(
            "This capitalization was reversed. Retain its historical evidence."
        )
    if AssetDisposal.objects.filter(asset=asset).exists():
        raise BusinessRuleViolation(
            "This asset has been disposed. Its historical records remain available."
        )


def _depreciate(request, action):
    data = action.payload
    company = lock_company()
    asset = _get(Asset, data["asset_id"])
    _active(asset)
    pending = [r for r in schedule(asset) if r["scheduled"] > 0 and r["journal_id"] is None]
    month = on_date(data["month"])
    if not pending or pending[0]["month"] != month:
        raise BusinessRuleViolation(
            "Post the earliest unposted scheduled month; charges cannot be skipped or duplicated."
        )
    entry = pending[0]
    recognition = on_date(data["recognition_date"])
    if recognition < month_end(month) or recognition < asset.recognition_date:
        raise ValidationError(
            {
                "recognition_date": "Posting cannot precede the service month end "
                "or asset recognition."
            }
        )
    if recognition != month_end(month):
        require(request.user, "accounting.manage")
    journal = _journal(
        request,
        action,
        recognition,
        f"Depreciation {asset.tag} — {month:%Y-%m}",
        [
            _line(asset.depreciation_account_id, company.base_currency, entry["scheduled"]),
            _line(
                control("accumulated_depreciation").pk, company.base_currency, -entry["scheduled"]
            ),
        ],
        month_end(month),
    )
    charge = DepreciationCharge.objects.create(
        asset=asset,
        estimate_id=entry["estimate_id"],
        month=month,
        amount=entry["scheduled"],
        recognition_date=recognition,
        journal=journal,
        created_by=request.user,
    )
    record(
        "asset.depreciation_posted",
        request=request,
        target=asset,
        after={"month": month, "recognition_date": recognition, "amount": charge.amount},
        reason=data["reason"],
    )
    return str(charge.pk)


def _estimate(request, action):
    data = action.payload
    company = lock_company()
    asset = _get(Asset, data["asset_id"])
    _active(asset)
    effective = on_date(data["effective_date"])
    pending = [r for r in schedule(asset) if r["scheduled"] > 0 and r["journal_id"] is None]
    if (
        effective.day != 1
        or (pending and effective != pending[0]["month"])
        or effective < asset.in_service_date
    ):
        raise BusinessRuleViolation(
            "Prospective estimates start at the first unposted service month. "
            "Retain earlier charges unchanged."
        )
    carrying = asset.cost - accumulated(asset)
    residual = money(data["residual"], company.base_currency)
    if residual > carrying:
        raise ValidationError({"residual": "Residual cannot exceed the remaining carrying amount."})
    latest = asset.estimates.order_by("-version").first()
    obj = AssetEstimate(
        asset=asset,
        version=latest.version + 1,
        effective_date=effective,
        remaining_months=data["remaining_months"],
        residual=residual,
        carrying_basis=carrying,
        reason=data["reason"],
        created_by=request.user,
    )
    obj.full_clean()
    obj.save()
    record(
        "asset.estimate_revised",
        request=request,
        target=asset,
        after={"version": obj.version, "effective_date": effective, "residual": residual},
        reason=data["reason"],
    )
    return str(obj.pk)


def _dispose(request, action):
    from apps.billing.models import Invoice, InvoiceLine
    from apps.sales.calculation import allocate

    data = action.payload
    company = lock_company()
    asset = _get(Asset, data["asset_id"])
    _active(asset)
    on = on_date(data["date"])
    if on < max(asset.recognition_date, asset.in_service_date):
        raise BusinessRuleViolation("Disposal cannot precede capitalization or service.")
    rows = schedule(asset)
    for row in rows:
        if row["month"] < month_start(on) and row["scheduled"] > 0 and row["journal_id"] is None:
            raise BusinessRuleViolation("Post the earlier depreciation months before disposal.")
    if asset.charges.filter(recognition_date__gt=on).exists():
        raise BusinessRuleViolation("Disposal cannot precede an existing depreciation posting.")
    current = next((r for r in rows if r["month"] == month_start(on)), None)
    extra, estimate_id = ZERO, None
    if current:
        if current["journal_id"] and on != month_end(on):
            raise BusinessRuleViolation(
                "A full-month charge exists. Use a month-end disposal or a reviewed correction."
            )
        if current["journal_id"] is None:
            start = max(asset.in_service_date, month_start(on))
            with localcontext() as ctx:
                ctx.prec = 60
                extra = (
                    current["scheduled"]
                    * Decimal((on - start).days + 1)
                    / Decimal((month_end(on) - start).days + 1)
                ).quantize(quantum(company.base_currency), rounding=ROUND_HALF_UP)
            estimate_id = current["estimate_id"]
    prior = accumulated(asset)
    accum = prior + extra
    book = asset.cost - accum
    proceeds, invoice_line = ZERO, None
    revenue_account_id = None
    if data["kind"] == "sale":
        require(request.user, "invoices.issue")
        invoice_line = _get(InvoiceLine, data.get("invoice_line_id"))
        invoice = invoice_line.invoice
        from apps.purchasing.models import Expense, VendorBill

        source_project = (
            Expense.objects.filter(journal_id=asset.source_line.journal_id)
            .values_list("project_id", flat=True)
            .first()
        )
        if source_project is None:
            source_project = (
                VendorBill.objects.filter(journal_id=asset.source_line.journal_id)
                .values_list("project_id", flat=True)
                .first()
            )
        if invoice.project_id is not None and invoice.project_id != source_project:
            raise BusinessRuleViolation(
                "The asset-sale invoice must retain the acquisition project or no "
                "project. Use audited analytical classification for another "
                "management scope."
            )
        if (
            invoice.status not in Invoice.ISSUED_STATES
            or invoice.issue_date != on
            or invoice.amount_credited
            or invoice_line.sales_order_line_id
        ):
            raise BusinessRuleViolation(
                "Select an uncredited, issued asset-sale line on the same effective date, "
                "separate from stock contracts."
            )
        if AssetDisposal.objects.filter(invoice_line=invoice_line).exists():
            raise BusinessRuleViolation("This sale line has already funded another disposal.")
        # Reproduce invoice issuance allocation, which aggregates by account/tax.
        if invoice.sales_order_id:
            raise BusinessRuleViolation(
                "Use a separate asset-sale invoice, without fulfillment contract allocations."
            )
        account_base = (
            invoice.journal.lines.filter(
                account_id=invoice_line.revenue_account_id, tax_revision__isnull=True
            ).aggregate(v=Sum("base_credit"))["v"]
            or ZERO
        )
        siblings = list(
            invoice.lines.filter(revenue_account_id=invoice_line.revenue_account_id).order_by(
                "position"
            )
        )
        amounts = allocate(account_base, [row.taxable for row in siblings], company.base_currency)
        proceeds = amounts[[row.pk for row in siblings].index(invoice_line.pk)]
        revenue_account_id = invoice_line.revenue_account_id
    elif data.get("invoice_line_id"):
        raise ValidationError(
            {"invoice_line_id": "Retirement and write-off do not record sale proceeds."}
        )
    gain = proceeds - book
    if gain > 0 and not data.get("gain_account_id"):
        raise ValidationError({"gain_account_id": "Choose the disposal gain revenue account."})
    if gain < 0 and not data.get("loss_account_id"):
        raise ValidationError({"loss_account_id": "Choose the disposal loss expense account."})
    gain_account = _get(Account, data["gain_account_id"]) if gain > 0 else None
    if gain_account and (
        gain_account.account_type != "revenue"
        or gain_account.control
        or not gain_account.is_active
        or not gain_account.is_postable
    ):
        raise ValidationError(
            {"gain_account_id": "Choose an active unprotected disposal-gain revenue account."}
        )
    loss_account = _expense_account(data["loss_account_id"]) if gain < 0 else None
    raw = [_line(control("fixed_assets").pk, company.base_currency, -asset.cost)]
    for account_id, value in (
        (control("accumulated_depreciation").pk, accum),
        (revenue_account_id, proceeds),
        (loss_account.pk if loss_account else None, -gain if gain < 0 else ZERO),
        (gain_account.pk if gain_account else None, -gain if gain > 0 else ZERO),
        (asset.depreciation_account_id, extra),
        (control("accumulated_depreciation").pk, -extra),
    ):
        if value:
            raw.append(_line(account_id, company.base_currency, value))
    journal = _journal(request, action, on, f"Dispose {asset.tag}: {data['reason']}", raw)
    obj = AssetDisposal.objects.create(
        asset=asset,
        date=on,
        kind=data["kind"],
        invoice_line=invoice_line,
        proceeds_base=proceeds,
        accumulated=accum,
        book_value=book,
        gain_loss=gain,
        journal=journal,
        reason=data["reason"],
        created_by=request.user,
    )
    if extra:
        DepreciationCharge.objects.create(
            asset=asset,
            estimate_id=estimate_id,
            month=month_start(on),
            amount=extra,
            recognition_date=on,
            journal=journal,
            created_by=request.user,
        )
    record(
        "asset.disposed",
        request=request,
        target=asset,
        after={
            "kind": obj.kind,
            "proceeds": proceeds,
            "book_value": book,
            "gain_loss": gain,
            "cash_posted": False,
        },
        reason=data["reason"],
    )
    return str(obj.pk)


@transaction.atomic
def request_action(request, operation, data):
    require(request.user, "assets.manage", "assets.post", "finance.view")
    if operation == "cancel":
        require(request.user, "accounting.manage")
    company = lock_company()
    if not is_module_enabled("assets"):
        raise BusinessRuleViolation(
            "Fixed assets is disabled. Historical registers and reports remain readable."
        )
    digest = fingerprint({"operation": operation, **data})
    previous = AssetAction.objects.filter(key=data["key"]).first()
    if previous:
        if previous.fingerprint != digest:
            raise BusinessRuleViolation("This asset action key belongs to different content.")
        return previous
    value = (
        money(data["cost"], company.base_currency)
        if operation == "capitalize"
        else _get(Asset, data["asset_id"]).cost
    )
    payload = strings(data)
    if operation != "capitalize":
        payload["_basis"] = action_basis(_get(Asset, data["asset_id"]))
    obj = AssetAction.objects.create(
        operation=operation,
        key=data["key"],
        fingerprint=digest,
        payload=payload,
        created_by=request.user,
    )
    policy = approvals.policy_for_action("asset.post")
    if (
        policy
        and policy.in_force
        and (policy.amount_threshold is None or value >= policy.amount_threshold)
    ):
        obj.approval = approvals.submit(
            request,
            action="asset.post",
            title=f"Fixed asset: {operation}",
            subject_key=f"asset:{obj.key}",
            reason=data["reason"][:500],
            payload={"action_id": obj.pk},
        )
        obj.save(update_fields=["approval"])
    else:
        _execute(request, obj)
    return obj


def _execute(request, obj):
    if obj.status != "pending":
        raise BusinessRuleViolation("This asset action is already decided.")
    if (
        obj.operation != "capitalize"
        and action_basis(_get(Asset, obj.payload["asset_id"])) != obj.payload["_basis"]
    ):
        raise BusinessRuleViolation(
            "The asset financial basis changed during review. Withdraw and submit a fresh action."
        )
    obj.result_id = {
        "capitalize": _capitalize,
        "depreciation": _depreciate,
        "estimate": _estimate,
        "disposal": _dispose,
        "cancel": _cancel,
    }[obj.operation](request, obj)
    obj.status = "done"
    obj.save(update_fields=["result_id", "status"])


def action_basis(asset):
    return strings(
        {
            "cost": asset.cost,
            "accumulated": accumulated(asset),
            "estimate_id": asset.estimates.order_by("-version")
            .values_list("pk", flat=True)
            .first(),
            "last_charge_id": asset.charges.order_by("-pk").values_list("pk", flat=True).first(),
            "disposed": AssetDisposal.objects.filter(asset=asset).exists(),
            "cancelled": CapitalizationReversal.objects.filter(asset=asset).exists(),
        }
    )


def execute_approval(request, approval, approver):
    obj = _get(AssetAction, approval.payload["action_id"])
    _execute(request, obj)
    return f"asset:{obj.result_id}"


def _cancel(request, action):
    """Reverse an unused capitalization, preserving the source and every record."""
    from apps.accounting.services.posting import reverse

    require(request.user, "accounting.manage")
    asset = _get(Asset, action.payload["asset_id"])
    _active(asset)
    if asset.charges.exists():
        raise BusinessRuleViolation(
            "Posted depreciation prevents a simple capitalization reversal. "
            "Use the documented disposal/current-period correction workflow."
        )
    on = on_date(action.payload["recognition_date"])
    if on < asset.recognition_date:
        raise ValidationError({"recognition_date": "Reversal cannot precede capitalization."})
    journal = reverse(
        request,
        asset.journal_id,
        on,
        action.payload["reason"],
        f"asset:{action.key}",
        authority=authorize(request.user, "asset_event", "reverse"),
    )
    if journal.status != "posted":
        raise BusinessRuleViolation(
            "Capitalization reversal must finish its domain approval first."
        )
    obj = CapitalizationReversal.objects.create(
        asset=asset,
        date=on,
        journal=journal,
        reason=action.payload["reason"],
        created_by=request.user,
    )
    record(
        "asset.capitalization_reversed",
        request=request,
        target=asset,
        after={"reversal": journal.pk, "source_line": asset.source_line_id},
        reason=obj.reason,
    )
    return str(obj.pk)


def declined(request, approval):
    obj = _get(AssetAction, approval.payload["action_id"])
    obj.status = "rejected"
    obj.save(update_fields=["status"])


def can_read_evidence(user, stored):
    return (
        "finance.view" in get_permission_codes(user)
        and AssetEvidence.objects.filter(file=stored).exists()
    )


@transaction.atomic
def add_evidence(request, asset_id, description, upload):
    from apps.files.services import store_document

    require(request.user, "assets.manage", "documents.manage", "finance.view")
    lock_company()
    asset = _get(Asset, asset_id)
    stored = store_document(upload, purpose="asset_evidence", user=request.user)
    obj = AssetEvidence.objects.create(
        asset=asset, file=stored, description=description, created_by=request.user
    )
    record(
        "asset.evidence_added",
        request=request,
        target=asset,
        after={"file_id": stored.pk},
        reason=description,
    )
    return obj


@transaction.atomic
def update_metadata(request, asset_id, data):
    require(request.user, "assets.manage", "finance.view")
    lock_company()
    asset = _get(Asset, asset_id)
    before = {k: getattr(asset, k) for k in data}
    for key, value in data.items():
        setattr(asset, key, value)
    asset.full_clean()
    asset.save(update_fields=list(data))
    record("asset.metadata_updated", request=request, target=asset, before=before, after=data)
    return asset


def guard_sale_invoice(invoice):
    if AssetDisposal.objects.filter(invoice_line__invoice=invoice).exists():
        raise BusinessRuleViolation(
            "This invoice is retained disposal evidence. Correct the source-owned asset "
            "disposal before changing its proceeds."
        )


@transaction.atomic
def reconciliation():
    from apps.billing.services.reconciliation import gl_balance

    lock_company()
    cost = (
        Asset.objects.filter(disposal__isnull=True, cancellation__isnull=True).aggregate(
            v=Sum("cost")
        )["v"]
        or ZERO
    )
    dep = (
        DepreciationCharge.objects.filter(asset__disposal__isnull=True).aggregate(v=Sum("amount"))[
            "v"
        ]
        or ZERO
    )
    _, gl_cost = gl_balance("fixed_assets", credit_normal=False)
    _, gl_dep = gl_balance("accumulated_depreciation", credit_normal=True)
    return {
        "cost": cost,
        "cost_ledger": gl_cost,
        "cost_difference": gl_cost - cost,
        "depreciation": dep,
        "depreciation_ledger": gl_dep,
        "depreciation_difference": gl_dep - dep,
    }
