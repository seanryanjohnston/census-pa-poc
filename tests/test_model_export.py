from __future__ import annotations

import pandas as pd
import pytest

from census_pa_poc.model_export import (
    _add_derived_socioeconomic_features,
    select_source_product,
)


def test_source_selection_uses_latest_product_released_by_election() -> None:
    metadata = pd.DataFrame(
        {
            "product_id": ["early", "late"],
            "estimate_year": [2009, 2010],
            "period_start": ["2005-01-01", "2006-01-01"],
            "period_end": ["2009-12-31", "2010-12-31"],
            "release_date": pd.to_datetime(["2010-12-14", "2011-12-08"]),
        }
    )

    selected = select_source_product(
        pd.Timestamp("2012-11-06"), ["early", "late"], metadata
    )

    assert selected["product_id"] == "late"
    assert selected["source_timing"] == "latest_cutoff_safe_product"


def test_source_selection_rejects_future_backfill() -> None:
    metadata = pd.DataFrame(
        {
            "product_id": ["earliest", "later"],
            "estimate_year": [2009, 2010],
            "period_start": ["2005-01-01", "2006-01-01"],
            "period_end": ["2009-12-31", "2010-12-31"],
            "release_date": pd.to_datetime(["2010-12-14", "2011-12-08"]),
        }
    )

    with pytest.raises(ValueError, match="No cutoff-safe source product"):
        select_source_product(
            pd.Timestamp("2008-11-04"), ["later", "earliest"], metadata
        )


def test_source_selection_rejects_period_ending_after_election() -> None:
    metadata = pd.DataFrame(
        {
            "product_id": ["future_period"],
            "estimate_year": [2012],
            "period_start": ["2008-01-01"],
            "period_end": ["2012-12-31"],
            "release_date": ["2012-01-01"],
        }
    )

    with pytest.raises(ValueError, match="No cutoff-safe source product"):
        select_source_product(pd.Timestamp("2012-11-06"), ["future_period"], metadata)


def test_derived_rates_use_compatible_allocated_counts() -> None:
    frame = pd.DataFrame(
        {
            "employment_employed_estimate": [60.0],
            "employment_unemployed_estimate": [5.0],
            "employment_armed_forces_estimate": [1.0],
            "employment_population_16_plus_estimate": [100.0],
            "poverty_under_0_50_estimate": [5.0],
            "poverty_under_0_50_moe": [3.0],
            "poverty_ratio_0_50_0_99_estimate": [10.0],
            "poverty_ratio_0_50_0_99_moe": [4.0],
            "poverty_ratio_1_00_1_24_estimate": [5.0],
            "poverty_ratio_1_00_1_24_moe": [1.0],
            "poverty_ratio_1_25_1_49_estimate": [5.0],
            "poverty_ratio_1_25_1_49_moe": [1.0],
            "poverty_ratio_1_50_1_84_estimate": [10.0],
            "poverty_ratio_1_50_1_84_moe": [2.0],
            "poverty_ratio_1_85_1_99_estimate": [5.0],
            "poverty_ratio_1_85_1_99_moe": [1.0],
            "poverty_poverty_status_determined_estimate": [100.0],
        }
    )

    result = _add_derived_socioeconomic_features(frame).iloc[0]

    assert result["employment_to_population_rate"] == 0.6
    assert result["civilian_unemployment_rate"] == 5 / 65
    assert result["labor_force_participation_rate"] == 0.66
    assert result["poverty_below_poverty_line_estimate"] == 15
    assert result["poverty_below_poverty_line_approx_moe"] == 5
    assert result["poverty_below_200_percent_share"] == 0.4
