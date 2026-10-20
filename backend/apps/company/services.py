"""Company profile, business settings and module configuration."""

import re
from datetime import date

from django.db import IntegrityError, transaction
from django.forms.models import model_to_dict
from django.http import HttpRequest
from rest_framework import exceptions

from apps.audit.services import diff, record
from apps.core.exceptions import BusinessRuleViolation
from apps.files.models import FilePurpose, StoredFile
from apps.files.services import store_image

from .models import SINGLETON_ID, BusinessSettings, CompanyProfile, ModuleSetting
from .reference import DEFAULT_NUMBERING, MODULE_KEYS, NUMBERING_KEYS, OPTIONAL_MODULES

PROFILE_FIELDS = (
    "display_name",
    "legal_name",
    "email",
    "phone",
    "website",
    "address_line1",
    "address_line2",
    "city",
    "region",
    "postal_code",
    "country",
    "tax_id",
    "registration_number",
    "base_currency",
    "time_zone",
    "fiscal_year_start_month",
    "notes",
)
# Changing these after financial records exist would rewrite history.
HISTORY_SENSITIVE_FIELDS = ("base_currency", "fiscal_year_start_month")


def financial_history_exists() -> bool:
    """Whether posted financial records exist.

    Called while holding the company row lock, shared with first posting.
    Drafts and approval requests do not constitute posted financial history.
    """
    from apps.accounting.models import JournalEntry

    return JournalEntry.objects.filter(status="posted").exists()


# --- Company profile -------------------------------------------------------------


def get_company() -> CompanyProfile | None:
    return CompanyProfile.objects.select_related("logo").filter(pk=SINGLETON_ID).first()


def _profile_snapshot(company: CompanyProfile) -> dict:
    data = model_to_dict(company, fields=PROFILE_FIELDS)
    data["logo"] = str(company.logo_id) if company.logo_id else None
    return data


def create_company(request: HttpRequest, data: dict) -> CompanyProfile:
    """First-time setup. The singleton constraint makes a second profile impossible."""
    try:
        with transaction.atomic():
            company = CompanyProfile.objects.create(
                id=SINGLETON_ID,
                updated_by=request.user,
                **{k: v for k, v in data.items() if k in PROFILE_FIELDS},
            )
            ensure_base_currency_enabled(company.base_currency, request)
            record(
                "company.created", request=request, target=company, after=_profile_snapshot(company)
            )
    except IntegrityError as exc:
        raise BusinessRuleViolation(
            "This installation already has a company profile. Update it instead.",
            code="company_exists",
        ) from exc
    return company


@transaction.atomic
def update_company(request: HttpRequest, data: dict) -> CompanyProfile:
    company = CompanyProfile.objects.select_for_update().filter(pk=SINGLETON_ID).first()
    if company is None:
        raise exceptions.NotFound("The company profile has not been set up yet.")
    before = _profile_snapshot(company)

    if financial_history_exists():
        locked = [
            f for f in HISTORY_SENSITIVE_FIELDS if f in data and data[f] != getattr(company, f)
        ]
        if locked:
            raise BusinessRuleViolation(
                "Base currency and fiscal year start cannot change once financial records exist.",
                code="financial_history_locked",
            )

    from apps.accounting.models import FiscalYear

    if (
        "fiscal_year_start_month" in data
        and data["fiscal_year_start_month"] != company.fiscal_year_start_month
        and FiscalYear.objects.exists()
    ):
        raise BusinessRuleViolation(
            "Fiscal years already exist with the current boundaries.",
            code="fiscal_structure_exists",
        )

    for field, value in data.items():
        if field in PROFILE_FIELDS:
            setattr(company, field, value)
    company.updated_by = request.user
    company.save()
    ensure_base_currency_enabled(company.base_currency, request)

    old, new = diff(before, _profile_snapshot(company))
    if new:
        record("company.updated", request=request, target=company, before=old, after=new)
    return company


