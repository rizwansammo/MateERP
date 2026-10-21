from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers as s

from apps.files.api.serializers import StoredFileSerializer

from .. import models as m


def exact_register_json(value):
    """Share counts are strings at the browser boundary, including counts > 2**53."""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == "units" and isinstance(item, dict):
                result[key] = {k: str(v) for k, v in item.items()}
            elif key in {"units", "total"} and isinstance(item, int):
                result[key] = str(item)
            else:
                result[key] = exact_register_json(item)
        return result
    if isinstance(value, list):
        return [exact_register_json(v) for v in value]
    return value


class ClassSerializer(s.ModelSerializer):
    class Meta:
        model = m.ShareClass
        fields = "__all__"


@extend_schema_serializer(component_name="OwnershipLine")
class LineSerializer(s.ModelSerializer):
    units = s.CharField(read_only=True)

    class Meta:
        model = m.OwnershipLine
        fields = ["id", "transferor", "recipient", "units", "price"]


@extend_schema_serializer(component_name="OwnershipEvidence")
class EvidenceSerializer(s.ModelSerializer):
    file = StoredFileSerializer(read_only=True)

    class Meta:
        model = m.OwnershipEvidence
        fields = "__all__"


class ProposalSerializer(s.ModelSerializer):
    snapshot = s.SerializerMethodField()
    lines = LineSerializer(many=True, read_only=True)
    evidence = EvidenceSerializer(many=True, read_only=True)
    consents = s.SerializerMethodField()
    approval_status = s.CharField(source="approval.status", read_only=True, allow_null=True)

    class Meta:
        model = m.OwnershipProposal
        fields = "__all__"

    def get_consents(self, obj) -> list:
        return list(obj.consents.values("party_id", "actor_id", "mode", "reference"))

    def get_snapshot(self, obj) -> dict:
        return exact_register_json(obj.snapshot)


@extend_schema_serializer(component_name="OwnershipLineInput")
class LineInput(s.Serializer):
    transferor_id = s.IntegerField(min_value=1, required=False)
    recipient_id = s.IntegerField(min_value=1)
    units = s.IntegerField(min_value=1, max_value=9223372036854775807, required=False)
    percentage_points = s.DecimalField(
        max_digits=12, decimal_places=6, min_value=0, max_value=100, required=False
    )
    price = s.DecimalField(max_digits=24, decimal_places=6, min_value=0, default="0")


class ProposalInput(s.Serializer):
    client_key = s.CharField(min_length=8, max_length=160)
    kind = s.ChoiceField(choices=["provisional", "transfer", "issuance", "opening"])
    title = s.CharField(max_length=200)
    effective_date = s.DateField()
    share_class_id = s.IntegerField(min_value=1, required=False)
    rationale = s.CharField(max_length=2000)
    legal_reference = s.CharField(max_length=500, allow_blank=True, default="")
    weights = s.DictField(child=s.CharField(), required=False)
    lines = LineInput(many=True, required=False)

    def validate(self, data):
        if data["kind"] == "transfer" and any(
            "transferor_id" not in row for row in data.get("lines", [])
        ):
            raise s.ValidationError({"lines": "Each transfer needs an authorizing transferor."})
        return data
