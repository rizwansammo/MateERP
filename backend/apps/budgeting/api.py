from django.urls import include, path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from apps.accounting.api.serializers import DecimalText
from apps.sales.api.base import DomainViewSet, search, validated

from . import services
from .models import AnalyticalClassification, Budget, BudgetLine, BudgetRevision, CostCenter


class CostCenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CostCenter
        fields = [
            "id",
            "code",
            "name",
            "description",
            "owner_reference",
            "department",
            "categories",
            "is_active",
        ]
        extra_kwargs = {"code": {"validators": []}}


class ClassificationInput(serializers.Serializer):
    line_id = serializers.IntegerField(min_value=1)
    cost_center_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    project_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    reason = serializers.CharField(max_length=1000)


class ClassificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalyticalClassification
        fields = [
            "id",
            "line_id",
            "version",
            "cost_center_id",
            "project_id",
            "reason",
            "created_at",
            "created_by_id",
        ]


class BudgetInput(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    fiscal_year_id = serializers.IntegerField(min_value=1)
    owner_reference = serializers.CharField(max_length=150, required=False, allow_blank=True)


class BudgetSerializer(serializers.ModelSerializer):
    fiscal_start = serializers.DateField(source="fiscal_year.start")
    fiscal_end = serializers.DateField(source="fiscal_year.end")

    class Meta:
        model = Budget
        fields = [
            "id",
            "name",
            "fiscal_year_id",
            "fiscal_start",
            "fiscal_end",
            "owner_reference",
            "is_archived",
            "active_revision_id",
            "original_revision_id",
            "created_at",
        ]


class BudgetLineInput(serializers.Serializer):
    month = serializers.DateField()
    account_id = serializers.IntegerField(min_value=1)
    category = serializers.ChoiceField(choices=sorted(services.CATEGORIES))
    cost_center_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    project_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    amount = DecimalText()
    annual = serializers.BooleanField(required=False)


class BudgetRevisionInput(serializers.Serializer):
    notes = serializers.CharField(max_length=1000)
    lines = BudgetLineInput(many=True, allow_empty=False, max_length=100)


class BudgetLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code")

    class Meta:
        model = BudgetLine
        fields = [
            "id",
            "month",
            "account_id",
            "account_code",
            "category",
            "cost_center_id",
            "project_id",
            "amount",
        ]


class BudgetRevisionSerializer(serializers.ModelSerializer):
    lines = BudgetLineSerializer(many=True, read_only=True)

    class Meta:
        model = BudgetRevision
        fields = [
            "id",
            "budget_id",
            "version",
            "notes",
            "status",
            "approval_id",
            "created_at",
            "lines",
        ]


class BudgetArchiveInput(serializers.Serializer):
    is_archived = serializers.BooleanField()


class SpendingLineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    journal_id = serializers.UUIDField()
    number = serializers.CharField(source="journal.number")
    date = serializers.DateField(source="journal.posting_date")
    account_id = serializers.IntegerField()
    account_code = serializers.CharField(source="account.code")
    description = serializers.CharField()
    base_debit = DecimalText()
    base_credit = DecimalText()
    analytical_cost_center = serializers.CharField(allow_null=True)
    analytical_project = serializers.CharField(allow_null=True)


class BudgetComparisonRow(serializers.Serializer):
    id = serializers.IntegerField()
    month = serializers.DateField()
    account_id = serializers.IntegerField()
    account_code = serializers.CharField()
    account_name = serializers.CharField()
    category = serializers.CharField()
    cost_center_id = serializers.IntegerField(allow_null=True)
    cost_center = serializers.CharField(allow_null=True)
    project_id = serializers.IntegerField(allow_null=True)
    original = DecimalText()
    revised = DecimalText()
    actual = DecimalText()
    remaining = DecimalText()
    variance = DecimalText()
    over_budget = serializers.BooleanField()


@extend_schema(tags=["budgeting"])
class CostCenterViewSet(DomainViewSet):
    queryset = CostCenter.objects.all()
    serializer_class = CostCenterSerializer
    write_permissions = ("budgets.manage",)

    def list(self, request):
        return self.respond_list(
            search(self.queryset, request, "code", "name", "department").order_by("code")
        )

    def create(self, request):
        return Response(
            self.serializer_class(
                services.save_cost_center(request, validated(self.serializer_class, request.data))
            ).data,
            status=201,
        )

    def partial_update(self, request, pk=None):
        return Response(
            self.serializer_class(
                services.save_cost_center(
                    request,
                    validated(self.serializer_class, request.data, partial=True),
                    self.get_object().pk,
                )
            ).data
        )


@extend_schema(tags=["budgeting"])
class ClassificationViewSet(DomainViewSet):
    queryset = AnalyticalClassification.objects.all()
    serializer_class = ClassificationSerializer
    write_permissions = ("budgets.manage",)

    def list(self, request):
        qs = self.queryset
        if request.query_params.get("line_id"):
            qs = qs.filter(line_id=request.query_params["line_id"])
        return self.respond_list(qs.order_by("-created_at", "-pk"))

    @extend_schema(request=ClassificationInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                services.classify(request, validated(ClassificationInput, request.data))
            ).data,
            status=201,
        )


