from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import DatabaseError, transaction
from rest_framework.exceptions import PermissionDenied

from apps.approvals.models import ApprovalPolicy
from apps.approvals.services import decide
from apps.assets import services
from apps.assets.models import Asset, AssetDisposal, DepreciationCharge
from apps.billing.services import credits, invoices
from apps.core.exceptions import BusinessRuleViolation
from apps.purchasing.services import payables

pytestmark = pytest.mark.django_db


def registration(books, source, **extra):
    return {
        "tag": "SERVER-01",
        "name": "Office server",
        "category": "Computers",
        "source_line_id": source.pk,
        "recognition_date": date(2026, 1, 1),
        "in_service_date": date(2026, 1, 1),
        "cost": "60000",
        "residual": "0",
        "useful_life_months": 60,
        "depreciation_account_id": books.accounts["6100"].pk,
        "reason": "Documented correction from initial expense classification to fixed asset",
        "key": "asset-register-server-01",
        **extra,
    }


def asset(books, equipment, **extra):
    obj = services.request_action(
        books.request, "capitalize", registration(books, equipment, **extra)
    )
    return Asset.objects.get(pk=obj.result_id)


def test_capitalization_claims_source_once_without_duplicate_ap_or_cash(
    books, equipment, admin_client
):
    source = admin_client.get("/api/v1/assets/acquisitions/?search=EQUIPMENT-001")
    assert source.status_code == 200 and source.data["results"][0]["id"] == equipment.pk
    assert source.data["results"][0]["source_reference"] == "EQUIPMENT-001"
    registered = asset(books, equipment)
    assert registered.cost == 60000
    assert services.available_acquisition(equipment) == 0
    assert registered.journal.lines.count() == 2
    assert not registered.journal.lines.filter(
        account__control__in=["payable", "receivable"]
    ).exists()
    assert services.request_action(
        books.request, "capitalize", registration(books, equipment)
    ).result_id == str(registered.pk)
    with pytest.raises(BusinessRuleViolation):
        asset(books, equipment, tag="DUPLICATE", key="second-asset-same-source")
    with pytest.raises(BusinessRuleViolation):
        payables.void_bill(
            books.request,
            equipment.journal.source_id,
            "Cannot independently undo capitalized acquisition",
        )
    with pytest.raises(DatabaseError), transaction.atomic():
        Asset.objects.filter(pk=registered.pk).update(cost="1")


def test_depreciation_schedule_and_prospective_estimate_preserve_posted_months(books, equipment):
    registered = asset(books, equipment)
    rows = services.schedule(registered)
    assert len(rows) == 60 and all(r["scheduled"] == 1000 for r in rows)
    first = services.request_action(
        books.request,
        "depreciation",
        {
            "asset_id": str(registered.pk),
            "month": date(2026, 1, 1),
            "recognition_date": date(2026, 1, 31),
            "reason": "January service charge",
            "key": "asset-january-charge-01",
        },
    )
    assert first.status == "done" and services.accumulated(registered) == 1000
    with pytest.raises(BusinessRuleViolation):
        services.request_action(
            books.request,
            "depreciation",
            {
                "asset_id": str(registered.pk),
                "month": date(2026, 3, 1),
                "recognition_date": date(2026, 3, 31),
                "reason": "Cannot skip February",
                "key": "skip-depreciation-month",
            },
        )
    services.request_action(
        books.request,
        "estimate",
        {
            "asset_id": str(registered.pk),
            "effective_date": date(2026, 2, 1),
            "remaining_months": 2,
            "residual": "1000",
            "reason": "Documented prospective life reassessment",
            "key": "asset-estimate-v2-01",
        },
    )
    rows = services.schedule(registered)
    assert rows[0]["posted"] == 1000
    assert [r["scheduled"] for r in rows] == [1000, 29000, 29000]
    assert registered.estimates.count() == 2
    charge = DepreciationCharge.objects.get()
    with pytest.raises(DatabaseError), transaction.atomic():
        DepreciationCharge.objects.filter(pk=charge.pk).update(amount="1")


def test_partial_month_and_exact_final_residual(books, equipment):
    registered = asset(
        books,
        equipment,
        cost="100",
        residual="10",
        useful_life_months=2,
        in_service_date=date(2026, 1, 16),
    )
    rows = services.schedule(registered)
    assert [r["scheduled"] for r in rows] == [Decimal("23.23"), Decimal("45"), Decimal("21.77")]
    assert sum((r["scheduled"] for r in rows), Decimal(0)) == 90