@transaction.atomic
def set_logo(request: HttpRequest, upload) -> CompanyProfile:
    company = CompanyProfile.objects.select_for_update().filter(pk=SINGLETON_ID).first()
    if company is None:
        raise exceptions.NotFound("Set up the company profile before uploading a logo.")
    stored = store_image(upload, purpose=FilePurpose.COMPANY_LOGO, user=request.user)
    previous = company.logo_id
    company.logo = stored
    company.updated_by = request.user
    company.save(update_fields=["logo", "updated_by", "updated_at"])
    # The previous file is kept: published branding versions may reference it.
    record(
        "company.logo_replaced" if previous else "company.logo_added",
        request=request,
        target=company,
        before={"logo": str(previous) if previous else None},
        after={"logo": str(stored.pk), "file_name": stored.original_name},
    )
    return company


@transaction.atomic
def remove_logo(request: HttpRequest) -> CompanyProfile:
    company = CompanyProfile.objects.select_for_update().filter(pk=SINGLETON_ID).first()
    if company is None:
        raise exceptions.NotFound("The company profile has not been set up yet.")
    if company.logo_id:
        previous = company.logo_id
        company.logo = None
        company.updated_by = request.user
        company.save(update_fields=["logo", "updated_by", "updated_at"])
        record(
            "company.logo_removed",
            request=request,
            target=company,
            before={"logo": str(previous)},
            after={"logo": None},
        )
    return company


def company_file_references(stored: StoredFile) -> set[str]:
    return {"company_logo"} if CompanyProfile.objects.filter(logo_id=stored.pk).exists() else set()


# --- Business settings ---------------------------------------------------------------

_NUMBER_TOKEN = re.compile(r"\{(YYYY|YY|MM|#{3,8})\}")
_NUMBER_FORMAT = re.compile(r"^(?:[A-Z0-9/_.\-]|\{YYYY\}|\{YY\}|\{MM\}|\{#{3,8}\})+$")


def get_business_settings() -> BusinessSettings:
    settings_obj, _ = BusinessSettings.objects.get_or_create(
        pk=SINGLETON_ID, defaults={"numbering": dict(DEFAULT_NUMBERING)}
    )
    merged = {**DEFAULT_NUMBERING, **(settings_obj.numbering or {})}
    settings_obj.numbering = merged
    return settings_obj


def render_number(fmt: str, on: date, sequence: int) -> str:
    def replace(match: re.Match) -> str:
        part = match.group(1)
        if part == "YYYY":
            return f"{on.year:04d}"
        if part == "YY":
            return f"{on.year % 100:02d}"
        if part == "MM":
            return f"{on.month:02d}"
        return str(sequence).zfill(len(part))

    return _NUMBER_TOKEN.sub(replace, fmt)


def validate_numbering(numbering: dict, current: dict | None = None) -> dict[str, str]:
    """Validate document number formats; reject ambiguous or colliding formats.

    Every document type must keep a distinct literal prefix so a number can
    never be mistaken for another document type's number.
    """
    errors: dict[str, str] = {}
    clean: dict[str, str] = {}
    for key, value in numbering.items():
        if key not in NUMBERING_KEYS:
            errors[key] = "Unknown document type."
            continue
        fmt = str(value).strip().upper()
        if not (3 <= len(fmt) <= 40) or not _NUMBER_FORMAT.match(fmt):
            errors[key] = "Use letters, digits, - / _ . and the tokens {YYYY} {YY} {MM} {###}."
            continue
        sequences = re.findall(r"\{#{3,8}\}", fmt)
        if len(sequences) != 1:
            errors[key] = "Include exactly one sequence token such as {####}."
            continue
        prefix = fmt.split("{", 1)[0]
        if not re.search(r"[A-Z]", prefix):
            errors[key] = "Start with a letter prefix such as INV- so numbers are recognisable."
            continue
        clean[key] = fmt

    full = {**DEFAULT_NUMBERING, **(current or {}), **clean}
    for key, fmt in clean.items():
        prefix = fmt.split("{", 1)[0]
        clash = next(
            (k for k, f in full.items() if k != key and f.split("{", 1)[0] == prefix), None
        )
        if clash:
            errors[key] = f"Prefix '{prefix}' is already used by {NUMBERING_KEYS[clash]}."
    if errors:
        raise exceptions.ValidationError({"numbering": errors})
    return clean


