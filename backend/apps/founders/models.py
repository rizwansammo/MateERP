"""Corporate source records, non-GL personal sharing and versioned funding plans."""

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower, Trim

from apps.accounting.models import amount as money_field
from apps.core.models import IdentifiedRecord

USER = settings.AUTH_USER_MODEL
PARTY = "company.FinancialParty"


class CorporateTransaction(IdentifiedRecord):
    kind = models.CharField(
        max_length=16,
        choices=[
            (x, x.replace("_", " ").title())
            for x in (
                "receipt",
                "expense",
                "vendor_payment",
                "reimbursement",
                "loan_repayment",
                "reclassify",
                "reassign",
            )
        ],
    )
    party = models.ForeignKey(
        PARTY, on_delete=models.PROTECT, related_name="corporate_transactions"
    )
    recipient = models.ForeignKey(
        PARTY, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    classification = models.CharField(
        max_length=24,
        choices=[
            (x, x.replace("_", " ").title())
            for x in ("payable", "loan", "other_equity", "share_capital", "pending")
        ],
    )
    date = models.DateField()
    currency = models.CharField(max_length=3)
    amount = money_field()
    base_amount = money_field(null=True, blank=True)
    bank = models.ForeignKey(
        "banking.BankAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    loan = models.ForeignKey(
        "founders.FounderLoan",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    expense = models.OneToOneField(
        "purchasing.Expense",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="founder_funding",
    )
    issuance = models.ForeignKey(
        "ownership.OwnershipProposal",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="funding",
    )
    reference = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=2000, blank=True)
    status = models.CharField(
        max_length=20,
        default="recorded",
        choices=[
            (x, x.replace("_", " ").title())
            for x in ("recorded", "awaiting_approval", "posted", "rejected", "reversed")
        ],
    )
    client_key = models.CharField(max_length=160, unique=True)
    fingerprint = models.CharField(max_length=64)
    request_data = models.JSONField(default=dict, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    journal = models.OneToOneField(
        "accounting.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="founder_transaction",
    )
    reversal_journal = models.OneToOneField(
        "accounting.JournalEntry", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    approval = models.ForeignKey(
        "approvals.ApprovalRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    verified_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-pk"]
        constraints = [
            models.UniqueConstraint(
                Lower(Trim("reference")),
                F("bank"),
                condition=Q(kind="receipt")
                & ~Q(reference="")
                & ~Q(status__in=["rejected", "reversed"]),
                name="founder_cash_reference_once",
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="founder_transaction_positive"),
            models.CheckConstraint(
                condition=~Q(status__in=["posted", "reversed"])
                | Q(journal__isnull=False, base_amount__isnull=False),
                name="founder_posted_metadata",
            ),
        ]


class FounderLoan(IdentifiedRecord):
    party = models.ForeignKey(PARTY, on_delete=models.PROTECT, related_name="loans")
    name = models.CharField(max_length=160)
    currency = models.CharField(max_length=3)
    terms = models.CharField(max_length=2000, blank=True)
    maturity = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")


class FounderObligation(IdentifiedRecord):
    recovery_origin = models.ForeignKey(
        CorporateTransaction,
        on_delete=models.PROTECT,
        related_name="recovery_obligations",
    )
    """Original company liability; balances are source allocations, not bank caches."""

    origin = models.OneToOneField(
        CorporateTransaction, on_delete=models.PROTECT, related_name="obligation"
    )
    party = models.ForeignKey(PARTY, on_delete=models.PROTECT, related_name="obligations")
    category = models.CharField(max_length=16)
    currency = models.CharField(max_length=3)
    amount = money_field()
    base_amount = money_field()
    original_expense = models.ForeignKey(
        "purchasing.Expense",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="founder_obligations",
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0, base_amount__gt=0), name="founder_obligation_positive"
            )
        ]


class ObligationAllocation(IdentifiedRecord):
    transaction = models.ForeignKey(
        CorporateTransaction, on_delete=models.PROTECT, related_name="allocations"
    )
    obligation = models.ForeignKey(
        FounderObligation, on_delete=models.PROTECT, related_name="allocations"
    )
    amount = money_field()
    base_amount = money_field()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["transaction", "obligation"], name="founder_allocation_once"
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0, base_amount__gt=0), name="founder_allocation_positive"
            ),
        ]


class FounderVendorAllocation(IdentifiedRecord):
    transaction = models.ForeignKey(
        CorporateTransaction, on_delete=models.PROTECT, related_name="vendor_allocations"
    )
    bill = models.ForeignKey(
        "purchasing.VendorBill",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="founder_allocations",
    )
    expense = models.ForeignKey(
        "purchasing.Expense",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="founder_allocations",
    )
    amount = money_field()
    base_amount = money_field()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0)
                & (
                    Q(bill__isnull=False, expense__isnull=True)
                    | Q(bill__isnull=True, expense__isnull=False)
                ),
                name="founder_vendor_one_source",
            )
        ]


