import io

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
