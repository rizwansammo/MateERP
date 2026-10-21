"""Historical evidence is non-posting. Explicit independent adoption uses existing domains."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.authorization import get_permission_codes, require
from apps.approvals import services as approvals
from apps.audit.services import record
from apps.banking.models import BankAccount
from apps.company.services import next_number
from apps.core.exceptions import BusinessRuleViolation
from apps.files.services import store_document
from apps.founders.models import CorporateTransaction, FounderObligation
from apps.purchasing.models import Vendor, VendorBill, VendorBillLine
from apps.sales.services import _get, enabled_currency

from ..models import Account, HistoricalRecord, HistoricalTreatment, JournalLine
from ..money import convert, money, strings
from .adapters import authorize
from .posting import fingerprint, post_journal
from .setup import lock_company, rate_for


def can_read_evidence(user, stored):
    codes = get_permission_codes(user)
    if not {"onboarding.manage", "finance.view"} <= codes:
        return False
    return visible_records(user, HistoricalRecord.objects.filter(evidence=stored)).exists()


def visible_records(user, qs):
    codes = get_permission_codes(user)
    if "founder.view" not in codes:
        qs = qs.filter(party__isnull=True)
    if "founder.personal.view" not in codes:
        return qs.exclude(funding_classification="personal_settlement")
    if "founder.attest" not in codes:
        qs = qs.filter(
            ~Q(funding_classification="personal_settlement")
            | Q(party__user=user)
            | Q(created_by=user)
        )
    return qs


@transaction.atomic
def document(request, data, upload=None):
    require(request.user, "onboarding.manage", "finance.view")
    lock_company()
    enabled_currency(data["currency"])
    data["amount"] = money(data["amount"], data["currency"])
    data["external_reference"] = data["external_reference"].strip().upper()
    if data["amount"] <= 0:
        raise ValidationError({"amount": "Enter the documented positive amount."})
    if data.get("party_id"):
        require(request.user, "founder.view")
    if data["funding_classification"] == "personal_settlement":
        from apps.company.models import FinancialParty

        require(request.user, "founder.personal.view", "founder.settlements.manage")
        participant = _get(FinancialParty, data.get("party_id"))
        if participant.user_id != request.user.pk and "founder.attest" not in get_permission_codes(
            request.user
        ):
            raise PermissionDenied(
                "Document personal settlement evidence as yourself or through "
                "authorized attestation."
            )
    stored = (
        store_document(upload, purpose="historical_evidence", user=request.user) if upload else None
    )
    obj = HistoricalRecord(created_by=request.user, evidence=stored, **data)
    obj.full_clean()
    obj.save()
    record(
        "historical.documented",
        request=request,
        target=obj,
        after={
            "reference": obj.external_reference,
            "date": obj.original_date,
            "pre_registration": obj.pre_registration,
            "posting_effect": "none",
        },
    )
    return obj


@transaction.atomic
def request_treatment(request, pk, data):
    require(request.user, "onboarding.manage", "accounting.manage", "finance.view")
    lock_company()
    source = _get(HistoricalRecord, pk)
    if not visible_records(request.user, HistoricalRecord.objects.filter(pk=source.pk)).exists():
        raise PermissionDenied("This historical source is restricted.")
    if HistoricalTreatment.objects.filter(record=source).exclude(status="rejected").exists():
        raise BusinessRuleViolation(
            "This item already has a disposition. Opening and reconstruction cannot both apply."
        )
    allowed = {
        "reconstructed": {"company_expense", "founder_expense"},
        "opening_only": {
            "bank_balance",
            "vendor_payable",
            "founder_expense",
            "loan",
            "contribution",
            "inventory_opening",
        },
        "linked": {
            "company_expense",
            "vendor_payable",
            "founder_expense",
            "loan",
            "contribution",
            "reimbursement",
            "personal_settlement",
        },
    }
    if source.funding_classification not in allowed[data["mode"]]:
        raise ValidationError(
            {
                "mode": (
                    "Choose the existing verified source or the appropriate reviewed "
                    "opening/reconstruction for this funding type."
                )
            }
        )
    if data["recognition_date"] < source.original_date:
        raise ValidationError(
            {"recognition_date": "Recognition cannot precede the documented transaction."}
        )
    if source.funding_classification == "personal_settlement":
        require(request.user, "founder.personal.view", "founder.settlements.manage")
    elif source.party_id:
        require(request.user, "founder.view", "founder.transactions.manage")
    obj = HistoricalTreatment.objects.create(
        record=source,
        mode=data["mode"],
        recognition_date=data["recognition_date"],
        reason=data["reason"],
        payload=strings(data.get("payload", {})),
        requested_by=request.user,
    )
    # Independent review is mandatory even if the ordinary journal policy is off.
    obj.approval = approvals.submit(
        request,
        action="historical.review",
        subject_key=f"history:{source.pk}",
        title=f"Review historical treatment — {source.external_reference}"[:200],
        reason=obj.reason[:500],
        payload={"treatment_id": obj.pk},
    )
    obj.save(update_fields=["approval"])
    return obj


def execute_review(request, approval, approver):
    treatment = _get(HistoricalTreatment, approval.payload["treatment_id"])
    source = treatment.record
    if treatment.status != "pending" or approver.pk in (
        treatment.requested_by_id,
        source.created_by_id,
    ):
        raise PermissionDenied(
            "An independent authorized operator must review historical recognition."
        )
    if source.funding_classification == "personal_settlement":
        require(approver, "founder.personal.view", "founder.settlements.manage")
    elif source.party_id:
        require(approver, "founder.view", "founder.transactions.manage")
    if treatment.mode == "opening_only":
        _opening(request, treatment)
    elif treatment.mode == "linked":
        _link_existing(request, treatment)
    else:
        _reconstruct(request, treatment)
    treatment.status, treatment.approved_by = "approved", approver
    treatment.save()
    record(
        "historical.treatment_approved",
        request=request,
        target=treatment,
        after={
            "record": source.pk,
            "mode": treatment.mode,
            "original_date": source.original_date,
            "recognition_date": treatment.recognition_date,
        },
        reason=treatment.reason,
    )
    return f"historical:{source.pk}"


def _link_existing(request, treatment):
    """Attach provenance to the existing verified owning workflow; never repost it.

    This covers receipts, loans, reimbursements and confirmed personal transfers
    with their original distinctions. Pre-registration corporate adoption must be
    explicitly evidenced. Linking does not invent or clear any company obligation.
    """
    source, data = treatment.record, treatment.payload
    pk = data.get("source_id")
    if not isinstance(pk, int) or isinstance(pk, bool) or pk <= 0:
        raise ValidationError({"source_id": "Select the existing verified source record."})
    if (
        source.pre_registration
        and source.funding_classification != "personal_settlement"
        and not data.get("corporate_adoption_reference")
    ):
        raise ValidationError(
            {"corporate_adoption_reference": "Retain explicit corporate adoption authority."}
        )
    classification = source.funding_classification
    if classification in ("contribution", "loan", "reimbursement", "founder_expense"):
        require(request.user, "founder.view", "founder.transactions.manage")
        tx = _get(CorporateTransaction, pk)
        expected = {
            "contribution": "receipt",
            "loan": "receipt",
            "reimbursement": "reimbursement",
            "founder_expense": "expense",
        }[classification]
        if (
            tx.kind != expected
            or tx.status != "posted"
            or (classification == "loan" and tx.classification != "loan")
            or (
                classification == "contribution"
                and tx.classification not in ("pending", "other_equity", "share_capital")
            )
        ):
            raise BusinessRuleViolation(
                "Select the matching verified corporate funding classification, "
                "not a personal transfer or unverified promise."
            )
        if source.party_id != tx.party_id:
            raise BusinessRuleViolation(
                "The financial participant differs from the documented original source."
            )
        if classification == "founder_expense":
            treatment.expense = tx.expense
        treatment.founder_transaction, treatment.journal = tx, tx.journal
        amount, currency, recognized = tx.amount, tx.currency, tx.date
    elif classification == "personal_settlement":
        from apps.founders.services.sharing import visible_settlements

        require(request.user, "founder.personal.view", "founder.settlements.manage")
        obj = visible_settlements(request.user).filter(pk=pk, status="confirmed").first()
        if obj is None or source.party_id not in (obj.payer_id, obj.recipient_id):
            raise BusinessRuleViolation(
                "Select a visible confirmed personal settlement involving the "
                "documented participant."
            )
        treatment.personal_settlement = obj
        amount, currency, recognized = obj.amount, obj.currency, obj.date
    elif classification in ("company_expense", "vendor_payable"):
        from apps.purchasing.models import Expense

        model = Expense if classification == "company_expense" else VendorBill
        obj = _get(model, pk)
        if obj.status not in ("posted", "partially_paid", "paid") or (
            classification == "company_expense" and obj.payment_mode == "founder"
        ):
            raise BusinessRuleViolation(
                "Select a posted source with the documented payment/obligation distinction."
            )
        if classification == "company_expense":
            treatment.expense = obj
        else:
            treatment.vendor_bill = obj
        treatment.journal = obj.journal
        amount, currency = obj.total, obj.currency
        recognized = obj.expense_date if classification == "company_expense" else obj.bill_date
    else:
        raise ValidationError(
            {"funding_classification": "Use reviewed opening treatment for this balance source."}
        )
    if (
        amount != source.amount
        or currency != source.currency
        or recognized != treatment.recognition_date
    ):
        raise BusinessRuleViolation(
            "The verified source amount, currency and recognition date must "
            "match the historical disposition exactly."
        )
    treatment.full_clean()


def declined(request, approval):
    obj = _get(HistoricalTreatment, approval.payload["treatment_id"])
    obj.status = "rejected"
    obj.save(update_fields=["status"])


def _reconstruct(request, treatment):
    source, data = treatment.record, treatment.payload
    if source.funding_classification not in ("company_expense", "founder_expense"):
        raise ValidationError(
            {
                "funding_classification": "Use the existing contribution, loan, reimbursement "
                "or personal-settlement workflow. This action prepares expense drafts only."
            }
        )
    from apps.purchasing.api.serializers import ExpenseInput
    from apps.purchasing.services.payables import save_expense
    from apps.sales.api.base import validated

    payload = {
        **data,
        "amount": str(source.amount),
        "currency": source.currency,
        "description": source.description[:300],
        "expense_date": treatment.recognition_date,
        "original_transaction_date": source.original_date,
        "recognition_reason": treatment.reason[:1000],
        "reference": source.external_reference,
        "prices_include_tax": True,
    }
    if source.funding_classification == "founder_expense":
        from apps.founders.services.corporate import record_transaction

        require(request.user, "founder.transactions.manage", "expenses.manage")
        tx = record_transaction(
            request,
            {
                "kind": "expense",
                "party_id": source.party_id,
                "date": str(treatment.recognition_date),
                "classification": data.get("classification", "pending"),
                "currency": source.currency,
                "expense": payload,
                "reference": source.external_reference,
                "notes": treatment.reason,
            },
            f"history:{source.pk}:adopt",
            historical_treatment=treatment,
        )
        treatment.expense, treatment.founder_transaction = tx.expense, tx
    else:
        require(request.user, "expenses.manage")
        payload = validated(ExpenseInput, payload)
        if payload.get("payment_mode") not in ("paid", "accrued"):
            raise ValidationError(
                {"payment_mode": "Choose the actual company bank payment or vendor obligation."}
            )
        treatment.expense = save_expense(request, payload, historical_treatment=treatment)
    if treatment.expense.currency != source.currency or treatment.expense.total != source.amount:
        raise BusinessRuleViolation(
            "Reconstructed expense must equal the documented gross payment and currency."
        )
    # Review authorizes adoption/preparation, never pretends a draft is posted.
    # The existing expense posting or founder maker/checker workflow still runs.


def _opening(request, treatment):
    source, data = treatment.record, treatment.payload
    company = lock_company()
    if source.pre_registration and not data.get("corporate_adoption_reference"):
        raise ValidationError(
            {
                "corporate_adoption_reference": "Document explicit corporate adoption "
                "of this startup expenditure."
            }
        )
    equity = _get(Account, data.get("opening_equity_account_id"))
    if (
        equity.control
        or equity.account_type != "equity"
        or not equity.is_postable
        or not equity.is_active
    ):
        raise ValidationError(
            {"opening_equity_account_id": "Choose a reviewed opening equity account."}
        )
    fx, rate_source = rate_for(source.currency, treatment.recognition_date, company.base_currency)
    value = convert(source.amount, fx, company.base_currency)
    liability = source.funding_classification in (
        "vendor_payable",
        "founder_expense",
        "loan",
        "contribution",
    )
    if source.funding_classification == "bank_balance":
        bank = _get(BankAccount, data.get("bank_id"))
        if not bank.is_active or bank.currency != source.currency:
            raise ValidationError({"bank_id": "Select an active bank in the documented currency."})
        if JournalLine.objects.filter(account=bank.gl_account, journal__status="posted").exists():
            raise BusinessRuleViolation(
                "This bank has posted activity. Reconcile its existing opening "
                "rather than count it again."
            )
        account = bank.gl_account
    elif source.funding_classification == "inventory_opening":
        require(request.user, "inventory.manage", "inventory.post")
        from apps.inventory import services as stock
        from apps.inventory.models import Movement

        qty = stock.decimal(data.get("quantity"), "quantity")
        if qty <= 0 or Movement.objects.filter(item_id=data.get("item_id")).exists():
            raise BusinessRuleViolation(
                "Opening stock requires a positive count and an item without existing stock events."
            )
        stock._validate(
            data.get("item_id"), data.get("location_id"), treatment.recognition_date, qty
        )
        account = stock.control("inventory")
    elif liability:
        from apps.inventory.services import control

        purpose = {
            "vendor_payable": "payable",
            "founder_expense": "founder_payable",
            "loan": "founder_loan",
            "contribution": "founder_pending",
        }[source.funding_classification]
        account = control(purpose)
        if source.funding_classification == "vendor_payable":
            _get(Vendor, data.get("vendor_id"))
        elif not source.party_id:
            raise ValidationError(
                {"party_id": "Identify the founder whose opening obligation is documented."}
            )
    else:
        raise ValidationError(
            {
                "mode": "Opening treatment supports bank/stock balances and outstanding "
                "vendor/founder obligations. It cannot repeat an expense or personal payment."
            }
        )
    raw = [
        {
            "account_id": account.pk,
            "currency": source.currency,
            "credit" if liability else "debit": str(source.amount),
            "exchange_rate": str(fx),
            "rate_source": rate_source,
            "dimensions": {"historical_record": source.pk, "provenance": "opening_only"},
        },
        {
            "account_id": equity.pk,
            "currency": company.base_currency,
            "debit" if liability else "credit": str(value),
        },
    ]
    journal = post_journal(
        actor=request.user,
        authority=authorize(request.user, "cutover", "post"),
        source_type="cutover",
        source_id=source.pk,
        source_action="post",
        posting_key=f"cutover:{source.pk}:opening",
        posting_date=treatment.recognition_date,
        journal_date=source.original_date,
        description=f"Reviewed opening {source.external_reference}",
        reason=treatment.reason[:500],
        request_context=request,
        lines=raw,
    )
    treatment.journal = journal
    if source.funding_classification == "inventory_opening":
        stock._persist(
            request,
            item_id=data["item_id"],
            location_id=data["location_id"],
            on=treatment.recognition_date,
            kind="opening",
            qty=qty,
            value=value,
            key=f"cutover:{source.pk}:inventory",
            source_type="cutover",
            source_id=source.pk,
            reason=treatment.reason[:500],
            digest=fingerprint(strings(data)),
            journal=journal,
        )
    elif source.funding_classification == "vendor_payable":
        vendor = _get(Vendor, data["vendor_id"])
        from apps.purchasing.services.payables import normalize_reference

        bill = VendorBill.objects.create(
            vendor=vendor,
            vendor_reference=source.external_reference[:80],
            normalized_reference=normalize_reference(source.external_reference),
            bill_date=treatment.recognition_date,
            due_date=treatment.recognition_date,
            currency=source.currency,
            taxable=source.amount,
            subtotal=source.amount,
            total=source.amount,
            notes=f"Opening-only obligation; original {source.original_date}. {treatment.reason}"[
                :1000
            ],
            created_by=request.user,
        )
        VendorBillLine.objects.create(
            bill=bill,
            position=1,
            description="Opening liability (no current expense)",
            account=equity,
            quantity=1,
            unit_price=source.amount,
            subtotal=source.amount,
            taxable=source.amount,
            total=source.amount,
        )
        bill.number = next_number(
            "vendor_bill",
            treatment.recognition_date,
            lambda n: VendorBill.objects.filter(number=n).exists(),
        )
        bill.status, bill.journal, bill.exchange_rate, bill.base_total = (
            "posted",
            journal,
            fx,
            value,
        )
        bill.posted_by, bill.posted_at = request.user, timezone.now()
        bill.save()
        treatment.vendor_bill = bill
    elif liability:
        classification = {"founder_expense": "payable", "loan": "loan", "contribution": "pending"}[
            source.funding_classification
        ]
        tx = CorporateTransaction.objects.create(
            kind="opening",
            classification=classification,
            party=source.party,
            date=treatment.recognition_date,
            currency=source.currency,
            amount=source.amount,
            base_amount=value,
            journal=journal,
            status="posted",
            client_key=f"cutover:{source.pk}",
            fingerprint=fingerprint(strings(raw)),
            reference=source.external_reference,
            notes=treatment.reason,
            snapshot={"provenance": "opening_only", "original_date": str(source.original_date)},
            request_data={"historical_record": source.pk},
            created_by=treatment.requested_by,
            verified_by=request.user,
        )
        FounderObligation.objects.create(
            origin=tx,
            recovery_origin=tx,
            party=source.party,
            category=classification,
            currency=source.currency,
            amount=source.amount,
            base_amount=value,
        )
        treatment.founder_transaction = tx