class SharingPolicy(IdentifiedRecord):
    name = models.CharField(max_length=160)
    effective_from = models.DateField()
    effective_until = models.DateField(null=True, blank=True)
    category = models.ForeignKey(
        "accounting.Account", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    basis = models.CharField(
        max_length=16,
        choices=[(x, x.title()) for x in ("equal", "custom", "provisional", "formal")],
    )
    weights = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, default="draft")
    snapshot = models.JSONField(default=dict, blank=True)
    approval = models.ForeignKey(
        "approvals.ApprovalRequest",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_until__isnull=True)
                | Q(effective_until__gte=F("effective_from")),
                name="sharing_policy_dates",
            )
        ]


class SharedExpense(IdentifiedRecord):
    expense = models.OneToOneField(
        "purchasing.Expense",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="personal_sharing",
    )
    founder_payment = models.OneToOneField(
        CorporateTransaction,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="personal_sharing",
    )
    payer = models.ForeignKey(PARTY, on_delete=models.PROTECT, related_name="shared_expenses")
    date = models.DateField()
    currency = models.CharField(max_length=3)
    amount = money_field()
    description = models.CharField(max_length=300)
    policy = models.ForeignKey(SharingPolicy, on_delete=models.PROTECT)
    snapshot = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")


class PersonalObligation(IdentifiedRecord):
    sharing = models.ForeignKey(SharedExpense, on_delete=models.PROTECT, related_name="obligations")
    debtor = models.ForeignKey(PARTY, on_delete=models.PROTECT, related_name="personal_payables")
    creditor = models.ForeignKey(
        PARTY, on_delete=models.PROTECT, related_name="personal_receivables"
    )
    amount = money_field()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sharing", "debtor"], name="personal_share_once"),
            models.CheckConstraint(
                condition=Q(amount__gt=0) & ~Q(debtor=F("creditor")),
                name="personal_parties_distinct",
            ),
        ]


class PersonalSettlement(IdentifiedRecord):
    payer = models.ForeignKey(PARTY, on_delete=models.PROTECT, related_name="personal_payments")
    recipient = models.ForeignKey(PARTY, on_delete=models.PROTECT, related_name="personal_receipts")
    date = models.DateField()
    currency = models.CharField(max_length=3)
    amount = money_field()
    reference = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=2000, blank=True)
    status = models.CharField(max_length=16, default="recorded")
    is_return = models.BooleanField(default=False)
    returns = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="refunds"
    )
    client_key = models.CharField(max_length=160, unique=True)
    fingerprint = models.CharField(max_length=64)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-date", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0) & ~Q(payer=F("recipient")), name="personal_transfer_valid"
            )
        ]


class PersonalAllocation(IdentifiedRecord):
    settlement = models.ForeignKey(
        PersonalSettlement, on_delete=models.PROTECT, related_name="allocations"
    )
    obligation = models.ForeignKey(
        PersonalObligation, on_delete=models.PROTECT, related_name="allocations"
    )
    amount = money_field()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["settlement", "obligation"], name="personal_settlement_allocation_once"
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="personal_allocation_positive"),
        ]


class PersonalConfirmation(IdentifiedRecord):
    settlement = models.ForeignKey(
        PersonalSettlement, on_delete=models.PROTECT, related_name="confirmations"
    )
    party = models.ForeignKey(PARTY, on_delete=models.PROTECT)
    actor = models.ForeignKey(USER, on_delete=models.PROTECT)
    mode = models.CharField(max_length=16)
    reference = models.CharField(max_length=500)
    confirmed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["settlement", "party"], name="personal_confirmation_once"
            )
        ]


class RecoveryResolution(IdentifiedRecord):
    obligation = models.ForeignKey(
        FounderObligation, on_delete=models.PROTECT, related_name="resolutions"
    )
    settlement = models.ForeignKey(
        PersonalSettlement, on_delete=models.PROTECT, related_name="resolutions"
    )
    corporate_transaction = models.ForeignKey(
        CorporateTransaction,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="recovery_resolutions",
    )
    personal_return = models.ForeignKey(
        PersonalSettlement,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="return_resolutions",
    )
    amount = money_field()
    reason = models.CharField(max_length=1000)
    authorized_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class FundingPlan(IdentifiedRecord):
    name = models.CharField(max_length=160)
    starts = models.DateField()
    months = models.PositiveSmallIntegerField(default=12)
    mode = models.CharField(max_length=16, default="founders")
    snapshot = models.JSONField(default=dict, blank=True)
    previous = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class FundingPledge(IdentifiedRecord):
    plan = models.ForeignKey(FundingPlan, on_delete=models.PROTECT, related_name="pledges")
    party = models.ForeignKey(PARTY, on_delete=models.PROTECT)
    month = models.DateField()
    currency = models.CharField(max_length=3)
    amount = money_field()
    status = models.CharField(max_length=16, default="requested")
    reference = models.CharField(max_length=200, blank=True)