def test_disposal_sale_uses_actual_issued_receivable_without_posting_cash_twice(
    books, equipment, commerce
):
    registered = asset(books, equipment)
    doc = invoices.save_invoice(
        books.request,
        {
            "customer_id": commerce.customer.pk,
            "currency": "BDT",
            "issue_date": date(2026, 1, 31),
            "due_date": date(2026, 1, 31),
            "lines": [
                {
                    "description": "Sale of server",
                    "quantity": "1",
                    "unit_price": "65000",
                    "revenue_account_id": books.accounts["4100"].pk,
                }
            ],
        },
    )
    invoices.issue_invoice(books.request, doc.pk)
    action = services.request_action(
        books.request,
        "disposal",
        {
            "asset_id": str(registered.pk),
            "date": date(2026, 1, 31),
            "kind": "sale",
            "invoice_line_id": doc.lines.get().pk,
            "gain_account_id": books.accounts["4900"].pk,
            "loss_account_id": books.accounts["6100"].pk,
            "reason": "Approved server disposal and issued receivable",
            "key": "asset-sale-disposal-01",
        },
    )
    result = AssetDisposal.objects.get(pk=action.result_id)
    assert result.proceeds_base == 65000 and result.accumulated == 1000
    assert result.book_value == 59000 and result.gain_loss == 6000
    assert not result.journal.lines.filter(account__control="receivable").exists()
    assert not result.journal.lines.filter(account__code__in=["1010", "1020"]).exists()
    assert result.journal.lines.get(account=books.accounts["4900"]).base_credit == 6000
    with pytest.raises(BusinessRuleViolation):
        invoices.void_invoice(books.request, doc.pk, "Cannot undo retained disposal proceeds")
    with pytest.raises(BusinessRuleViolation):
        credits.request_credit_note(
            books.request,
            doc.pk,
            {
                "issue_date": date(2026, 2, 1),
                "reason": "Cannot bypass asset disposal",
                "lines": [{"invoice_line_id": doc.lines.get().pk, "amount": "100"}],
            },
            "asset-sale-credit-bypass",
        )


def test_retirement_prorates_disposal_month_and_never_creates_proceeds(books, equipment):
    registered = asset(books, equipment)
    services.request_action(
        books.request,
        "disposal",
        {
            "asset_id": str(registered.pk),
            "date": date(2026, 1, 15),
            "kind": "retirement",
            "loss_account_id": books.accounts["6100"].pk,
            "reason": "Irreparable documented damage",
            "key": "asset-retirement-01",
        },
    )
    result = registered.disposal
    assert result.proceeds_base == 0 and result.accumulated == Decimal("483.87")
    assert result.book_value == Decimal("59516.13")
    assert services.accumulated(registered) == Decimal("483.87")
    with pytest.raises(BusinessRuleViolation):
        services.request_action(
            books.request,
            "disposal",
            {
                "asset_id": str(registered.pk),
                "date": date(2026, 1, 16),
                "kind": "retirement",
                "loss_account_id": books.accounts["6100"].pk,
                "reason": "No double disposal",
                "key": "second-asset-disposal",
            },
        )


def test_capitalization_approval_and_restricted_direct_api(books, equipment, make_user, client_for):
    ApprovalPolicy.objects.filter(category="financial_adjustments").update(
        is_required=True, is_active=True
    )
    action = services.request_action(books.request, "capitalize", registration(books, equipment))
    assert action.status == "pending" and not Asset.objects.exists()
    with pytest.raises(PermissionDenied):
        decide(books.request, action.approval_id, approve=True)
    reviewer = SimpleNamespace(user=make_user("asset-reviewer", "administrator"), META={})
    decide(
        reviewer,
        action.approval_id,
        approve=True,
        reason="Acquisition evidence and capitalization checked",
    )
    assert Asset.objects.count() == 1
    viewer = client_for(make_user("asset-viewer"))
    assert viewer.get("/api/v1/assets/register/").status_code == 200
    assert viewer.post("/api/v1/assets/register/", {}, format="json").status_code == 403


