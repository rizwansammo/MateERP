"""Server-side PDF rendering of issued documents from their frozen snapshots.

The HTML/CSS templates reimplement the approved Meridian / Ledger / Atlas invoice and
Official / Compact receipt layouts (the same geometry as ``features/documents``).
Rendering reads only the document snapshot and its immutable ``BrandingVersion``, so
regenerating a missing PDF reproduces the issued content. Only vendored fonts and
embedded data URIs can be loaded; any other URL is refused.
"""

import base64
import math
from decimal import Decimal
from pathlib import Path

from django.template.loader import render_to_string
from django.utils.html import escape

from apps.files.services import private_storage

from . import formatting as f

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
SPACING = {"compact": (30, 12, 5), "regular": (42, 18, 8), "airy": (54, 24, 11)}
# Noto Sans Bengali supplies the Taka sign (৳) and Bengali names; Plex has neither.
STACKS = {
    "sans": '"Plex Sans", "Plex Sans Ext", "Noto Sans Bengali", "DejaVu Sans", sans-serif',
    "serif": '"Plex Serif", "Plex Sans Ext", "Noto Sans Bengali", "DejaVu Serif", serif',
    "mono": '"Plex Mono", "Noto Sans Bengali", "DejaVu Sans Mono", monospace',
}


def css_string(value) -> str:
    """Text for a CSS ``content`` string (margin boxes), never interpreted as markup."""
    text = str(value or "").replace("\\", "\\\\").replace('"', '\\"')
    return " ".join(text.split())


def _fetcher():
    from weasyprint.urls import URLFetcher

    allowed = FONT_DIR.as_uri() + "/"

    class DocumentFetcher(URLFetcher):
        def fetch(self, url, headers=None):
            if url.startswith("data:") or (url.startswith(allowed) and ".." not in url):
                return super().fetch(url, headers)
            raise ValueError("Documents may not load external resources.")

    return DocumentFetcher(allowed_protocols={"file", "data"}, allow_redirects=False)


def render_pdf(template: str, context: dict) -> bytes:
    from weasyprint import HTML

    html = render_to_string(template, {"fonts": FONT_DIR.as_uri(), **context})
    return HTML(string=html, url_fetcher=_fetcher()).write_pdf()


def data_uri(stored) -> str | None:
    if stored is None:
        return None
    storage = private_storage()
    if not storage.exists(stored.storage_name):
        return None
    with storage.open(stored.storage_name, "rb") as fh:
        payload = base64.b64encode(fh.read()).decode()
    return f"data:{stored.content_type};base64,{payload}"


def initials(name: str) -> str:
    return "".join(w[0] for w in (name or "MateERP").split() if w)[:2].upper()


def _arc(text: str, *, radius: float, top: bool, size: float, spacing: float) -> str:
    """Characters placed individually along an arc (renderer-independent textPath)."""
    advance = size * 0.64 + spacing
    step = advance / radius
    n = len(text)
    out = []
    for i, ch in enumerate(text):
        offset = (i - (n - 1) / 2) * step
        angle = -math.pi / 2 + offset if top else math.pi / 2 - offset
        x, y = radius * math.cos(angle), radius * math.sin(angle)
        rotation = math.degrees(angle) + (90 if top else -90)
        out.append(
            f'<text x="{x:.2f}" y="{y:.2f}" transform="rotate({rotation:.2f} {x:.2f} {y:.2f})" '
            f'text-anchor="middle" dy="0.35em">{escape(ch)}</text>'
        )
    return "".join(out)


def seal_svg(seal: dict, size: int = 112) -> str:
    """SVG company stamp matching the branding editor's circle and square geometry."""
    color = escape(seal.get("color") or "#1E4FD8")
    top = (seal.get("top") or "")[:30]
    bottom = (seal.get("bottom") or "")[:26]
    square = seal.get("shape") == "square"
    center = (seal.get("center") or "")[: 10 if square else 9]
    font = 'font-family="Plex Sans, sans-serif"'
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-180 -180 360 360" '
        f'width="{size}" height="{size}" fill="{color}" stroke="{color}">'
    )
    if square:
        body = (
            '<rect x="-164" y="-164" width="328" height="328" fill="none" stroke-width="7"/>'
            '<rect x="-150" y="-150" width="300" height="300" fill="none" stroke-width="2"/>'
            '<rect x="-120" y="-92" width="240" height="2" stroke="none"/>'
            '<rect x="-120" y="90" width="240" height="2" stroke="none"/>'
            f'<g stroke="none" text-anchor="middle" {font}>'
            f'<text y="-118" dy="0.35em" font-size="22" font-weight="700">{escape(top)}</text>'
            f'<text y="120" dy="0.35em" font-size="22" font-weight="700">{escape(bottom)}</text>'
            f'<text y="2" dy="0.35em" font-size="50" font-weight="800">{escape(center)}</text></g>'
        )
    else:
        body = (
            '<circle r="168" fill="none" stroke-width="7"/>'
            '<circle r="150" fill="none" stroke-width="2"/>'
            '<circle r="92" fill="none" stroke-width="2"/>'
            f'<g stroke="none" font-size="25" font-weight="700" {font}>'
            f"{_arc(top, radius=121, top=True, size=25, spacing=3)}"
            f"{_arc(bottom, radius=121, top=False, size=25, spacing=3)}</g>"
            f'<g stroke="none" text-anchor="middle" {font}>'
            '<text x="-121" y="1" dy="0.35em" font-size="20" font-weight="800">★</text>'
            '<text x="121" y="1" dy="0.35em" font-size="20" font-weight="800">★</text>'
            f'<text y="2" dy="0.35em" font-size="{30 if len(center) > 6 else 40}" '
            f'font-weight="800">{escape(center)}</text></g>'
        )
    return f"{head}{body}</svg>"


