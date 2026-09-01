from __future__ import annotations

import pandas as pd
import pytest

from census_pa_poc.direct_legislative_vap import (
    METRIC_ID,
    WEIGHTING_UNIVERSE,
    aggregate_vap,
    build_vap_crosswalk,
)


def atomic_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "target_chamber": ["house"] * 5,
            "target_plan_id": ["plan"] * 5,
            "target_plan_reference_vintage": ["2021"] * 5,
            "source_geography_id": ["a", "a", "b", "c", "c"],
            "source_atomic_geoid": ["a1", "a2", "b1", "c1", "c2"],
            "target_district_id": ["1", "2", "1", "1", "2"],
            "atomic_vap_support": [8, 0, 0, 0, 0],
            "atomic_area_square_meters": [1.0, 9.0, 5.0, 1.0, 3.0],
        }
    )


def test_vap_crosswalk_uses_p3_support_not_total_population_weights() -> None:
    result = build_vap_crosswalk(atomic_fixture())
    weights = result.set_index(["source_geography_id", "target_district_id"])

    assert weights.loc[("a", "1"), "weight"] == pytest.approx(1.0)
    assert weights.loc[("a", "2"), "weight"] == pytest.approx(0.0)
    assert weights.loc[("a", "1"), "weight_method"] == "published_fragment_p003"
    assert weights.loc[("c", "1"), "weight"] == pytest.approx(0.25)
    assert weights.loc[("c", "2"), "weight"] == pytest.approx(0.75)
    assert (
        weights.loc[("c", "1"), "weight_method"]
        == "zero_vap_atomic_area_fallback"
    )
    assert result["source_metric_id"].eq(METRIC_ID).all()
    assert result["weighting_universe"].eq(WEIGHTING_UNIVERSE).all()
    assert not any("precinct" in column for column in result)


def test_aggregate_vap_keeps_metric_and_moe_contract_explicit() -> None:
    crosswalk = build_vap_crosswalk(atomic_fixture())
    vap = pd.DataFrame(
        {"source_block_geoid": ["a", "b", "c"], METRIC_ID: [8, 0, 0]}
    )

    result = aggregate_vap(vap, crosswalk)

    assert result[["target_district_id", "estimate"]].to_dict("records") == [
        {"target_district_id": "1", "estimate": 8.0},
        {"target_district_id": "2", "estimate": 0.0},
    ]
    assert result["source_metric_id"].eq(METRIC_ID).all()
    assert result["population_universe"].eq(
        "total_population_18_years_and_over"
    ).all()
    assert result["moe"].isna().all()
    assert result["moe_treatment"].eq(
        "not_applicable_exact_decennial_count"
    ).all()
