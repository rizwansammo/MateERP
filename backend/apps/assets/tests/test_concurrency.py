from datetime import date

import pytest

from apps.accounting.tests.test_concurrency import race
from apps.assets import services
from apps.assets.models import Asset, DepreciationCharge

from .test_assets import asset, registration

pytestmark = pytest.mark.django_db(transaction=True)


def test_concurrent_claims_cannot_capitalize_one_acquisition_twice(books, equipment):
    results = race(
        books.request.user.pk,
        *[
            lambda request, index=index: (
                services.request_action(
                    request,
                    "capitalize",
                    registration(
                        books, equipment, tag=f"RACE-{index}", key=f"concurrent-acquisition-{index}"
                    ),
                ).result_id
            )
            for index in range(2)
        ],
    )
    assert sum(ok for ok, _ in results) == 1
    assert Asset.objects.count() == 1
    assert services.available_acquisition(equipment) == 0
    assert services.reconciliation()["cost_difference"] == 0


def test_concurrent_depreciation_cannot_post_one_service_month_twice(books, equipment):
    registered = asset(books, equipment)
    data = {
        "asset_id": str(registered.pk),
        "month": date(2026, 1, 1),
        "recognition_date": date(2026, 1, 31),
        "reason": "Same independently requested service month",
    }
    results = race(
        books.request.user.pk,
        *[
            lambda request, index=index: (
                services.request_action(
                    request, "depreciation", {**data, "key": f"concurrent-depreciation-{index}"}
                ).result_id
            )
            for index in range(2)
        ],
    )
    assert sum(ok for ok, _ in results) == 1
    assert DepreciationCharge.objects.count() == 1
    assert services.reconciliation()["depreciation_difference"] == 0
