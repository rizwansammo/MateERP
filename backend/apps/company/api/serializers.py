import re
from zoneinfo import available_timezones

from rest_framework import serializers

from apps.company.models import BusinessSettings, CompanyProfile
from apps.company.reference import CURRENCIES, NUMBERING_KEYS
from apps.files.api.serializers import StoredFileSerializer, file_url

_PHONE = re.compile(r"^[0-9+()\-.\s]{5,40}$")


def validate_currency(value: str) -> str:
    code = value.upper()
    if code not in CURRENCIES:
        raise serializers.ValidationError("Unsupported currency.")
    return code


class CompanyProfileSerializer(serializers.ModelSerializer):
    logo = StoredFileSerializer(read_only=True)

    class Meta:
        model = CompanyProfile
        fields = [
            "display_name",
            "legal_name",
            "email",
            "phone",
            "website",
            "address_line1",
            "address_line2",
            "city",
            "region",
            "postal_code",
            "country",
            "tax_id",
            "registration_number",
            "base_currency",
            "time_zone",
            "fiscal_year_start_month",
            "notes",
            "logo",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["logo", "created_at", "updated_at"]

    def validate_display_name(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Enter the company's display name.")
        return value

    def validate_phone(self, value: str) -> str:
        if value and not _PHONE.match(value):
            raise serializers.ValidationError("Use digits, spaces and + ( ) - . only.")
        return value

    def validate_base_currency(self, value: str) -> str:
        return validate_currency(value)

    def validate_time_zone(self, value: str) -> str:
        if value not in available_timezones():
            raise serializers.ValidationError("Unknown time zone.")
        return value


class CompanySummarySerializer(serializers.Serializer):
    configured = serializers.BooleanField()
    display_name = serializers.CharField(allow_null=True)
    legal_name = serializers.CharField(allow_null=True)
    initials = serializers.CharField(allow_null=True)
    location = serializers.CharField(allow_null=True)
    logo_url = serializers.CharField(allow_null=True)

    @staticmethod
    def build(company: CompanyProfile | None) -> dict:
        if company is None:
            return {
                "configured": False,
                "display_name": None,
                "legal_name": None,
                "initials": None,
                "location": None,
                "logo_url": None,
            }
        words = [w for w in re.split(r"\s+", company.display_name) if w]
        return {
            "configured": True,
            "display_name": company.display_name,
            "legal_name": company.legal_name or None,
            "initials": "".join(w[0] for w in words)[:2].upper(),
            "location": ", ".join(p for p in (company.city, company.country) if p) or None,
            "logo_url": file_url(company.logo),
        }


class BusinessSettingsSerializer(serializers.ModelSerializer):
    enabled_currencies = serializers.ListField(
        child=serializers.CharField(max_length=3), max_length=len(CURRENCIES)
    )
    numbering = serializers.DictField(child=serializers.CharField(max_length=40))

    class Meta:
        model = BusinessSettings
        fields = [
            "currency_display",
            "number_grouping",
            "enabled_currencies",
            "tax_registered",
            "tax_label",
            "tax_registration_label",
            "default_tax_rate",
            "prices_include_tax",
            "numbering",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_enabled_currencies(self, value: list[str]) -> list[str]:
        return [validate_currency(v) for v in value]

    def validate_numbering(self, value: dict) -> dict:
        unknown = set(value) - set(NUMBERING_KEYS)
        if unknown:
            raise serializers.ValidationError(f"Unknown document types: {sorted(unknown)}")
        return value


class ModuleSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    phase = serializers.IntegerField()
    nav_id = serializers.CharField()
    enabled = serializers.BooleanField()
    implemented = serializers.BooleanField()


class ModuleUpdateSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()


class CurrencySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    symbol = serializers.CharField()
    minor_units = serializers.IntegerField()
