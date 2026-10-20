import calendar
from datetime import date

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.authorization import require
from apps.audit.services import record
from apps.company.models import CompanyProfile
from apps.company.services import get_business_settings
from apps.core.exceptions import BusinessRuleViolation

from ..models import (
    Account,
    AccountingPeriod,
    ExchangeRate,
    FiscalYear,
    TaxCode,
    TaxRevision,
)
from ..money import decimal, quantum, strings

STARTER = [
    ("1000", "Assets", "asset", "", False, ""),
    ("1010", "Cash", "asset", "1000", True, ""),
    ("1020", "Bank", "asset", "1000", True, ""),
    ("1100", "Accounts receivable", "asset", "1000", True, ""),
    ("1150", "Input tax", "asset", "1000", True, ""),
    ("2000", "Liabilities", "liability", "", False, ""),
    ("2010", "Accounts payable", "liability", "2000", True, ""),
    ("2100", "Output tax", "liability", "2000", True, ""),
    ("3000", "Equity", "equity", "", False, ""),
    ("3010", "Owner capital", "equity", "3000", True, ""),
    ("3100", "Retained earnings", "equity", "3000", True, "retained_earnings"),
    ("4000", "Income", "revenue", "", False, ""),
    ("4100", "Sales revenue", "revenue", "4000", True, ""),
    ("4900", "Interest income", "revenue", "4000", True, ""),
    ("4950", "Exchange gains", "revenue", "4000", True, "fx_gain"),
    ("5000", "Expenses", "expense", "", False, ""),
    ("5100", "Cost of sales", "expense", "5000", True, ""),
    ("6100", "Operating expenses", "expense", "5000", True, ""),
    ("6200", "Bank charges", "expense", "5000", True, ""),
    ("6950", "Exchange losses", "expense", "5000", True, "fx_loss"),
]


def lock_company():
    obj = CompanyProfile.objects.select_for_update().filter(pk=1).first()
    if obj is None:
        raise BusinessRuleViolation("Set up the company profile first.", code="company_required")
    return obj


@transaction.atomic
def save_account(request, data, pk=None):
    require(request.user, "accounting.manage")
    lock_company()
    obj = Account.objects.select_for_update().filter(pk=pk).first() if pk else Account()
    if obj is None:
        raise NotFound()
    historical = bool(pk and obj.journal_lines.filter(journal__status="posted").exists())
    immutable = (
        "code",
        "account_type",
        "normal_side",
        "parent_id",
        "currency",
        "is_postable",
        "control",
        "subtype",
    )
    if historical and any(k in data and data[k] != getattr(obj, k) for k in immutable):
        raise BusinessRuleViolation(
            "This change would reinterpret posted history.", code="account_history_locked"
        )
    if pk and obj.control and any(k in data and data[k] != getattr(obj, k) for k in immutable):
        raise BusinessRuleViolation("Protected control-account settings cannot change.")
    for k, v in data.items():
        setattr(obj, k, v)
    if not obj.normal_side:
        obj.normal_side = "debit" if obj.account_type in ("asset", "expense") else "credit"
    control_types = {"fx_gain": "revenue", "fx_loss": "expense", "retained_earnings": "equity"}
    if obj.control and (
        obj.control not in control_types or control_types[obj.control] != obj.account_type
    ):
        raise ValidationError(
            {"control": "Choose a control purpose compatible with the account type."}
        )
    if obj.currency:
        quantum(obj.currency)
    parent = Account.objects.filter(pk=obj.parent_id).first() if obj.parent_id else None
    seen = {obj.pk} if obj.pk else set()
    while parent:
        if parent.pk in seen or parent.account_type != obj.account_type or parent.is_postable:
            raise ValidationError(
                {"parent_id": "Choose a summary parent of the same type without a cycle."}
            )
        seen.add(parent.pk)
        parent = parent.parent
    if obj.is_postable and pk and obj.account_set.exists():
        raise ValidationError(
            {"is_postable": "An account with children must remain a summary account."}
        )
    if pk and obj.account_set.exclude(account_type=obj.account_type).exists():
        raise ValidationError(
            {"account_type": "A summary and its children must have the same type."}
        )
    obj.full_clean()
    obj.save()
    record("account.updated" if pk else "account.created", request=request, target=obj, after=data)
    return obj