def ensure_base_currency_enabled(base_currency: str, request: HttpRequest | None = None) -> None:
    settings_obj = get_business_settings()
    if base_currency not in settings_obj.enabled_currencies:
        settings_obj.enabled_currencies = [base_currency, *settings_obj.enabled_currencies]
        settings_obj.save(update_fields=["enabled_currencies", "updated_at"])


def _settings_snapshot(obj: BusinessSettings) -> dict:
    return {
        "currency_display": obj.currency_display,
        "number_grouping": obj.number_grouping,
        "enabled_currencies": list(obj.enabled_currencies),
        "tax_registered": obj.tax_registered,
        "tax_label": obj.tax_label,
        "tax_registration_label": obj.tax_registration_label,
        "default_tax_rate": str(obj.default_tax_rate) if obj.default_tax_rate is not None else None,
        "prices_include_tax": obj.prices_include_tax,
        "numbering": dict(obj.numbering),
    }


@transaction.atomic
def update_business_settings(request: HttpRequest, data: dict) -> BusinessSettings:
    # Same lock order as posting: company, business settings, financial records.
    CompanyProfile.objects.select_for_update().filter(pk=SINGLETON_ID).first()
    obj = get_business_settings()
    obj = BusinessSettings.objects.select_for_update().get(pk=obj.pk)
    obj.numbering = {**DEFAULT_NUMBERING, **(obj.numbering or {})}
    before = _settings_snapshot(obj)

    if "numbering" in data:
        obj.numbering = {
            **obj.numbering,
            **validate_numbering(data.pop("numbering"), obj.numbering),
        }
    if "enabled_currencies" in data:
        currencies = list(dict.fromkeys(data.pop("enabled_currencies")))
        company = get_company()
        if company and company.base_currency not in currencies:
            currencies.insert(0, company.base_currency)
        obj.enabled_currencies = currencies
    for field, value in data.items():
        setattr(obj, field, value)
    obj.updated_by = request.user
    obj.save()

    old, new = diff(before, _settings_snapshot(obj))
    if new:
        record(
            "settings.business_updated",
            request=request,
            target_type="company.businesssettings",
            target_id=str(obj.pk),
            target_label="Business settings",
            before=old,
            after=new,
        )
    return obj


# --- Modules -------------------------------------------------------------------------


def module_states() -> dict[str, bool]:
    stored = dict(ModuleSetting.objects.values_list("key", "enabled"))
    return {m.key: stored.get(m.key, True) for m in OPTIONAL_MODULES}


def is_module_enabled(key: str) -> bool:
    """Server-side source of truth for optional modules (used by future domain APIs)."""
    if key not in MODULE_KEYS:
        raise ValueError(f"Unknown module: {key}")
    return module_states()[key]


@transaction.atomic
def set_module(request: HttpRequest, key: str, enabled: bool) -> bool:
    if key not in MODULE_KEYS:
        raise exceptions.NotFound("Unknown or mandatory module.")
    setting, _ = ModuleSetting.objects.select_for_update().get_or_create(key=key)
    if setting.enabled != enabled:
        setting.enabled = enabled
        setting.updated_by = request.user
        setting.save()
        record(
            "settings.module_enabled" if enabled else "settings.module_disabled",
            request=request,
            target_type="company.modulesetting",
            target_id=key,
            target_label=key,
            before={"enabled": not enabled},
            after={"enabled": enabled},
        )
    return enabled
