from __future__ import annotations

import pandas as pd
import pytest

from census_pa_poc.direct_legislative_acs import (
    aggregate_acs,
    normalize_support_with_fallback,
    regime_for_year,
    require_manifest_hashes,
)


def test_support_regimes_follow_accepted_vintage_policy() -> None:
    assert regime_for_year(2009) == "simple_2009"
    assert regime_for_year(2010) == "simple_2010"
    assert regime_for_year(2011) == "population_2010_bg"
    assert regime_for_year(2019) == "population_2010_bg"
    assert regime_for_year(2020) == "population_2020_bg"
    assert regime_for_year(2024) == "population_2020_bg"


def test_zero_support_uses_explicit_simple_area_fallback() -> None:
    grouped = pd.DataFrame(
        {
            "source_geography_id": ["a", "b"],
            "target_district_id": [1, 2],
            "raw_support_value": [10.0, 0.0],
        }
    )
    simple = pd.DataFrame(
        {
            "source_geography_id": ["a", "b", "b"],
            "target_district_id": [1, 2, 3],
            "raw_support_value": [1.0, 3.0, 1.0],
            "weight": [1.0, 0.75, 0.25],
        }
    )

    crosswalk, fallback_count = normalize_support_with_fallback(grouped, simple)

    observed = crosswalk.set_index(["source_geography_id", "target_district_id"])[
        "weight"
    ].to_dict()
    assert observed == {("a", 1): 1.0, ("b", 2): 0.75, ("b", 3): 0.25}
    assert fallback_count == 1
    assert set(
        crosswalk.loc[crosswalk["source_geography_id"].eq("b"), "fallback_basis"]
    ) == {"zero_2010_population_simple_area"}


def test_aggregate_keeps_estimate_and_moe_paths_separate() -> None:
    population = pd.DataFrame(
        {
            "source_block_group_geoid": ["a", "b"],
            "B01003_001E": [100, 50],
            "B01003_001M": [10, 6],
        }
    )
    crosswalk = pd.DataFrame(
        {
            "source_geography_id": ["a", "b"],
            "target_district_id": pd.Series([1, 1], dtype="Int64"),
            "weight": [1.0, 1.0],
            "assignment_status": ["assigned", "assigned"],
        }
    )
    partition = {
        "population_product_id": "acs5_2015",
        "target_chamber": "house",
        "target_plan_id": "pa_house_2012_revised_final",
        "target_plan_reference_vintage": "2012",
        "support_regime": "population_2010_bg",
        "uncertainty": "test",
    }

    result = aggregate_acs(population, crosswalk, partition)

    assert result["estimate"].tolist() == [150]
    assert result["margin_of_error"].iloc[0] == pytest.approx((10**2 + 6**2) ** 0.5)


def test_manifest_rejects_changed_source_bytes() -> None:
    manifest = {
        "verified_source_files": [
            {
                "relative_path": "source.zip",
                "sha256": "expected",
                "observed_sha256": "changed",
            }
        ]
    }

    with pytest.raises(RuntimeError, match="source.zip"):
        require_manifest_hashes(manifest)
