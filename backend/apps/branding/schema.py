"""Invoice & receipt branding configuration: defaults and validation.

The option set mirrors the approved MateERP-UI prototype (templates Meridian,
Ledger and Atlas; Official and Compact receipts; a stamp-style seal).
"""

import re

from rest_framework import serializers

HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")

DEFAULT_CONFIG: dict = {
    "invoice_template": "meridian",
    "brand_color": "#0B2A4A",
    "accent_color": "#00B0F0",
    "header_layout": "logo-left",
    "typography": "sans",
    "spacing": "regular",
    "table_style": "lined",
    "logo_size": 52,
    "footer_text": "Thank you for your business.",
    "terms": "Payment is due within the agreed terms. Please quote the invoice number with "
    "your remittance.",
    "payment_instructions": "",
    "custom_fields": [],
    "signature_name": "",
    "signature_title": "",
    "show_signature_on_invoice": True,
    "show_signature_on_receipt": True,
    "receipt_template": "official",
    "receipt_confirmation": "Received with thanks the sum stated below towards settlement of "
    "the referenced invoice.",
    "receipt_footer": "This is a system-generated official money receipt.",
    "show_logo_on_receipt": True,
    "seal": {
        "mode": "none",
        "top": "",
        "center": "PAID",
        "bottom": "",
        "color": "#1E4FD8",
        "shape": "circle",
    },
}


def _hex(value: str) -> str:
    if not HEX_COLOR.match(value):
        raise serializers.ValidationError("Use a 6-digit hex colour such as #0B2A4A.")
    return value.upper()


class CustomFieldSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=40)
    value = serializers.CharField(max_length=80)


class SealSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=["editor", "image", "none"])
    top = serializers.CharField(max_length=30, allow_blank=True)
    center = serializers.CharField(max_length=9, allow_blank=True)
    bottom = serializers.CharField(max_length=26, allow_blank=True)
    color = serializers.CharField(max_length=7)
    shape = serializers.ChoiceField(choices=["circle", "square"])

    def validate_color(self, value: str) -> str:
        return _hex(value)


class BrandingConfigSerializer(serializers.Serializer):
    invoice_template = serializers.ChoiceField(choices=["meridian", "ledger", "atlas"])
    brand_color = serializers.CharField(max_length=7)
    accent_color = serializers.CharField(max_length=7)
    header_layout = serializers.ChoiceField(choices=["logo-left", "logo-right", "centered"])
    typography = serializers.ChoiceField(choices=["sans", "serif", "mono"])
    spacing = serializers.ChoiceField(choices=["compact", "regular", "airy"])
    table_style = serializers.ChoiceField(choices=["lined", "striped", "boxed"])
    logo_size = serializers.IntegerField(min_value=24, max_value=120)
    footer_text = serializers.CharField(max_length=200, allow_blank=True)
    terms = serializers.CharField(max_length=2000, allow_blank=True)
    payment_instructions = serializers.CharField(max_length=1000, allow_blank=True)
    custom_fields = CustomFieldSerializer(many=True, max_length=6)
    signature_name = serializers.CharField(max_length=80, allow_blank=True)
    signature_title = serializers.CharField(max_length=80, allow_blank=True)
    show_signature_on_invoice = serializers.BooleanField()
    show_signature_on_receipt = serializers.BooleanField()
    receipt_template = serializers.ChoiceField(choices=["official", "compact"])
    receipt_confirmation = serializers.CharField(max_length=500, allow_blank=True)
    receipt_footer = serializers.CharField(max_length=300, allow_blank=True)
    show_logo_on_receipt = serializers.BooleanField()
    seal = SealSerializer()

    def validate_brand_color(self, value: str) -> str:
        return _hex(value)

    def validate_accent_color(self, value: str) -> str:
        return _hex(value)


def normalise_config(config: dict) -> dict:
    """Merge with defaults (for older stored configs) and validate."""
    merged = {**DEFAULT_CONFIG, **(config or {})}
    merged["seal"] = {**DEFAULT_CONFIG["seal"], **(merged.get("seal") or {})}
    serializer = BrandingConfigSerializer(data=merged)
    serializer.is_valid(raise_exception=True)
    data = dict(serializer.validated_data)
    data["seal"] = dict(data["seal"])
    data["custom_fields"] = [dict(f) for f in data["custom_fields"]]
    return data