def test_project_costs_remove_capitalized_expense_and_include_only_actual_depreciation(
    books, equipment, commerce, client_for
):
    from apps.sales.services import save_project

    project = save_project(
        books.request,
        {
            "reference": "ASSET-PROJECT",
            "name": "Project equipment",
            "customer_id": commerce.customer.pk,
            "currency": "BDT",
            "contract_value": "10000",
        },
    )
    vendor = payables.save_vendor(
        books.request, {"name": "Project asset supplier", "currency": "BDT"}
    )
    bill = payables.save_bill(
        books.request,
        {
            "vendor_id": vendor.pk,
            "vendor_reference": "PROJECT-ASSET-SOURCE",
            "project_id": project.pk,
            "bill_date": date(2026, 1, 1),
            "due_date": date(2026, 1, 1),
            "currency": "BDT",
            "lines": [
                {
                    "description": "Project server",
                    "quantity": "1",
                    "unit_price": "6000",
                    "account_id": books.accounts["6100"].pk,
                }
            ],
        },
    )
    payables.post_bill(books.request, bill.pk)
    bill.refresh_from_db()
    source = bill.journal.lines.get(account=books.accounts["6100"])
    registered = asset(
        books, source, cost="6000", tag="PROJECT-SERVER", key="project-asset-register"
    )
    client = client_for(books.request.user)
    data = client.get(f"/api/v1/billing/projects/{project.pk}/financials/").data
    assert Decimal(data["base_costs"]) == 0
    services.request_action(
        books.request,
        "depreciation",
        {
            "asset_id": str(registered.pk),
            "month": date(2026, 1, 1),
            "recognition_date": date(2026, 1, 31),
            "reason": "Project service charge",
            "key": "project-asset-depreciation",
        },
    )
    data = client.get(f"/api/v1/billing/projects/{project.pk}/financials/").data
    assert Decimal(data["base_costs"]) == 100 and Decimal(data["base_margin"]) == -100


@pytest.mark.django_db(transaction=True)
def test_unused_capitalization_can_be_reversed_and_replaced_without_losing_source(
    books, equipment, admin_client
):
    registered = asset(books, equipment)
    data = {
        "asset_id": str(registered.pk),
        "recognition_date": date(2026, 10, 1),
        "reason": "Correct unused duplicate equipment registration",
        "key": "reverse-unused-capitalization",
    }
    action = services.request_action(books.request, "cancel", data)
    registered.refresh_from_db()
    assert registered.cancellation.journal.reversal_of_id == registered.journal_id
    assert services.available_acquisition(equipment) == 60000
    assert services.schedule(registered) == []
    assert services.reconciliation()["cost_difference"] == 0
    result = admin_client.get(f"/api/v1/assets/register/{registered.pk}/")
    assert result.status_code == 200 and result.data["status"] == "cancelled"
    assert (
        result.data["book_value"] == "0" and result.data["cancellation"]["reason"] == data["reason"]
    )
    assert services.request_action(books.request, "cancel", data).pk == action.pk
    with pytest.raises(BusinessRuleViolation):
        payables.void_bill(
            books.request,
            equipment.journal.source_id,
            "Cannot predate retained claim release",
            date(2026, 1, 1),
        )
    # Historical identity retained; the available source can fund a corrected registration.
    with pytest.raises(BusinessRuleViolation):
        asset(books, equipment, tag="BACKDATED-REPLACEMENT", key="backdated-replacement-source")
    replacement = asset(
        books,
        equipment,
        tag="CORRECTED-SERVER",
        key="replacement-server-register",
        recognition_date=date(2026, 10, 1),
    )
    assert replacement.pk != registered.pk and Asset.objects.count() == 2
    assert services.reconciliation()["cost_difference"] == 0


def test_posted_depreciation_blocks_simple_capitalization_reversal(books, equipment):
    registered = asset(books, equipment)
    services.request_action(
        books.request,
        "depreciation",
        {
            "asset_id": str(registered.pk),
            "month": date(2026, 1, 1),
            "recognition_date": date(2026, 1, 31),
            "reason": "Verified service month",
            "key": "charge-before-cancellation",
        },
    )
    with pytest.raises(BusinessRuleViolation):
        services.request_action(
            books.request,
            "cancel",
            {
                "asset_id": str(registered.pk),
                "recognition_date": date(2026, 10, 1),
                "reason": "Cannot erase consumed service months",
                "key": "cancel-after-depreciation",
            },
        )
    assert services.available_acquisition(equipment) == 0
