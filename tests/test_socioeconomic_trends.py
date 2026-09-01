from __future__ import annotations

import pandas as pd
import pytest

from census_pa_poc.socioeconomic_trends import (
    _derive_poverty_rates,
    add_shares,
    aggregate_additive_cells,
    allocate_categories,
    canonical_tables_for_year,
    parse_expressions,
)


def test_parse_expressions_preserves_only_declared_cells() -> None:
    assert parse_expressions("first=T_001E+T_002E;second=T_003E") == {
        "first": ("T_001E", "T_002E"),
        "second": ("T_003E",),
    }


def test_continuous_sources_keep_b23001_at_tract_grain() -> None:
    assert canonical_tables_for_year(2009) == ["B15002", "B23001", "C17002"]
    assert canonical_tables_for_year(2024) == ["B15002", "B23001", "C17002"]


def test_aggregate_additive_cells_uses_rss_for_moes() -> None:
    source = pd.DataFrame(
        {
            "source_block_group_geoid": ["a"],
            "T_001E": [30],
            "T_001M": [3],
            "T_002E": [40],
            "T_002M": [4],
        }
    )

    result = aggregate_additive_cells(source, {"combined": ("T_001E", "T_002E")})

    assert result["combined_estimate"].tolist() == [70]
    assert result["combined_moe"].tolist() == [5]


def test_allocate_categories_keeps_estimate_and_moe_paths_separate() -> None:
    source = pd.DataFrame(
        {
            "source_block_group_geoid": ["a", "b"],
            "category_estimate": [100, 50],
            "category_moe": [10, 6],
        }
    )
    crosswalk = pd.DataFrame(
        {
            "source_geography_id": ["a", "a", "b"],
            "target_district_id": pd.Series([1, 2, 2], dtype="Int64"),
            "weight": [0.25, 0.75, 1.0],
            "assignment_status": ["assigned", "assigned", "assigned"],
        }
    )

    result = allocate_categories(source, crosswalk, ["category"])
    district_two = result[result["geography_id"].eq(2)].iloc[0]

    assert district_two["estimate"] == 125
    assert district_two["margin_of_error"] == pytest.approx(
        ((0.75 * 10) ** 2 + 6**2) ** 0.5
    )


def test_add_shares_derives_ratio_after_target_aggregation() -> None:
    target = pd.DataFrame(
        {
            "geography_id": [1, 1],
            "category": ["part", "parent"],
            "estimate": [25.0, 100.0],
            "margin_of_error": [5.0, 10.0],
        }
    )

    result = add_shares(target, "parent")

    assert result.loc[result["category"].eq("part"), "share"].iloc[0] == 0.25
    assert result["denominator_estimate"].tolist() == [100.0, 100.0]


def test_poverty_thresholds_sum_published_bands_after_allocation() -> None:
    frame = pd.DataFrame(
        {
            "estimate_year": [2024] * 8,
            "metric_family": ["poverty_ratio"] * 8,
            "geography_type": ["house"] * 8,
            "geography_id": [1] * 8,
            "category": [
                "under_0_50",
                "ratio_0_50_0_99",
                "ratio_1_00_1_24",
                "ratio_1_25_1_49",
                "ratio_1_50_1_84",
                "ratio_1_85_1_99",
                "ratio_2_00_plus",
                "poverty_status_determined",
            ],
            "estimate": [5, 10, 5, 5, 10, 5, 60, 100],
        }
    )

    result = _derive_poverty_rates(frame).set_index("rate_id")

    assert result.loc["below_poverty_line", "rate"] == 0.15
    assert result.loc["below_200_percent_poverty", "rate"] == 0.40
    assert result["rate_moe"].isna().all()
