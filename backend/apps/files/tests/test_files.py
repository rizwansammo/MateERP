import io
import uuid
from pathlib import Path

import pytest
from django.conf import settings
from PIL import Image

from apps.accounts.models import Permission, Role
from apps.files.models import FilePurpose, StoredFile
from apps.files.services import store_image
from conftest import image_bytes, upload

pytestmark = pytest.mark.django_db


def test_storage_path_ignores_client_filename(admin_user):
    stored = store_image(
        upload("../../etc/passwd.png"), purpose=FilePurpose.COMPANY_LOGO, user=admin_user
    )
    assert ".." not in stored.storage_name and "passwd" not in stored.storage_name
    assert stored.storage_name.startswith("company_logo/")
    path = Path(settings.PRIVATE_STORAGE_ROOT, stored.storage_name).resolve()
    assert path.is_relative_to(Path(settings.PRIVATE_STORAGE_ROOT).resolve())
    assert "/" not in stored.original_name


def test_reencoding_strips_metadata_and_trailing_payload(admin_user):
    image = Image.new("RGB", (40, 40), (10, 20, 30))
    buffer = io.BytesIO()
    exif = Image.Exif()
    exif[0x010E] = "GPS secret location"
    image.save(buffer, "JPEG", exif=exif)
    payload = buffer.getvalue() + b"<?php system($_GET['x']); ?>"

    stored = store_image(
        upload("photo.jpg", payload, "image/jpeg"),
        purpose=FilePurpose.COMPANY_LOGO,
        user=admin_user,
    )
    data = Path(settings.PRIVATE_STORAGE_ROOT, stored.storage_name).read_bytes()
    assert b"<?php" not in data and b"GPS secret" not in data
    assert stored.content_type == "image/jpeg" and stored.width == 40


def _file(admin_user, purpose):
    return store_image(upload(), purpose=purpose, user=admin_user)


def url(stored):
    return f"/api/v1/files/{stored.pk}/content/"


def test_anonymous_access_denied(api_client, admin_user):
    stored = _file(admin_user, FilePurpose.COMPANY_LOGO)
    assert api_client.get(url(stored)).status_code == 401


def test_unreferenced_logo_only_for_branding_managers(
    admin_user, admin_client, make_user, client_for
):
    stored = _file(admin_user, FilePurpose.COMPANY_LOGO)
    viewer = client_for(make_user("v1", "viewer"))
    assert viewer.get(url(stored)).status_code == 404
    response = admin_client.get(url(stored))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert "sandbox" in response["Content-Security-Policy"]
    assert response["Cache-Control"].startswith("private")


def test_signature_and_seal_require_branding_manage(
    admin_user, admin_client, make_user, client_for, company
):
    for kind in ("signature", "seal"):
        admin_client.post(
            f"/api/v1/branding/draft/assets/{kind}/", {"file": upload()}, format="multipart"
        )
    files = StoredFile.objects.filter(
        purpose__in=[FilePurpose.BRANDING_SIGNATURE, FilePurpose.BRANDING_SEAL]
    )
    assert files.count() == 2

    # company.view is not enough for sensitive document assets.
    accountant = client_for(make_user("acc", "accountant"))
    designer_role = Role.objects.create(key="designer", name="Designer")
    designer_role.permissions.set(Permission.objects.filter(code="branding.manage"))
    designer = make_user("des", None)
    designer.role = designer_role
    designer.save()
    for stored in files:
        assert accountant.get(url(stored)).status_code == 404
        assert client_for(designer).get(url(stored)).status_code == 200
        assert admin_client.get(url(stored)).status_code == 200


def test_unknown_file_is_404(admin_client):
    assert admin_client.get(f"/api/v1/files/{uuid.uuid4()}/content/").status_code == 404


def test_deactivated_user_loses_file_access(
    admin_user, company, admin_client, make_user, client_for
):
    admin_client.post(
        "/api/v1/company/logo/", {"file": upload(data=image_bytes())}, format="multipart"
    )
    stored = StoredFile.objects.get(purpose=FilePurpose.COMPANY_LOGO)
    user = make_user("v1", "viewer")
    client = client_for(user)
    assert client.get(url(stored)).status_code == 200
    user.is_active = False
    user.save()
    assert client.get(url(stored)).status_code == 401
