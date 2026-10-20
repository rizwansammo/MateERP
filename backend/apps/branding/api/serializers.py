from rest_framework import serializers

from apps.accounts.authorization import has_perm
from apps.branding.models import BrandingDraft, BrandingVersion
from apps.files.api.serializers import file_url


def _asset_url(stored, user) -> str | None:
    # Signatures and seals are only exposed to branding managers (see files.access).
    return file_url(stored) if stored is not None and has_perm(user, "branding.manage") else None


class VersionSummarySerializer(serializers.ModelSerializer):
    published_by = serializers.CharField(source="published_by.display_name")
    invoice_template = serializers.CharField(source="config.invoice_template")
    receipt_template = serializers.CharField(source="config.receipt_template")
    brand_color = serializers.CharField(source="config.brand_color")
    accent_color = serializers.CharField(source="config.accent_color")
    restored_from = serializers.IntegerField(
        source="restored_from.number", allow_null=True, default=None
    )
    approved = serializers.SerializerMethodField()

    class Meta:
        model = BrandingVersion
        fields = [
            "number",
            "label",
            "invoice_template",
            "receipt_template",
            "brand_color",
            "accent_color",
            "published_by",
            "published_at",
            "restored_from",
            "approved",
        ]
        read_only_fields = fields

    def get_approved(self, obj) -> bool:
        return obj.approval_request_id is not None


class VersionDetailSerializer(VersionSummarySerializer):
    config = serializers.JSONField()
    company = serializers.JSONField()
    numbering = serializers.JSONField()
    logo_url = serializers.SerializerMethodField()
    signature_url = serializers.SerializerMethodField()
    seal_image_url = serializers.SerializerMethodField()

    class Meta(VersionSummarySerializer.Meta):
        fields = [
            *VersionSummarySerializer.Meta.fields,
            "config",
            "company",
            "numbering",
            "logo_url",
            "signature_url",
            "seal_image_url",
        ]
        read_only_fields = fields

    def get_logo_url(self, obj) -> str | None:
        return file_url(obj.logo)

    def get_signature_url(self, obj) -> str | None:
        return _asset_url(obj.signature, self.context["user"])

    def get_seal_image_url(self, obj) -> str | None:
        return _asset_url(obj.seal_image, self.context["user"])


class DraftSerializer(serializers.ModelSerializer):
    signature_url = serializers.SerializerMethodField()
    seal_image_url = serializers.SerializerMethodField()
    updated_by = serializers.CharField(source="updated_by.display_name", default=None)

    class Meta:
        model = BrandingDraft
        fields = ["config", "signature_url", "seal_image_url", "updated_at", "updated_by"]
        read_only_fields = fields

    def get_signature_url(self, obj) -> str | None:
        return _asset_url(obj.signature, self.context["user"])

    def get_seal_image_url(self, obj) -> str | None:
        return _asset_url(obj.seal_image, self.context["user"])


class DraftUpdateSerializer(serializers.Serializer):
    config = serializers.DictField()


class PublishSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=80, allow_blank=True, default="")
    reason = serializers.CharField(max_length=500, allow_blank=True, default="")
