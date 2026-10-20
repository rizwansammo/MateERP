"""Shared rules for commercial adapters: control accounts, exact settlement, snapshots."""

from decimal import Decimal
from types import SimpleNamespace

from rest_framework.exceptions import ValidationError

from apps.accounting.models import Account
from apps.accounting.money import ZERO, convert
from apps.company.reference import CURRENCIES
from apps.company.services import get_business_settings, get_company
from apps.core.exceptions import BusinessRuleViolation

CONTROL_SETUP = {
    "receivable": "Assign the Receivable control purpose to your accounts-receivable account "
    "(Banking & Accounting → Chart of accounts) before issuing invoices.",
    "customer_credit": "Assign the Customer credit control purpose to a liability account "
    "(Banking & Accounting → Chart of accounts) to hold unapplied receipts and credits.",
    "payable": "Assign the Payable control purpose to your accounts-payable account "
    "(Banking & Accounting → Chart of accounts) before posting bills or accrued expenses.",
}


def control(purpose: str) -> Account:
    account = Account.objects.filter(control=purpose, is_active=True, is_postable=True).first()
    if account is None:
        raise BusinessRuleViolation(CONTROL_SETUP[purpose], code=f"{purpose}_control_required")
    return account


def ledger_settings():
    from ..models import LedgerSettings

    obj, _ = LedgerSettings.objects.get_or_create(pk=1)
    return obj


def posting_account(account_id, *, kind: str, fallback=None) -> Account:
    """An active postable revenue (or expense/asset) account, else an actionable error."""
    types = ("revenue",) if kind == "revenue" else ("expense", "asset")
    account = (
        Account.objects.filter(pk=account_id).first()
        if account_id
        else fallback
        if fallback is not None
        else None
    )
    if account is None:
        defaults = ledger_settings()
        account = (
            defaults.default_revenue_account
            if kind == "revenue"
            else defaults.default_expense_account
        )
    if account is None:
        raise ValidationError(
            {
                "account_id": f"Choose a {kind} account for every line, or set a default {kind} "
                "account in Sales & Billing setup."
            }
        )
    if account.account_type not in types or not account.is_active or not account.is_postable:
        raise ValidationError(
            {"account_id": f"{account.code} is not an active postable {kind} account."}
        )
    if account.control:
        raise ValidationError({"account_id": "Protected control accounts cannot be used on lines."})
    return account


def settlement_base(native, *, total, base_total, native_settled, base_settled, rate, base):
    """Base value removed when ``native`` of a document is settled.

    Partial settlements convert at the document's own (historical) rate; the final
    settlement takes exactly the remaining base, so a document always clears to zero.
    """
    remaining_native = total - native_settled
    remaining_base = base_total - base_settled
    if native > remaining_native:
        raise BusinessRuleViolation("The settlement exceeds the document's outstanding amount.")
    if native == remaining_native:
        return remaining_base
    return min(convert(native, rate, base), remaining_base)


def base_currency() -> str:
    company = get_company()
    if company is None:
        raise BusinessRuleViolation("Set up the company profile first.", code="company_required")
    return company.base_currency


def company_identity() -> dict:
    co = get_company()
    return {
        "display_name": co.display_name,
        "legal_name": co.legal_name,
        "address_lines": co.address_lines,
        "email": co.email,
        "phone": co.phone,
        "website": co.website,
        "tax_id": co.tax_id,
        "registration_number": co.registration_number,
    }


def money_format(currency: str) -> dict:
    settings_obj = get_business_settings()
    return {
        "currency": currency,
        "symbol": CURRENCIES[currency].symbol,
        "display": settings_obj.currency_display,
        "grouping": settings_obj.number_grouping,
        "minor_units": CURRENCIES[currency].minor_units,
    }


def tax_labels() -> dict:
    settings_obj = get_business_settings()
    return {
        "tax_label": settings_obj.tax_label,
        "tax_registration_label": settings_obj.tax_registration_label,
    }


def published_branding():
    from apps.branding.services import current_version

    version = current_version()
    if version is None:
        raise BusinessRuleViolation(
            "Publish invoice and receipt branding (Settings → Branding) before issuing documents.",
            code="branding_required",
        )
    return version


def acting(user):
    """Request-like context for executors and scheduled runs."""
    return SimpleNamespace(user=user, META={})


def positive(value: Decimal, field="amount"):
    if value <= ZERO:
        raise ValidationError({field: "Enter a positive amount."})
    return value


def posting_key(*parts) -> str:
    return ":".join(str(p) for p in ("commerce", *parts))[:160]
