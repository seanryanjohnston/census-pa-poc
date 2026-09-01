from __future__ import annotations

import pandas as pd

from census_pa_poc.source_reconciliation import (
    build_reconciliation,
    source_totals_for_product,
)


def provenance() -> dict[str, object]:
    return {
        "producer": "U.S. Census Bureau",
        "source_product": "fixture",
        "source_unit_geography": "census_block",
        "metric": "population",
        "population_universe": "total_population",
        "reference_start": "2020-04-01",
        "reference_end": "2020-04-01",
        "release_date": "2021-08-12",
        "source_url": "https://example.test/source",
        "published_aggregate_source_url": pd.NA,
        "license_access": "public",
    }


def test_source_totals_include_counties_and_state() -> None:
    blocks = pd.DataFrame(
        {
            "source_block_geoid": [
                "420010001001001",
                "420010001001002",
                "420030001001001",
            ],
            "P0010001": [10, 20, 40],
        }
    )

    result = source_totals_for_product(
        "dec_2020", blocks, "source_block_geoid", "P0010001", provenance()
    )

    assert result[
        [
            "geography_level",
            "geography_id",
            "official_source_unit_sum",
            "source_unit_count",
        ]
    ].to_dict("records") == [
        {
            "geography_level": "state",
            "geography_id": "42",
            "official_source_unit_sum": 70,
            "source_unit_count": 3,
        },
        {
            "geography_level": "county",
            "geography_id": "001",
            "official_source_unit_sum": 30,
            "source_unit_count": 2,
        },
        {
            "geography_level": "county",
            "geography_id": "003",
            "official_source_unit_sum": 40,
            "source_unit_count": 1,
        },
    ]


def test_reconciliation_exposes_all_deltas_and_statuses() -> None:
    allocated = pd.DataFrame(
        {
            "population_product_id": ["acs5_2024", "acs5_2024"],
            "senate_plan_id": ["plan", "plan"],
            "target_precinct_geoid": ["42001000001", "42003000001"],
            "estimate": [30.0, 40.0],
        }
    )
    published = pd.DataFrame(
        {
            "geography_level": ["state", "county", "county"],
            "geography_id": ["42", "001", "003"],
            "geography_name": ["Pennsylvania", "Adams", "Allegheny"],
            "source_record_geoid": ["0400000US42", "0500000US42001", "0500000US42003"],
            "published_estimate": [70, 30, 40],
            "published_margin_of_error": pd.array(
                [pd.NA, pd.NA, pd.NA], dtype="Float64"
            ),
            "margin_of_error_status": [
                "controlled_estimate_no_meaningful_moe",
                "controlled_estimate_no_meaningful_moe",
                "controlled_estimate_no_meaningful_moe",
            ],
        }
    )
    source_units = pd.DataFrame(
        {
            "source_block_group_geoid": ["420010001001", "420030001001"],
            "B01003_001E": [30, 40],
        }
    )
    source_totals = source_totals_for_product(
        "acs5_2024",
        source_units,
        "source_block_group_geoid",
        "B01003_001E",
        provenance(),
        published,
    )

    result = build_reconciliation(allocated, source_totals)

    assert len(result) == 3
    assert result["allocated_minus_source_sum"].eq(0).all()
    assert result["source_sum_minus_published_aggregate"].eq(0).all()
    assert set(result["allocation_comparison_status"]) == {"within_tolerance"}
    assert set(result["source_to_published_comparison_status"]) == {"within_tolerance"}
