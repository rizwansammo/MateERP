from datetime import date
from types import SimpleNamespace

DAY = date(2026, 10, 10)


def as_user(user):
    return SimpleNamespace(user=user, META={})


def draft(commerce, *, lines=None, user=None, **header):
    from apps.billing.services.invoices import save_invoice

    data = {
        "customer_id": commerce.customer.pk,
        "issue_date": DAY,
        "lines": lines
        or [
            {
                "description": "Consulting",
                "quantity": "1",
                "unit_price": "10000",
                "tax_code_id": commerce.books.vat.pk,
                "revenue_account_id": commerce.books.accounts["4100"].pk,
            }
        ],
        **header,
    }
    return save_invoice(as_user(user or commerce.users.issuer), data)


def issued(commerce, **kw):
    from apps.billing.services.invoices import issue_invoice

    invoice = draft(commerce, **kw)
    return issue_invoice(as_user(commerce.users.issuer), invoice.pk)
