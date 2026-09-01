from __future__ import annotations

import pandas as pd
import pytest

from census_pa_poc.election_population_review import (
    build_election_precinct_population,
    build_election_senate_population,
    display_product_label,
    missingness_summary,
    normalize_requested_years,
    select_display_products,
)


def election_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "election_id": ["e1990", "e1992"],
            "election_year": [1990, 1992],
            "election_date": ["1990-11-06", "1992-11-03"],
            "cycle_role": ["historical_training", "historical_training"],
            "precinct_snapshot_id": ["fixed", "fixed"],
            "senate_plan_id": ["plan_1981", "plan_1991"],
        }
    )


def availability_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "election_id": ["e1990", "e1992", "e1992"],
            "election_date": ["1990-11-06", "1992-11-03", "1992-11-03"],
            "product_id": ["dec_1990", "dec_1990", "acs5_2009"],
            "product_family": ["Census", "Census", "ACS"],
            "reference_start": ["1990-04-01", "1990-04-01", "2005-01-01"],
            "reference_end": ["1990-04-01", "1990-04-01", "2009-12-31"],
            "release_date_latest": ["1991-12-31", "1991-12-31", "2010-12-14"],
            "release_date_published": ["1991", "1991", "2010-12-14"],
            "candidate_for_poc016": ["false", "true", "false"],
        }
    )


def test_display_selection_retains_no_product_and_selects_newest_available() -> None:
    result = select_display_products(election_fixture(), availability_fixture())

    assert pd.isna(result.loc[0, "population_product_id"])
    assert result.loc[1, "population_product_id"] == "dec_1990"
    assert result["display_selection_status"].tolist() == [
        "no_product_available_by_cutoff",
        "selected_available_product",
    ]
    assert result.loc[0, "missing_reason"] == (
        "no_cataloged_population_product_available_by_election_day"
    )


def test_precinct_table_materializes_expected_missing_rows() -> None:
    selection = select_display_products(election_fixture(), availability_fixture())
    population = pd.DataFrame(
        {
            "population_product_id": ["dec_1990", "dec_1990"],
            "senate_plan_id": ["plan_1991", "plan_1991"],
            "target_precinct_geoid": ["p1", "p2"],
            "estimate": [10.0, 20.0],
            "margin_of_error": [pd.NA, pd.NA],
        }
    )

    result = build_election_precinct_population(
        selection, population, pd.Series(["p1", "p2"], dtype="string")
    )

    assert len(result) == 4
    assert result.loc[result.election_year.eq(1990), "estimate"].isna().all()
    assert result.loc[result.election_year.eq(1992), "estimate"].sum() == 30
    assert set(result.loc[result.election_year.eq(1990), "data_status"]) == {"missing"}


def test_senate_table_preserves_all_fifty_expected_districts() -> None:
    selection = select_display_products(election_fixture(), availability_fixture())
    population = pd.DataFrame(
        {
            "population_product_id": ["dec_1990"],
            "senate_plan_id": ["plan_1991"],
            "senate_district": pd.Series([1], dtype="Int64"),
            "estimate": [30.0],
            "margin_of_error": [pd.NA],
        }
    )

    result = build_election_senate_population(selection, population)

    assert len(result) == 100
    assert result.loc[result.election_year.eq(1990), "estimate"].isna().all()
    missing_1992 = result.loc[result.election_year.eq(1992), "estimate"].isna()
    assert int(missing_1992.sum()) == 49
    assert set(
        result.loc[result.election_year.eq(1992) & missing_1992, "missing_reason"]
    ) == {"selected_result_row_missing"}


def test_missingness_summary_reports_each_level_separately() -> None:
    precincts = pd.DataFrame(
        {"election_year": [1990, 1990, 1992, 1992], "estimate": [pd.NA, pd.NA, 1, 2]}
    )
    senate = pd.DataFrame({"election_year": [1990, 1992], "estimate": [pd.NA, 3]})

    result = missingness_summary(precincts, senate)

    assert result == [
        {
            "election_year": 1990,
            "present_precinct": 0,
            "missing_precinct": 2,
            "present_senate": 0,
            "missing_senate": 1,
        },
        {
            "election_year": 1992,
            "present_precinct": 2,
            "missing_precinct": 0,
            "present_senate": 1,
            "missing_senate": 0,
        },
    ]


def test_requested_years_default_validate_and_deduplicate() -> None:
    selection = pd.DataFrame({"election_year": [1990, 1992]})

    assert normalize_requested_years(None, selection) == [1990, 1992]
    assert normalize_requested_years([1992, 1992], selection) == [1992]
    with pytest.raises(ValueError, match="not registered"):
        normalize_requested_years([1994], selection)


@pytest.mark.parametrize(
    ("product_id", "expected"),
    [
        ("dec_2020", "2020 Census"),
        ("acs5_2024", "ACS 2020\u20132024"),
        (pd.NA, "No product available"),
    ],
)
def test_display_product_label_is_explicit(product_id: object, expected: str) -> None:
    assert display_product_label({"population_product_id": product_id}) == expected