@extend_schema(tags=["budgeting"])
class BudgetViewSet(DomainViewSet):
    queryset = Budget.objects.select_related("fiscal_year")
    serializer_class = BudgetSerializer
    write_permissions = ("budgets.manage",)

    def list(self, request):
        qs = search(self.queryset, request, "name", "owner_reference")
        if request.query_params.get("status") in ("active", "archived"):
            qs = qs.filter(is_archived=request.query_params["status"] == "archived")
        return self.respond_list(qs.order_by("-pk"))

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @extend_schema(request=BudgetInput)
    def create(self, request):
        return Response(
            self.serializer_class(
                services.create_budget(request, validated(BudgetInput, request.data))
            ).data,
            status=201,
        )

    @extend_schema(request=BudgetArchiveInput)
    def partial_update(self, request, pk=None):
        data = validated(BudgetArchiveInput, request.data)
        return Response(
            self.serializer_class(
                services.archive(request, self.get_object().pk, data["is_archived"])
            ).data
        )

    @extend_schema(request=BudgetRevisionInput, responses=BudgetRevisionSerializer)
    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        obj = services.create_revision(
            request, self.get_object().pk, validated(BudgetRevisionInput, request.data)
        )
        return Response(BudgetRevisionSerializer(obj).data, status=201)


@extend_schema(tags=["budgeting"])
class RevisionViewSet(DomainViewSet):
    queryset = BudgetRevision.objects.prefetch_related("lines__account")
    serializer_class = BudgetRevisionSerializer
    write_permissions = ("budgets.manage",)

    def list(self, request):
        qs = self.queryset
        if request.query_params.get("budget_id"):
            qs = qs.filter(budget_id=request.query_params["budget_id"])
        return self.respond_list(qs.order_by("-version", "-pk"))

    def retrieve(self, request, pk=None):
        return Response(self.serializer_class(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return Response(
            self.serializer_class(services.submit_revision(request, self.get_object().pk)).data
        )

    @extend_schema(responses=BudgetComparisonRow(many=True))
    @action(detail=True, methods=["get"])
    def comparison(self, request, pk=None):
        obj = self.get_object()
        if obj.status != "approved":
            raise serializers.ValidationError(
                "Comparisons require an approved revision. "
                "Draft plans are not approved spending authority."
            )
        return Response(services.comparison(obj))

    @extend_schema(responses=SpendingLineSerializer(many=True))
    @action(detail=True, methods=["get"])
    def actuals(self, request, pk=None):
        obj = self.get_object()
        query = validated(ActualsInput, request.query_params)
        line = services._get(BudgetLine, query["line_id"])
        if line.revision_id != obj.pk:
            raise serializers.ValidationError("The budget line belongs to another revision.")
        return self.respond_list(
            services.line_actuals(line)
            .select_related("journal", "account")
            .order_by("-journal__posting_date", "-pk"),
            SpendingLineSerializer,
        )


class ActualsInput(serializers.Serializer):
    line_id = serializers.IntegerField(min_value=1)


@extend_schema(tags=["budgeting"])
class SpendingViewSet(DomainViewSet):
    queryset = services.JournalLine.objects.none()
    serializer_class = SpendingLineSerializer

    def list(self, request):
        qs = services.classified_lines().select_related("journal", "account")
        qs = search(qs, request, "journal__number", "account__code", "description")
        if request.query_params.get("journal_id"):
            data = validated(JournalFilter, request.query_params)
            qs = qs.filter(journal_id=data["journal_id"])
        return self.respond_list(qs.order_by("-journal__posting_date", "-pk"))


class JournalFilter(serializers.Serializer):
    journal_id = serializers.UUIDField()


router = SimpleRouter()
router.register("cost-centers", CostCenterViewSet)
router.register("classifications", ClassificationViewSet)
router.register("budgets", BudgetViewSet)
router.register("revisions", RevisionViewSet)
router.register("spending", SpendingViewSet, basename="budget-spending")
urlpatterns = [path("budgeting/", include(router.urls))]