@transaction.atomic
def setup_chart(request):
    require(request.user, "accounting.manage")
    lock_company()
    # Never silently overwrite a company's existing chart.
    if Account.objects.exists():
        expected = {r[0] for r in STARTER}
        if set(Account.objects.values_list("code", flat=True)) == expected:
            return list(Account.objects.all())
        raise BusinessRuleViolation("A chart already exists. Add accounts individually instead.")
    created = {}
    for code, name, typ, parent, postable, control in STARTER:
        created[code] = save_account(
            request,
            {
                "code": code,
                "name": name,
                "account_type": typ,
                "normal_side": "debit" if typ in ("asset", "expense") else "credit",
                "parent_id": created[parent].pk if parent else None,
                "is_postable": postable,
                "control": control,
                "subtype": "Cost of sales" if code == "5100" else typ.title(),
            },
        )
    return list(created.values())


@transaction.atomic
def create_year(request, start):
    require(request.user, "accounting.manage")
    company = lock_company()
    if start.day != 1 or start.month != company.fiscal_year_start_month:
        raise ValidationError({"start": "Use the first day of the company's fiscal start month."})
    end = date(start.year + 1, start.month, 1) - timezone.timedelta(days=1)
    if FiscalYear.objects.filter(start__lte=end, end__gte=start).exists():
        raise BusinessRuleViolation("Fiscal years cannot overlap.")
    year = FiscalYear.objects.create(name=f"FY {start.year}/{end.year}", start=start, end=end)
    for offset in range(12):
        month = (start.month - 1 + offset) % 12 + 1
        y = start.year + (start.month - 1 + offset) // 12
        AccountingPeriod.objects.create(
            fiscal_year=year,
            start=date(y, month, 1),
            end=date(y, month, calendar.monthrange(y, month)[1]),
        )
    record("accounting.year_created", request=request, target=year)
    return year


@transaction.atomic
def set_period(request, pk, closed, reason="", *, fiscal=False):
    require(request.user, "accounting.manage", "accounting.periods.manage")
    lock_company()
    model = FiscalYear if fiscal else AccountingPeriod
    obj = model.objects.select_for_update().filter(pk=pk).first()
    if obj is None:
        raise NotFound()
    if not closed and not reason.strip():
        raise ValidationError({"reason": "Give a reason for reopening."})
    if not fiscal and not closed and obj.fiscal_year.is_closed:
        raise BusinessRuleViolation("Reopen the fiscal year first.")
    if fiscal:
        if not closed:
            obj.is_closed = False
            obj.save()
        for period in obj.periods.all():
            set_period(request, period.pk, closed, reason)
    obj.is_closed = closed
    if not fiscal:
        obj.closed_by = request.user if closed else None
        obj.closed_at = timezone.now() if closed else None
    obj.save()
    record(
        "accounting.period_closed" if closed else "accounting.period_reopened",
        request=request,
        target=obj,
        reason=reason,
    )
    return obj


def rate_for(currency, on, base):
    if currency == base:
        return decimal("1"), "Base currency"
    obj = ExchangeRate.objects.filter(
        currency=currency, base_currency=base, effective_date__lte=on
    ).first()
    if obj is None:
        raise ValidationError({"exchange_rate": f"No {currency}/{base} rate on or before {on}."})
    return obj.value, f"Rate #{obj.pk}: {obj.source}"


@transaction.atomic
def add_rate(request, data):
    require(request.user, "accounting.manage")
    company = lock_company()
    value = decimal(data["value"], "value", 12)
    quantum(data["currency"])
    if data["currency"] == company.base_currency or value <= 0:
        raise ValidationError({"value": "Enter a positive rate for a foreign currency."})
    if data["currency"] not in get_business_settings().enabled_currencies:
        raise ValidationError({"currency": "Enable this currency in settings first."})
    obj = ExchangeRate.objects.create(
        **{**data, "value": value}, base_currency=company.base_currency, created_by=request.user
    )
    record("accounting.rate_added", request=request, target=obj, after=strings(data))
    return obj


@transaction.atomic
def save_tax(request, data, pk=None):
    require(request.user, "accounting.manage")
    lock_company()
    revision = data.pop("revision", None)
    obj = TaxCode.objects.filter(pk=pk).first() if pk else TaxCode()
    if obj is None:
        raise NotFound()
    for k, v in data.items():
        setattr(obj, k, v)
    obj.full_clean()
    obj.save()
    if revision:
        for field, typ in (("input_account_id", "asset"), ("output_account_id", "liability")):
            if not Account.objects.filter(
                pk=revision[field], account_type=typ, is_active=True, is_postable=True
            ).exists():
                raise ValidationError({field: f"Choose an active postable {typ} account."})
        revision["percent"] = decimal(revision["percent"], "percent")
        r = TaxRevision(tax_code=obj, **revision)
        r.full_clean()
        r.save()
    record("accounting.tax_updated", request=request, target=obj, after=strings(data))
    return obj
