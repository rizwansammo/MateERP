"""Branding workflow: edit draft → preview → save draft → publish (or request approval)."""

from django.db import transaction
from django.db.models import Max, Q
from django.http import HttpRequest
from rest_framework import exceptions

from apps.accounts.models import User
from apps.approvals import services as approvals
from apps.approvals.models import ApprovalRequest
from apps.audit.services import diff, record
from apps.company.services import get_business_settings, get_company
from apps.core.exceptions import BusinessRuleViolation
from apps.files.models import FilePurpose, StoredFile
from apps.files.services import store_image

from .models import SINGLETON_ID, BrandingDraft, BrandingVersion
from .schema import DEFAULT_CONFIG, normalise_config

PUBLISH_ACTION = "branding.publish"
ASSET_FIELDS = {"signature": FilePurpose.BRANDING_SIGNATURE, "seal": FilePurpose.BRANDING_SEAL}


def current_version() -> BrandingVersion | None:
    return BrandingVersion.objects.select_related("logo", "signature", "seal_image").first()


def get_draft() -> BrandingDraft:
    draft = (
        BrandingDraft.objects.select_related("signature", "seal_image")
        .filter(pk=SINGLETON_ID)
        .first()
    )
    if draft is not None:
        return draft
    latest = current_version()
    draft, _ = BrandingDraft.objects.get_or_create(
        pk=SINGLETON_ID,
        defaults={
            "config": normalise_config(latest.config if latest else DEFAULT_CONFIG),
            "signature": latest.signature if latest else None,
            "seal_image": latest.seal_image if latest else None,
        },
    )
    return draft


def has_unpublished_changes(draft: BrandingDraft, version: BrandingVersion | None) -> bool:
    if version is None:
        return True
    return (
        normalise_config(draft.config) != normalise_config(version.config)
        or draft.signature_id != version.signature_id
        or draft.seal_image_id != version.seal_image_id
    )


def pending_publication() -> ApprovalRequest | None:
    return (
        ApprovalRequest.objects.filter(action=PUBLISH_ACTION, status=ApprovalRequest.Status.PENDING)
        .select_related("requested_by")
        .first()
    )


@transaction.atomic
def save_draft(request: HttpRequest, config: dict) -> BrandingDraft:
    draft = BrandingDraft.objects.select_for_update().get(pk=get_draft().pk)
    before = normalise_config(draft.config)
    after = normalise_config(config)
    draft.config = after
    draft.updated_by = request.user
    draft.save()
    old, new = diff(before, after)
    if new:
        record(
            "branding.draft_updated",
            request=request,
            target_type="branding.brandingdraft",
            target_id="draft",
            target_label="Branding draft",
            before=old,
            after=new,
        )
    return draft


@transaction.atomic
def set_draft_asset(request: HttpRequest, kind: str, upload) -> BrandingDraft:
    if kind not in ASSET_FIELDS:
        raise exceptions.NotFound()
    draft = BrandingDraft.objects.select_for_update().get(pk=get_draft().pk)
    stored = store_image(upload, purpose=ASSET_FIELDS[kind], user=request.user)
    if kind == "signature":
        draft.signature = stored
    else:
        draft.seal_image = stored
        draft.config = {**normalise_config(draft.config)}
        draft.config["seal"] = {**draft.config["seal"], "mode": "image"}
    draft.updated_by = request.user
    draft.save()
    record(
        "branding.asset_uploaded",
        request=request,
        target_type="branding.brandingdraft",
        target_id="draft",
        target_label=f"Draft {kind}",
        after={"asset": kind, "file": str(stored.pk), "file_name": stored.original_name},
    )
    return draft


@transaction.atomic
def remove_draft_asset(request: HttpRequest, kind: str) -> BrandingDraft:
    if kind not in ASSET_FIELDS:
        raise exceptions.NotFound()
    draft = BrandingDraft.objects.select_for_update().get(pk=get_draft().pk)
    field = "signature" if kind == "signature" else "seal_image"
    previous = getattr(draft, f"{field}_id")
    if previous:
        setattr(draft, field, None)
        if kind == "seal":
            config = normalise_config(draft.config)
            if config["seal"]["mode"] == "image":
                config["seal"]["mode"] = "none"
            draft.config = config
        draft.updated_by = request.user
        draft.save()
        record(
            "branding.asset_removed",
            request=request,
            target_type="branding.brandingdraft",
            target_id="draft",
            target_label=f"Draft {kind}",
            before={"asset": kind, "file": str(previous)},
            after={"asset": kind, "file": None},
        )
    return draft


@transaction.atomic
def discard_draft(request: HttpRequest) -> BrandingDraft:
    version = current_version()
    draft = BrandingDraft.objects.select_for_update().get(pk=get_draft().pk)
    draft.config = normalise_config(version.config if version else DEFAULT_CONFIG)
    draft.signature = version.signature if version else None
    draft.seal_image = version.seal_image if version else None
    draft.updated_by = request.user
    draft.save()
    record(
        "branding.draft_discarded",
        request=request,
        target_type="branding.brandingdraft",
        target_id="draft",
        target_label="Branding draft",
    )
    return draft


