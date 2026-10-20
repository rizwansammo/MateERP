"""Validated image uploads into private storage."""

import hashlib
import io
import re
import unicodedata
import uuid
import warnings

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

from .models import StoredFile

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 4000
# Pillow raises DecompressionBombError beyond twice this many pixels and warns
# beyond it; warnings are promoted to errors below.
Image.MAX_IMAGE_PIXELS = MAX_DIMENSION * MAX_DIMENSION

# Pillow format -> (content type, extension). Anything else is rejected,
# including SVG, which can carry active content.
ALLOWED_FORMATS = {
    "PNG": ("image/png", "png"),
    "JPEG": ("image/jpeg", "jpg"),
    "WEBP": ("image/webp", "webp"),
}


def private_storage() -> FileSystemStorage:
    # No base_url: files are never addressable by URL, only via API views.
    return FileSystemStorage(location=settings.PRIVATE_STORAGE_ROOT, base_url=None)


def _safe_display_name(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = unicodedata.normalize("NFKC", base)
    base = re.sub(r"[^\w.\- ()]", "_", base).strip(" .")
    return base[:120] or "upload"


def _reencode(image: Image.Image, fmt: str) -> bytes:
    """Re-encode decoded pixels, dropping metadata and any trailing payload."""
    image = ImageOps.exif_transpose(image)
    out = io.BytesIO()
    if fmt == "JPEG":
        image.convert("RGB").save(out, "JPEG", quality=92, optimize=True)
    elif fmt == "PNG":
        if image.mode not in ("1", "L", "LA", "P", "RGB", "RGBA"):
            image = image.convert("RGBA")
        image.save(out, "PNG", optimize=True)
    else:
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")
        image.save(out, "WEBP", lossless=True)
    return out.getvalue()


def store_image(upload: UploadedFile, *, purpose: str, user) -> StoredFile:
    """Validate an uploaded image by its real content and store a clean copy."""
    if upload.size is None or upload.size > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": ["Images must be 2 MB or smaller."]})

    raw = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": ["Images must be 2 MB or smaller."]})

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                fmt = probe.format
                probe.verify()
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                if fmt not in ALLOWED_FORMATS:
                    raise ValidationError({"file": ["Upload a PNG, JPEG or WEBP image."]})
                if image.width > MAX_DIMENSION or image.height > MAX_DIMENSION:
                    raise ValidationError(
                        {
                            "file": [
                                f"Images must be at most {MAX_DIMENSION}×{MAX_DIMENSION} pixels."
                            ]
                        }
                    )
                data = _reencode(image, fmt)
                width, height = image.width, image.height
    except ValidationError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValidationError(
            {"file": ["The file is not a valid PNG, JPEG or WEBP image."]}
        ) from exc

    content_type, ext = ALLOWED_FORMATS[fmt]
    name = f"{purpose}/{uuid.uuid4().hex}.{ext}"
    stored_name = private_storage().save(name, ContentFile(data))
    return StoredFile.objects.create(
        purpose=purpose,
        storage_name=stored_name,
        original_name=_safe_display_name(upload.name or ""),
        content_type=content_type,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        width=width,
        height=height,
        uploaded_by=user,
    )
