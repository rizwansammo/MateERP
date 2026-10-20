import io
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Role, User

PASSWORD = "Ledger-Harbor-2026!"


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def csrf_client() -> APIClient:
    """A client that enforces CSRF exactly like a browser session would."""
    client = APIClient(enforce_csrf_checks=True)
    client.get("/api/v1/auth/csrf/")
    client.credentials(HTTP_X_CSRFTOKEN=client.cookies["mateerp_csrftoken"].value)
    return client


@pytest.fixture
def make_user(db):
    def factory(
        username: str,
        role: str | None = "viewer",
        *,
        active: bool = True,
        must_change: bool = False,
        email: str | None = None,
    ) -> User:
        user = User(
            username=username,
            email=email or f"{username}@example.test",
            first_name=username.capitalize(),
            role=Role.objects.get(key=role) if role else None,
            is_active=active,
            must_change_password=must_change,
        )
        user.set_password(PASSWORD)
        user.save()
        return user

    return factory


@pytest.fixture
def admin_user(make_user) -> User:
    return make_user("admin", "administrator")


@pytest.fixture
def client_for():
    def factory(user: User) -> APIClient:
        client = APIClient()
        client.force_login(user)
        return client

    return factory


@pytest.fixture
def admin_client(client_for, admin_user) -> APIClient:
    return client_for(admin_user)


def image_bytes(fmt: str = "PNG", size=(60, 30), color=(0, 176, 240)) -> bytes:
    mode = "RGB" if fmt == "JPEG" else "RGBA"
    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, fmt)
    return buffer.getvalue()


def upload(
    name: str = "logo.png", data: bytes | None = None, content_type: str = "image/png"
) -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name, data if data is not None else image_bytes(), content_type=content_type
    )


@pytest.fixture
def company(admin_client):
    response = admin_client.post(
        "/api/v1/company/",
        {
            "display_name": "NetaMate",
            "city": "Dhaka",
            "country": "Bangladesh",
            "base_currency": "BDT",
            "time_zone": "Asia/Dhaka",
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    return response.json()


@pytest.fixture
def user_with(make_user):
    """A user whose custom role holds exactly ``codes`` (no implicit grants)."""

    def factory(username: str, *codes: str) -> User:
        from apps.accounts.models import Permission

        role = Role.objects.create(key=f"role-{username}", name=f"Role {username}")
        role.permissions.set(Permission.objects.filter(code__in=codes))
        user = make_user(username, None)
        user.role = role
        user.save()
        return user

    return factory


@pytest.fixture
def books(admin_user, company):
    """Starter chart, FY2026, subledger controls and a 10% VAT code (admin-configured)."""
    from datetime import date

    from apps.accounting.services.setup import create_year, save_account, save_tax, setup_chart

    request = SimpleNamespace(user=admin_user, META={})
    accounts = {a.code: a for a in setup_chart(request)}
    create_year(request, date(2026, 1, 1))
    for code, control in (("1100", "receivable"), ("2010", "payable")):
        accounts[code] = save_account(request, {"control": control}, accounts[code].pk)
    accounts["2200"] = save_account(
        request,
        {
            "code": "2200",
            "name": "Customer credits & advances",
            "account_type": "liability",
            "parent_id": accounts["2000"].pk,
            "control": "customer_credit",
        },
    )
    vat = save_tax(
        request,
        {
            "code": "VAT10",
            "name": "VAT 10%",
            "revision": {
                "effective_date": date(2026, 1, 1),
                "percent": "10",
                "input_account_id": accounts["1150"].pk,
                "output_account_id": accounts["2100"].pk,
            },
        },
    )
    return SimpleNamespace(request=request, accounts=accounts, vat=vat)


@pytest.fixture
def commerce(books, user_with):
    """Configured books, published branding, a BDT bank, a customer and segregated users."""
    from apps.banking import services as banking
    from apps.branding.services import publish
    from apps.sales.services import save_customer

    admin = books.request
    publish(admin, label="Launch branding")
    bank = banking.save_account(
        admin,
        {
            "name": "Operating bank",
            "kind": "bank",
            "currency": "BDT",
            "gl_account_id": books.accounts["1020"].pk,
        },
    )
    customer = save_customer(
        admin, {"name": "Acme Trading Ltd", "currency": "BDT", "payment_terms_days": 30}
    )
    users = SimpleNamespace(
        clerk=user_with("clerk", "finance.view", "invoices.create"),
        issuer=user_with("issuer", "finance.view", "invoices.create", "invoices.issue"),
        recorder=user_with("recorder", "finance.view", "payments.record"),
        verifier=user_with("verifier", "finance.view", "payments.approve"),
        crediter=user_with("crediter", "finance.view", "credit_notes.manage"),
        viewer=user_with("viewer", "finance.view"),
    )
    return SimpleNamespace(books=books, admin=admin, bank=bank, customer=customer, users=users)
