from __future__ import annotations

import pandas as pd

from census_pa_poc.population_availability import (
    availability_is_monotonic,
    build_pairings,
    classify_availability,
    release_bounds,
)


def test_release_bounds_preserve_exact_and_year_only_precision() -> None:
    assert release_bounds("2001-03-09") == (
        "exact_day",
        "2001-03-09",
        "2001-03-09",
    )
    assert release_bounds("1991") == ("year_only", "1991-01-01", "1991-12-31")


def test_availability_uses_conservative_release_bounds() -> None:
    earliest = pd.Timestamp("1991-01-01")
    latest = pd.Timestamp("1991-12-31")

    assert (
        classify_availability(earliest, latest, pd.Timestamp("1990-11-06"))
        == "not_available"
    )
    assert (
        classify_availability(earliest, latest, pd.Timestamp("1992-11-03"))
        == "available"
    )
    assert (
        classify_availability(earliest, latest, pd.Timestamp("1991-06-01"))
        == "indeterminate"
    )


def test_pairings_keep_target_plan_and_future_release_rows() -> None:
    elections = pd.DataFrame(
        {
            "election_id": ["e1", "e2"],
            "election_date": ["1990-11-06", "1992-11-03"],
            "cycle_role": ["historical_training", "historical_training"],
            "precinct_snapshot_id": ["fixed", "fixed"],
            "senate_plan_id": ["plan_a", "plan_b"],
        }
    )
    products = pd.DataFrame(
        {
            "product_id": ["p1"],
            "product_family": ["decennial"],
            "reference_start": ["1990-04-01"],
            "reference_end": ["1990-04-01"],
            "release_date_published": ["1991"],
            "release_date_precision": ["year_only"],
            "release_date_earliest": ["1991-01-01"],
            "release_date_latest": ["1991-12-31"],
            "metric": ["total_population"],
            "source_geography_id": ["census_block"],
            "population_universe": ["standard_total_population"],
            "product_processing_status": ["statewide_proven"],
            "allocation_readiness": ["statewide_result_proven"],
            "accepted_method_id": ["method"],
        }
    )

    result = build_pairings(elections, products)

    assert result["availability_by_cutoff"].tolist() == [
        "not_available",
        "available",
    ]
    assert result["senate_plan_id"].tolist() == ["plan_a", "plan_b"]
    assert result["candidate_for_poc016"].tolist() == ["false", "true"]
    assert result["exact_release_days_before_cutoff"].isna().all()


def test_availability_monotonicity_rejects_reversion() -> None:
    assert availability_is_monotonic(["not_available", "not_available", "available"])
    assert not availability_is_monotonic(
        ["not_available", "available", "not_available"]
    )
