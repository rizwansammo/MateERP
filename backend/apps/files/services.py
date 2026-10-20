"""Validated uploads and generated documents in private storage.

Images are decoded and re-encoded (dropping metadata and trailing payloads). PDFs
cannot be safely re-encoded, so uploaded PDFs are structurally parsed and rejected
when they are encrypted or contain active content (JavaScript, launch/open actions,
embedded files, XFA). No antivirus/malware scanner is integrated.
"""

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
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 200
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
# PDF names that make a document active or carry hidden payloads.
ACTIVE_PDF_KEYS = frozenset(
    {
        "/JavaScript",
        "/JS",
        "/OpenAction",
        "/AA",
        "/Launch",
        "/EmbeddedFile",
        "/EmbeddedFiles",
        "/RichMedia",
        "/XFA",
        "/SubmitForm",
        "/ImportData",
        "/GoToR",
        "/GoToE",
    }
)


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


def _clean_image(raw: bytes) -> tuple[bytes, str, int, int]:
    """Decode and re-encode an image; returns (data, format, width, height)."""
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
                return _reencode(image, fmt), fmt, image.width, image.height
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


def _save(data: bytes, *, purpose: str, ext: str, content_type: str, name: str, user, **dims):
    stored_name = private_storage().save(f"{purpose}/{uuid.uuid4().hex}.{ext}", ContentFile(data))
    try:
        return StoredFile.objects.create(
            purpose=purpose,
            storage_name=stored_name,
            original_name=_safe_display_name(name),
            content_type=content_type,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            uploaded_by=user,
            **dims,
        )
    except Exception:
        # The row failed (e.g. the surrounding transaction is aborting): no orphan file.
        private_storage().delete(stored_name)
        raise


def store_image(upload: UploadedFile, *, purpose: str, user) -> StoredFile:
    """Validate an uploaded image by its real content and store a clean copy."""
    if upload.size is None or upload.size > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": ["Images must be 2 MB or smaller."]})

    raw = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": ["Images must be 2 MB or smaller."]})
    data, fmt, width, height = _clean_image(raw)
    content_type, ext = ALLOWED_FORMATS[fmt]
    return _save(
        data,
        purpose=purpose,
        ext=ext,
        content_type=content_type,
        name=upload.name or "",
        user=user,
        width=width,
        height=height,
    )


def _active_pdf_names(reader) -> set[str]:
    """Walk every reachable PDF object (including object streams) for active keys."""
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

    found: set[str] = set()
    seen: set[tuple[int, int]] = set()
    stack = [reader.trailer]
    budget = 50_000
    while stack and budget:
        budget -= 1
        obj = stack.pop()
        if isinstance(obj, IndirectObject):
            key = (obj.idnum, obj.generation)
            if key in seen:
                continue
            seen.add(key)
            obj = obj.get_object()
        if isinstance(obj, DictionaryObject):
            for name, value in obj.items():
                if name in ACTIVE_PDF_KEYS:
                    found.add(str(name))
                if name == "/S" and value in ("/JavaScript", "/Launch", "/SubmitForm"):
                    found.add(str(value))
                stack.append(value)
        elif isinstance(obj, ArrayObject):
            stack.extend(obj)
    if not budget:
        found.add("too many objects")
    return found


def validate_pdf(raw: bytes) -> int:
    """Return the page count of a passive, unencrypted PDF or raise ValidationError."""
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    if not raw.startswith(b"%PDF-"):
        raise ValidationError({"file": ["The file is not a PDF document."]})
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if reader.is_encrypted:
            raise ValidationError({"file": ["Password-protected PDFs are not accepted."]})
        pages = len(reader.pages)
        active = _active_pdf_names(reader)
    except ValidationError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError, RecursionError) as exc:
        raise ValidationError({"file": ["The PDF is damaged or unreadable."]}) from exc
    if not 1 <= pages <= MAX_PDF_PAGES:
        raise ValidationError({"file": [f"PDFs must have between 1 and {MAX_PDF_PAGES} pages."]})
    if active:
        raise ValidationError(
            {"file": ["PDFs with scripts, actions, forms or embedded files are not accepted."]}
        )
    return pages


def store_document(upload: UploadedFile, *, purpose: str, user) -> StoredFile:
    """Store an uploaded PDF, PNG, JPEG or WEBP document after content validation."""
    if upload.size is None or upload.size > MAX_DOCUMENT_BYTES:
        raise ValidationError({"file": ["Documents must be 10 MB or smaller."]})
    raw = upload.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES or not raw:
        raise ValidationError({"file": ["Documents must be between 1 byte and 10 MB."]})
    name = upload.name or ""
    if raw.startswith(b"%PDF-"):
        validate_pdf(raw)
        return _save(
            raw, purpose=purpose, ext="pdf", content_type="application/pdf", name=name, user=user
        )
    try:
        data, fmt, width, height = _clean_image(raw)
    except ValidationError:
        raise ValidationError({"file": ["Upload a PDF, PNG, JPEG or WEBP document."]}) from None
    content_type, ext = ALLOWED_FORMATS[fmt]
    return _save(
        data,
        purpose=purpose,
        ext=ext,
        content_type=content_type,
        name=name,
        user=user,
        width=width,
        height=height,
    )


def store_generated_pdf(data: bytes, *, purpose: str, name: str, user) -> StoredFile:
    """Store a server-rendered PDF (trusted content) with its integrity hash."""
    if not data.startswith(b"%PDF-"):
        raise ValueError("Generated content is not a PDF.")
    return _save(
        data, purpose=purpose, ext="pdf", content_type="application/pdf", name=name, user=user
    )
