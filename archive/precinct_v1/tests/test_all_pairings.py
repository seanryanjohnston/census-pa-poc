from __future__ import annotations

import pandas as pd
import pytest

from census_pa_poc.all_pairings import (
    acs_crosswalk_key,
    aggregate_acs,
    normalize_support_with_fallback,
    validate_acs_crosswalk,
)


def test_acs_crosswalk_regimes_preserve_non_leaking_support_policy() -> None:
    assert acs_crosswalk_key(2009, "plan") == ("simple_2009", "plan")
    assert acs_crosswalk_key(2010, "plan") == ("simple_2010", "plan")
    assert acs_crosswalk_key(2011, "plan") == ("population_2010_bg", "plan")
    assert acs_crosswalk_key(2019, "plan") == ("population_2010_bg", "plan")
    assert acs_crosswalk_key(2020, "plan") == ("population_2020_bg", "plan")
    assert acs_crosswalk_key(2024, "plan") == ("population_2020_bg", "plan")


def test_zero_population_support_uses_typed_area_fallback() -> None:
    informed = pd.DataFrame(
        {
            "source_block_group_geoid": ["a", "a", "b"],
            "target_precinct_geoid": ["p1", "p2", "p2"],
            "senate_district": [1, 1, 2],
            "raw_support_value": [3.0, 1.0, 0.0],
        }
    )
    simple = pd.DataFrame(
        {
            "source_block_group_geoid": ["a", "b", "b"],
            "target_precinct_geoid": ["p1", "p1", "p2"],
            "senate_district": [1, 2, 2],
            "raw_support_value": [10.0, 1.0, 3.0],
            "weight": [1.0, 0.25, 0.75],
            "fallback_basis": ["none", "none", "none"],
        }
    )

    result, fallback_count = normalize_support_with_fallback(informed, simple)

    assert fallback_count == 1
    sums = result.groupby("source_block_group_geoid")["weight"].sum()
    assert sums.to_dict() == pytest.approx({"a": 1.0, "b": 1.0})
    assert set(
        result.loc[result.source_block_group_geoid.eq("b"), "fallback_basis"]
    ) == {"zero_2010_population_simple_area"}


def test_acs_estimates_and_moes_remain_separate() -> None:
    population = pd.DataFrame(
        {
            "source_block_group_geoid": ["a", "b"],
            "B01003_001E": [100, 40],
            "B01003_001M": [10, 6],
        }
    )
    crosswalk = pd.DataFrame(
        {
            "source_block_group_geoid": ["a", "a", "b"],
            "target_precinct_geoid": ["p1", "p2", "p1"],
            "senate_district": [1, 2, 1],
            "weight": [0.25, 0.75, 1.0],
        }
    )

    precinct, senate = aggregate_acs(population, crosswalk)

    p1 = precinct.set_index("target_precinct_geoid").loc["p1"]
    assert p1["estimate"] == pytest.approx(65.0)
    assert p1["margin_of_error"] == pytest.approx((2.5**2 + 6**2) ** 0.5)
    assert senate["estimate"].sum() == pytest.approx(140.0)
    assert senate["margin_of_error"].sum() != pytest.approx(16.0)


def test_acs_crosswalk_validation_rejects_missing_source() -> None:
    population = pd.DataFrame(
        {
            "source_block_group_geoid": ["a", "b"],
            "B01003_001E": [1, 2],
            "B01003_001M": [1, 1],
        }
    )
    crosswalk = pd.DataFrame(
        {
            "source_block_group_geoid": ["a"],
            "weight": [1.0],
        }
    )

    with pytest.raises(ValueError, match="universe mismatch"):
        validate_acs_crosswalk(crosswalk, population)