def _draft_payload(draft: BrandingDraft, label: str, restored_from: int | None = None) -> dict:
    config = normalise_config(draft.config)
    return {
        "config": config,
        "signature_id": str(draft.signature_id) if draft.signature_id else None,
        "seal_image_id": str(draft.seal_image_id) if draft.seal_image_id else None,
        "label": label,
        "template": config["invoice_template"],
        "receipt_template": config["receipt_template"],
        "restored_from": restored_from,
    }


def _company_snapshot() -> tuple[dict, StoredFile | None]:
    company = get_company()
    if company is None:
        raise BusinessRuleViolation(
            "Set up the company profile before publishing branding.", code="company_required"
        )
    snapshot = {
        "display_name": company.display_name,
        "legal_name": company.legal_name,
        "address_lines": company.address_lines,
        "email": company.email,
        "phone": company.phone,
        "website": company.website,
        "tax_id": company.tax_id,
        "registration_number": company.registration_number,
    }
    return snapshot, company.logo


def _create_version(
    request: HttpRequest,
    payload: dict,
    *,
    published_by: User,
    approval: ApprovalRequest | None = None,
) -> BrandingVersion:
    # The draft row doubles as a mutex so version numbers are allocated serially.
    BrandingDraft.objects.select_for_update().get(pk=get_draft().pk)
    company, logo = _company_snapshot()
    settings_obj = get_business_settings()
    number = (BrandingVersion.objects.aggregate(n=Max("number"))["n"] or 0) + 1
    version = BrandingVersion.objects.create(
        number=number,
        label=payload.get("label", "")[:80],
        config=normalise_config(payload["config"]),
        company=company,
        numbering={k: settings_obj.numbering[k] for k in ("invoice", "receipt")},
        logo=logo,
        signature_id=payload.get("signature_id"),
        seal_image_id=payload.get("seal_image_id"),
        published_by=published_by,
        restored_from_id=payload.get("restored_from"),
        approval_request=approval,
    )
    record(
        "branding.published",
        request=request,
        target=version,
        after={
            "version": number,
            "label": version.label,
            "invoice_template": version.config["invoice_template"],
            "receipt_template": version.config["receipt_template"],
            "approved_via": approval.pk if approval else None,
        },
    )
    return version


def publish(
    request: HttpRequest,
    *,
    label: str = "",
    reason: str = "",
    restored_from: BrandingVersion | None = None,
):
    """Publish the draft, or submit it for approval when the policy requires.

    Returns ("published", version) or ("pending_approval", approval_request).
    """
    draft = get_draft()
    payload = _draft_payload(draft, label, restored_from.pk if restored_from else None)
    if approvals.approval_required(PUBLISH_ACTION):
        title = "Publish invoice & receipt branding" + (f" — {label}" if label else "")
        return "pending_approval", approvals.submit(
            request, action=PUBLISH_ACTION, title=title, payload=payload, reason=reason
        )
    with transaction.atomic():
        version = _create_version(request, payload, published_by=request.user)
    return "published", version


@transaction.atomic
def restore(request: HttpRequest, version: BrandingVersion):
    """Copy a historical version into the draft and publish it as a new version."""
    draft = BrandingDraft.objects.select_for_update().get(pk=get_draft().pk)
    draft.config = normalise_config(version.config)
    draft.signature = version.signature
    draft.seal_image = version.seal_image
    draft.updated_by = request.user
    draft.save()
    record(
        "branding.restore_requested",
        request=request,
        target=version,
        after={"restored_from": version.number},
    )
    return publish(request, label=f"Restored from version {version.number}", restored_from=version)


def execute_approved_publication(
    request: HttpRequest, approval: ApprovalRequest, approver: User
) -> str:
    """Approval executor: publish exactly the payload captured at request time."""
    version = _create_version(
        request, approval.payload, published_by=approval.requested_by, approval=approval
    )
    return f"branding_version:{version.number}"


def branding_file_references(stored: StoredFile) -> set[str]:
    refs: set[str] = set()
    if BrandingDraft.objects.filter(
        Q(signature_id=stored.pk) | Q(seal_image_id=stored.pk)
    ).exists():
        refs.add("branding_draft")
    if BrandingVersion.objects.filter(
        Q(logo_id=stored.pk) | Q(signature_id=stored.pk) | Q(seal_image_id=stored.pk)
    ).exists():
        refs.add("branding_version")
    if (
        ApprovalRequest.objects.filter(status=ApprovalRequest.Status.PENDING, action=PUBLISH_ACTION)
        .filter(Q(payload__signature_id=str(stored.pk)) | Q(payload__seal_image_id=str(stored.pk)))
        .exists()
    ):
        refs.add("pending_publication")
    return refs