class AnnualReserve(IdentifiedRecord):
    name = models.CharField(max_length=160)
    schedule = models.ForeignKey(
        "purchasing.RecurringExpenseSchedule", on_delete=models.PROTECT, related_name="reserves"
    )
    starts = models.DateField()
    renewal = models.DateField()
    currency = models.CharField(max_length=3)
    target = money_field()
    policy = models.ForeignKey(SharingPolicy, on_delete=models.PROTECT)
    previous = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, default="active")
    snapshot = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["schedule", "renewal"],
                condition=Q(status="active"),
                name="one_active_reserve_cycle",
            ),
            models.CheckConstraint(
                condition=Q(target__gt=0, renewal__gte=F("starts")), name="reserve_target_dates"
            ),
        ]


class FundingDesignation(IdentifiedRecord):
    receipt = models.ForeignKey(
        CorporateTransaction, on_delete=models.PROTECT, related_name="designations"
    )
    plan = models.ForeignKey(
        FundingPlan, null=True, blank=True, on_delete=models.PROTECT, related_name="designations"
    )
    reserve = models.ForeignKey(
        AnnualReserve, null=True, blank=True, on_delete=models.PROTECT, related_name="designations"
    )
    month = models.DateField()
    amount = money_field()
    consumed_by = models.ForeignKey(
        "purchasing.Expense",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reserve_funding",
    )
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0)
                & (
                    Q(plan__isnull=False, reserve__isnull=True)
                    | Q(plan__isnull=True, reserve__isnull=False)
                ),
                name="funding_designation_target",
            )
        ]


class FounderEvidence(IdentifiedRecord):
    file = models.OneToOneField(
        "files.StoredFile", on_delete=models.PROTECT, related_name="founder_evidence"
    )
    party = models.ForeignKey(PARTY, null=True, blank=True, on_delete=models.PROTECT)
    transaction = models.ForeignKey(
        CorporateTransaction,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="evidence",
    )
    settlement = models.ForeignKey(
        PersonalSettlement, null=True, blank=True, on_delete=models.PROTECT, related_name="evidence"
    )
    loan = models.ForeignKey(
        FounderLoan, null=True, blank=True, on_delete=models.PROTECT, related_name="evidence"
    )
    title = models.CharField(max_length=200)
    uploaded_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class CompanyFundingCoverage(IdentifiedRecord):
    """Explicit allocation of available company cash to a plan, never a cash receipt."""

    plan = models.ForeignKey(FundingPlan, on_delete=models.PROTECT, related_name="company_coverage")
    bank = models.ForeignKey("banking.BankAccount", on_delete=models.PROTECT)
    month = models.DateField()
    amount = money_field()
    status = models.CharField(max_length=16, default="active")
    expense = models.ForeignKey(
        "purchasing.Expense",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="company_funding_coverage",
    )
    reference = models.CharField(max_length=500)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="company_coverage_positive")
        ]


class ReserveDesignationTransfer(IdentifiedRecord):
    destination = models.ForeignKey(
        FundingDesignation,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transferred_from",
    )
    amount = money_field(null=True, blank=True)
    designation = models.ForeignKey(
        FundingDesignation, on_delete=models.PROTECT, related_name="transfers"
    )
    previous_reserve = models.ForeignKey(
        AnnualReserve, on_delete=models.PROTECT, related_name="funding_moved_out"
    )
    new_reserve = models.ForeignKey(
        AnnualReserve, on_delete=models.PROTECT, related_name="funding_moved_in"
    )
    reason = models.CharField(max_length=1000)
    actor = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class FundingConsumption(IdentifiedRecord):
    designation = models.ForeignKey(
        FundingDesignation, on_delete=models.PROTECT, related_name="consumptions"
    )
    expense = models.ForeignKey(
        "purchasing.Expense", on_delete=models.PROTECT, related_name="funding_consumptions"
    )
    amount = money_field()
    reverses = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    reason = models.CharField(max_length=1000, blank=True)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="funding_consumption_positive")
        ]


class FundingRelease(IdentifiedRecord):
    designation = models.ForeignKey(
        FundingDesignation, on_delete=models.PROTECT, related_name="releases"
    )
    amount = money_field()
    reason = models.CharField(max_length=1000)
    client_key = models.CharField(max_length=160, unique=True)
    created_by = models.ForeignKey(USER, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="funding_release_positive")
        ]
