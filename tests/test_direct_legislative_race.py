import pandas as pd

from census_pa_poc.direct_legislative_race import (
    CATEGORIES,
    build_crosswalk,
    category_weight_method,
)


def test_p2_crosswalk_uses_category_specific_support() -> None:
    rows = []
    for category in CATEGORIES:
        rows.extend(
            [
                {
                    "target_chamber": "house",
                    "target_plan_id": "plan",
                    "target_plan_reference_vintage": "2021",
                    "source_geography_id": "block",
                    "metric_category": category,
                    "target_district_id": "1",
                    "source_atomic_geoid": "blockA",
                    "atomic_category_support": 7 if category == "hispanic" else 0,
                    "atomic_area_square_meters": 25.0,
                },
                {
                    "target_chamber": "house",
                    "target_plan_id": "plan",
                    "target_plan_reference_vintage": "2021",
                    "source_geography_id": "block",
                    "metric_category": category,
                    "target_district_id": "2",
                    "source_atomic_geoid": "blockB",
                    "atomic_category_support": 3 if category == "hispanic" else 0,
                    "atomic_area_square_meters": 75.0,
                },
            ]
        )

    crosswalk = build_crosswalk(pd.DataFrame(rows))
    hispanic = crosswalk[crosswalk["metric_category"].eq("hispanic")]
    zero_category = crosswalk[crosswalk["metric_category"].eq("nh_white")]

    assert hispanic["weight"].tolist() == [0.7, 0.3]
    assert set(hispanic["weight_method"]) == {"published_fragment_p002_category"}
    assert zero_category["weight"].tolist() == [0.25, 0.75]
    assert set(zero_category["weight_method"]) == {
        "zero_category_atomic_area_fallback"
    }


def test_single_target_identity_precedes_zero_support_fallback() -> None:
    row = pd.Series({"parent_target_count": 1, "parent_category_support": 0})
    assert category_weight_method(row) == "single_target_identity"