def _script_size(name: str, preferred: int, width: int) -> int:
    """Typed-signature font size that keeps the name inside the signature block."""
    # Herr Von Muellerhoff averages ~0.53em per character.
    fitted = int(width / (0.53 * max(len(name), 1)))
    return max(20, min(preferred, fitted))


def branding_context(version) -> dict:
    b = version.config
    typography = b.get("typography", "sans")
    ff = STACKS["serif"] if typography == "serif" else STACKS["sans"]
    nf = STACKS["mono"] if typography == "mono" else ff
    seal = b.get("seal") or {}
    return {
        "b": b,
        "ff": ff,
        "nf": nf,
        "logo": data_uri(version.logo),
        "signature": data_uri(version.signature),
        "seal_image": data_uri(version.seal_image) if seal.get("mode") == "image" else None,
        "seal_svg": seal_svg(seal) if seal.get("mode") == "editor" else None,
        "signature_size": _script_size(b.get("signature_name", ""), 36, 190),
        "signature_size_compact": _script_size(b.get("signature_name", ""), 34, 180),
        "signature_caption": " · ".join(
            x for x in (b.get("signature_title"), "Authorised signatory") if x
        ),
    }


def company_context(co: dict) -> dict:
    legal = co.get("legal_name") or co.get("display_name", "")
    contacts = [v for v in (co.get("email"), co.get("phone"), co.get("website")) if v]
    return {
        "co": co,
        "legal_name": legal,
        "initials": initials(co.get("display_name", "")),
        "address": "\n".join(co.get("address_lines") or []),
        "co_contacts": contacts,
        "co_contacts_line": " · ".join(contacts),
        "co_email_phone": " · ".join(v for v in (co.get("email"), co.get("phone")) if v),
    }


def _header(b) -> dict:
    hd = b.get("header_layout", "logo-left")
    pad, gap, row_pad = SPACING.get(b.get("spacing", "regular"), SPACING["regular"])
    tpl = b.get("invoice_template", "meridian")
    ts = b.get("table_style", "lined")
    return {
        "pad": pad,
        "gap": gap,
        "row_pad": row_pad,
        "head_dir": {"logo-right": "row-reverse", "centered": "column"}.get(hd, "row"),
        "head_align": "center" if hd == "centered" else "flex-start",
        "head_text": "center" if hd == "centered" else "left",
        "title_align": {"centered": "center", "logo-right": "flex-start"}.get(hd, "flex-end"),
        "th_bg": "transparent"
        if tpl == "ledger"
        else "#F3F4F6"
        if ts == "boxed"
        else b["brand_color"],
        "th_fg": "#111827" if tpl == "ledger" or ts == "boxed" else "#FFFFFF",
    }


def _lines(doc, fmt):
    rows = []
    for i, line in enumerate(doc["lines"], 1):
        if Decimal(line.get("line_discount") or 0) == 0:
            discount = "—"
        elif line.get("discount_type") == "fixed":
            discount = f.number(line["line_discount"], fmt["currency"], fmt["grouping"])
        else:
            discount = f.percent(line["discount_value"])
        rows.append(
            {
                "index": f"{i:02d}",
                "description": line["description"],
                "quantity": f.quantity(line["quantity"]),
                "unit_price": f.number(line["unit_price"], fmt["currency"], fmt["grouping"]),
                "discount": discount,
                "tax_rate": f.percent(line.get("tax_rate") or "0"),
                "amount": f.number(line["amount"], fmt["currency"], fmt["grouping"]),
            }
        )
    return rows


def _total_rows(doc, fmt, tax_label):
    t = doc["totals"]
    rows = [("Subtotal", f.money(t["subtotal"], fmt))]
    total_discount = Decimal(t["line_discount"]) + Decimal(t["document_discount"])
    if total_discount:
        rows.append(("Discount", f"−{f.money(total_discount, fmt)}"))
    included = "Includes " if doc.get("prices_include_tax") else ""
    for tax in doc["taxes"]:
        rows.append((f"{included}{tax_label} {f.percent(tax['rate'])}", f.money(tax["tax"], fmt)))
    return rows


