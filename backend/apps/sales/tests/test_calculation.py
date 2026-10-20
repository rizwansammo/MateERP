"""Scenario C: exact discount, tax and rounding rules (server-authoritative)."""

from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from rest_framework.exceptions import ValidationError

from apps.accounting.services.setup import save_tax
from apps.sales.calculation import allocate, calculate

pytestmark = pytest.mark.django_db
DAY = date(2026, 10, 10)


def calc(books, lines, **kw):
    return calculate(currency=kw.pop("currency", "BDT"), on=kw.pop("on", DAY), lines=lines, **kw)


def vat_line(books, **kw):
    return {"quantity": "1", "unit_price": "10000", "tax_code_id": books.vat.pk, **kw}


def test_tax_exclusive_reference_example(books):
    r = calc(books, [vat_line(books)])
    assert (r["taxable"], r["tax"], r["total"]) == (D("10000.00"), D("1000.00"), D("11000.00"))
    assert r["taxes"][0]["tax"] == D("1000.00") and r["taxes"][0]["code"] == "VAT10"


def test_tax_inclusive_extracts_tax(books):
    r = calc(books, [vat_line(books, unit_price="11000")], prices_include_tax=True)
    assert (r["taxable"], r["tax"], r["total"]) == (D("10000.00"), D("1000.00"), D("11000.00"))
    odd = calc(books, [vat_line(books, unit_price="100")], prices_include_tax=True)
    # 100 / 1.1 = 90.909… → 90.91 taxable, tax is the exact remainder.
    assert (odd["taxable"], odd["tax"], odd["total"]) == (D("90.91"), D("9.09"), D("100"))


def test_line_and_document_discounts_in_documented_order(books):
    r = calc(
        books,
        [
            vat_line(books, quantity="2", unit_price="1000", discount_value="10"),
            vat_line(books, unit_price="500", discount_type="fixed", discount_value="50"),
        ],
        discount_type="fixed",
        discount_value="100",
    )
    first, second = r["lines"]
    assert (first["subtotal"], first["line_discount"], first["amount"]) == (
        D("2000.00"),
        D("200.00"),
        D("1800.00"),
    )
    assert second["amount"] == D("450.00")
    # 100 split 1800:450 → 80 / 20 exactly.
    assert (first["document_discount"], second["document_discount"]) == (D("80.00"), D("20.00"))
    assert r["taxable"] == D("2150.00") and r["tax"] == D("215.00") and r["total"] == D("2365.00")


def test_document_discount_allocation_sums_exactly():
    assert allocate(D("100.00"), [D(1), D(1), D(1)], "BDT") == [D("33.34"), D("33.33"), D("33.33")]
    assert sum(allocate(D("0.05"), [D("3"), D("7"), D("11")], "USD")) == D("0.05")
    assert allocate(D("10"), [D(1), D(2)], "JPY") == [D(3), D(7)]


def test_half_up_rounding_and_currency_precision(books):
    r = calc(books, [{"quantity": "1", "unit_price": "0.125"}])
    assert r["total"] == D("0.13")
    jpy = calc(books, [{"quantity": "3", "unit_price": "33.5"}], currency="JPY")
    assert jpy["total"] == D("101")


@pytest.mark.parametrize(
    ("line", "extra"),
    [
        ({"quantity": "0", "unit_price": "1"}, {}),
        ({"quantity": 1.5, "unit_price": "1"}, {}),
        ({"quantity": "1", "unit_price": "10", "discount_value": "101"}, {}),
        (
            {"quantity": "1", "unit_price": "10", "discount_type": "fixed", "discount_value": "11"},
            {},
        ),
        (
            {"quantity": "1", "unit_price": "10"},
            {"discount_type": "fixed", "discount_value": "10.01"},
        ),
        ({"quantity": "1", "unit_price": "-1"}, {}),
    ],
)
def test_invalid_inputs_rejected(books, line, extra):
    with pytest.raises(ValidationError):
        calc(books, [line], **extra)


def test_tax_rate_effective_on_document_date(books):
    request = SimpleNamespace(user=books.request.user, META={})
    save_tax(
        request,
        {
            "revision": {
                "effective_date": date(2026, 11, 1),
                "percent": "15",
                "input_account_id": books.accounts["1150"].pk,
                "output_account_id": books.accounts["2100"].pk,
            }
        },
        books.vat.pk,
    )
    assert calc(books, [vat_line(books)])["tax"] == D("1000.00")
    assert calc(books, [vat_line(books)], on=date(2026, 11, 2))["tax"] == D("1500.00")
    with pytest.raises(ValidationError):
        calc(books, [vat_line(books)], on=date(2025, 12, 31))
