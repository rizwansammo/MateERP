"""Filed client and vendor documents. Folder trees are derived; files stay immutable."""

from django.conf import settings
from django.db import models
from django.db.models import Q

USER = settings.AUTH_USER_MODEL


class FiledDocument(models.Model):
    class Area(models.TextChoices):
        CLIENT = "client", "Client documents"
        VENDOR = "vendor", "Vendor documents"

    class Kind(models.TextChoices):
        INVOICE = "invoice", "Invoice"
        RECEIPT = "receipt", "Money receipt"
        CREDIT_NOTE = "credit_note", "Credit note"
        BANK_PROOF = "bank_proof", "Bank payment proof"
        CLIENT_SUPPORTING = "client_supporting", "Supporting document"
        VENDOR_INVOICE = "vendor_invoice", "Vendor invoice"
        VENDOR_RECEIPT = "vendor_receipt", "Vendor receipt"
        VENDOR_SUPPORTING = "vendor_supporting", "Supporting document"

    CLIENT_KINDS = ("invoice", "receipt", "credit_note", "bank_proof", "client_supporting")
    VENDOR_KINDS = ("vendor_invoice", "vendor_receipt", "vendor_supporting")
    GENERATED_KINDS = ("invoice", "receipt", "credit_note")

    area = models.CharField(max_length=8, choices=Area.choices)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    file = models.OneToOneField("files.StoredFile", on_delete=models.PROTECT, related_name="filed")
    title = models.CharField(max_length=200)
    document_date = models.DateField()
    generated = models.BooleanField(default=False)
    restricted = models.BooleanField(default=False)
    customer = models.ForeignKey(
        "sales.Customer", null=True, blank=True, on_delete=models.PROTECT, related_name="documents"
    )
    vendor = models.ForeignKey(
        "purchasing.Vendor",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    invoice = models.ForeignKey(
        "billing.Invoice", null=True, blank=True, on_delete=models.PROTECT, related_name="documents"
    )
    payment = models.ForeignKey(
        "billing.CustomerPayment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    receipt = models.ForeignKey(
        "billing.MoneyReceipt", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    credit_note = models.ForeignKey(
        "billing.CreditNote", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    vendor_bill = models.ForeignKey(
        "purchasing.VendorBill",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    expense = models.ForeignKey(
        "purchasing.Expense",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    vendor_payment = models.ForeignKey(
        "purchasing.VendorPayment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    notes = models.CharField(max_length=500, blank=True)
    is_archived = models.BooleanField(default=False)
    archived_reason = models.CharField(max_length=500, blank=True)
    archived_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-document_date", "-pk"]
        indexes = [models.Index(fields=["area", "document_date"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(area="client", customer__isnull=False, vendor__isnull=True)
                    & Q(
                        kind__in=[
                            "invoice",
                            "receipt",
                            "credit_note",
                            "bank_proof",
                            "client_supporting",
                        ]
                    )
                )
                | (
                    Q(area="vendor", vendor__isnull=False, customer__isnull=True)
                    & Q(kind__in=["vendor_invoice", "vendor_receipt", "vendor_supporting"])
                ),
                name="filed_document_area_consistent",
            ),
            models.CheckConstraint(
                condition=~Q(generated=True, is_archived=True), name="generated_never_archived"
            ),
            models.CheckConstraint(
                condition=~Q(kind="bank_proof") | Q(restricted=True), name="bank_proof_restricted"
            ),
            models.CheckConstraint(
                condition=Q(generated=False) | Q(kind__in=["invoice", "receipt", "credit_note"]),
                name="generated_kinds_only",
            ),
        ]

    def __str__(self):
        return self.title