def invoice_context(doc: dict, version, *, credit: bool = False) -> dict:
    b = version.config
    fmt = doc["format"]
    tax_label = doc.get("tax_label") or "VAT"
    customer = doc["customer"]
    address = "\n".join(
        x
        for x in (
            customer.get("address"),
            ", ".join(v for v in (customer.get("city"), customer.get("country")) if v),
        )
        if x
    )
    ctx = {
        **branding_context(version),
        **company_context(doc["company"]),
        **_header(b),
        "doc": doc,
        "customer": customer,
        "customer_address": address,
        "tax_registration_label": doc.get("tax_registration_label") or "Tax ID",
        "tax_reg": (
            f"{doc.get('tax_registration_label') or 'Tax ID'} {doc['company'].get('tax_id')}"
            if doc["company"].get("tax_id")
            else ""
        ),
        "lines": _lines(doc, fmt),
        "total_rows": _total_rows(doc, fmt, tax_label),
        "total": f.money(doc["totals"]["total"], fmt),
        "notes": doc.get("notes", ""),
        "prices_note": "Prices include tax." if doc.get("prices_include_tax") else "",
        "show_signature": b.get("show_signature_on_invoice")
        and (version.signature_id or b.get("signature_name")),
        "footer_css": css_string(b.get("footer_text", "")),
        "number_css": css_string(doc["number"]),
    }
    if not credit:
        ctx.update(
            title="INVOICE",
            ledger_title="Tax Invoice",
            atlas_title="Invoice",
            total_label="Total due",
            due_line=f"Due by {f.day(doc['due_date'])}",
            show_payment_instructions=True,
            show_terms=True,
            meta=[
                ("Invoice date", f.day(doc["issue_date"])),
                ("Due date", f.day(doc["due_date"])),
                ("Currency", fmt["currency"]),
            ],
            reference_block=_reference_block(doc),
        )
    else:
        ctx.update(
            title="CREDIT NOTE",
            ledger_title="Credit Note",
            atlas_title="Credit note",
            total_label="Total credit",
            due_line="",
            show_payment_instructions=False,
            show_terms=False,
            notes=f"Reason: {doc['reason']}",
            meta=[
                ("Credit note date", f.day(doc["issue_date"])),
                ("Original invoice", doc["invoice_number"]),
                ("Currency", fmt["currency"]),
            ],
            reference_block={
                "title": "Credits invoice",
                "name": doc["invoice_number"],
                "code": f"Issued {f.day(doc['invoice_issue_date'])}",
                "detail": "",
            },
        )
    return ctx


def _reference_block(doc):
    project = doc.get("project")
    if project:
        milestone = doc.get("milestone")
        return {
            "title": "Project",
            "name": project["name"],
            "code": project["reference"],
            "detail": f"Milestone: {milestone['name']}" if milestone else "",
        }
    if doc.get("reference"):
        return {"title": "Your reference", "name": doc["reference"], "code": "", "detail": ""}
    return None


def receipt_context(doc: dict, version) -> dict:
    b = version.config
    fmt = doc["format"]
    co = doc["company"]
    invoices = doc["allocations"]
    rows = [
        ("Received from", doc["customer"]["name"], False),
        ("Payment date", f.day(doc["payment_date"]), False),
        (
            "Against invoice" if len(invoices) == 1 else "Against invoices",
            ", ".join(a["number"] for a in invoices) or "Customer credit",
            True,
        ),
        ("Payment method", doc["method"], False),
        (
            "Invoice total" if len(invoices) == 1 else "Invoices total",
            f.money(_sum(invoices, "invoice_total"), fmt),
            True,
        ),
        ("Received into", doc["bank_account"], False),
        ("Currency", fmt["currency"], False),
        ("Reference", doc.get("reference") or "—", True),
    ]
    balance_lines = []
    if len(invoices) == 1:
        remaining = invoices[0]["balance_after"]
        settled = " — invoice fully settled" if Decimal(remaining) == 0 else ""
        balance_lines.append(
            ("Invoice balance after this receipt:", f"{f.money(remaining, fmt)}{settled}")
        )
    elif invoices:
        balance_lines.append(
            ("Balance remaining on these invoices:", f.money(_sum(invoices, "balance_after"), fmt))
        )
    if Decimal(doc.get("unapplied") or 0):
        balance_lines.append(("Held as customer credit:", f.money(doc["unapplied"], fmt)))
    return {
        **branding_context(version),
        **company_context(co),
        "doc": doc,
        "official": b.get("receipt_template", "official") == "official",
        "show_logo": b.get("show_logo_on_receipt") and version.logo_id is not None,
        "co_line": " · ".join(
            x
            for x in (", ".join(co.get("address_lines") or []), co.get("phone"), co.get("tax_id"))
            if x
        ),
        "rows": rows,
        "amount": f.money(doc["amount"], fmt),
        "amount_words": f.in_words(doc["amount"], fmt["currency"]),
        "balance_lines": balance_lines,
    }


def _sum(rows, key):
    return sum((Decimal(r[key]) for r in rows), Decimal(0))
