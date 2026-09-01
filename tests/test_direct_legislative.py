from __future__ import annotations

import pandas as pd
import pytest

from census_pa_poc.direct_legislative import (
    aggregate_population,
    build_parent_crosswalk,
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
            "atomic_support_value": [8, 2, 0, 0, 0],
            "atomic_area_square_meters": [1.0, 9.0, 5.0, 1.0, 3.0],
        }
    )


def test_parent_crosswalk_separates_support_and_fallback_weights() -> None:
    result = build_parent_crosswalk(atomic_fixture())
    weights = result.set_index(["source_geography_id", "target_district_id"])

    assert weights.loc[("a", "1"), "weight"] == pytest.approx(0.8)
    assert weights.loc[("a", "2"), "weight"] == pytest.approx(0.2)
    assert weights.loc[("b", "1"), "weight"] == pytest.approx(1.0)
    assert weights.loc[("c", "1"), "weight"] == pytest.approx(0.25)
    assert weights.loc[("c", "2"), "weight"] == pytest.approx(0.75)
    assert weights.loc[("a", "1"), "weight_method"] == "published_fragment_p001"
    assert weights.loc[("b", "1"), "weight_method"] == "single_target_identity"
    assert (
        weights.loc[("c", "1"), "weight_method"] == "zero_support_atomic_area_fallback"
    )
    assert not any("precinct" in column for column in result)


def test_aggregate_population_uses_chamber_neutral_target_columns() -> None:
    crosswalk = build_parent_crosswalk(atomic_fixture())
    population = pd.DataFrame(
        {
            "source_block_geoid": ["a", "b", "c"],
            "P0010001": [10, 0, 0],
        }
    )
    result = aggregate_population(population, crosswalk)

    assert result[["target_district_id", "population"]].to_dict("records") == [
        {"target_district_id": "1", "population": 8.0},
        {"target_district_id": "2", "population": 2.0},
    ]
    assert result["target_chamber"].eq("house").all()
