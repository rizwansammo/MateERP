import pytest

from apps.documents.formatting import in_words


@pytest.mark.parametrize(
    ("amount", "currency", "expected"),
    [
        ("100000000000.01", "BDT", "Taka Ten Thousand Crore and One Poisha Only"),
        ("1000000000000.01", "USD", "One Trillion US Dollars and One Cents Only"),
        ("123.000000", "JPY", "One Hundred Twenty-Three JPY Only"),
    ],
)
def test_receipt_words_cover_full_financial_amount_range(amount, currency, expected):
    assert in_words(amount, currency) == expected
