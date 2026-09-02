"""Build complete district-by-election CSV feature panels for POC039."""

from __future__ import annotations

import argparse
import hashlib
import math
from collections.abc import Iterable, Mapping
from pathlib import Path

import geopandas as gpd
import pandas as pd

from census_pa_poc.decennial_socioeconomic import PRODUCTS as DECENNIAL_SOCIO_PRODUCTS
from census_pa_poc.sources import sha256
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_json,
)

ELECTIONS_PATH = "mappings/model_election_years_v1.csv"
PLANS_PATH = "data/processed/direct_legislative/legislative_plans_1991_2021_v2.parquet"
DECENNIAL_PATH = (
    "data/processed/direct_legislative/poc029/decennial_legislative_results_v1.parquet"
)
ACS_PATH = "data/processed/direct_legislative/poc029/acs_legislative_results_v1.parquet"
SOCIOECONOMIC_PATH = (
    "data/processed/direct_legislative/poc036/"
    "socioeconomic_legislative_partitions_v1.parquet"
)
DECENNIAL_SOCIOECONOMIC_PATH = (
    "data/processed/direct_legislative/poc039_support/"
    "decennial_socioeconomic_legislative_v2.parquet"
)
OUTPUT_ROOT = "data/exports/model_features/v2"
QA_PATH = "artifacts/poc039/model_export_qa_v2.json"
EXPECTED_DISTRICTS = {"house": 203, "senate": 50}
ELECTION_YEARS = tuple(range(1992, 2027, 2))
PARENT_CATEGORIES = {
    "education_attainment": "population_25_plus",
    "employment_status": "population_16_plus",
    "poverty_ratio": "poverty_status_determined",
}
FAMILY_PREFIXES = {
    "education_attainment": "education",
    "employment_status": "employment",
    "poverty_ratio": "poverty",
}
DECENNIAL_RELEASE_DATES = {
    "dec_1990": "1991-12-31",
    "dec_2000": "2001-03-09",
    "dec_2010": "2011-03-09",
    "dec_2020": "2021-08-12",
}


def load_elections(root: Path) -> pd.DataFrame:
    """Load and validate the active model-panel election spine."""
    elections = pd.read_csv(root / ELECTIONS_PATH, dtype="string")
    elections["election_year"] = elections["election_year"].astype(int)
    elections["election_date"] = pd.to_datetime(elections["election_date"])
    if tuple(elections["election_year"]) != ELECTION_YEARS:
        raise ValueError("Election mapping must contain every even year from 1992–2026")
    return elections


def load_product_metadata(root: Path) -> pd.DataFrame:
    """Return comparable release and reference fields for panel products."""
    acs = pd.read_csv(root / "mappings/acs5_products.csv", dtype="string")
    acs = acs[
        ["product_id", "estimate_year", "period_start", "period_end", "release_date"]
    ].copy()
    periods = pd.read_csv(root / "mappings/population_periods.csv", dtype="string")
    decennial = periods[periods["series_id"].isin(DECENNIAL_RELEASE_DATES)].copy()
    decennial = decennial.rename(
        columns={
            "series_id": "product_id",
            "reference_start": "period_start",
            "reference_end": "period_end",
        }
    )
    decennial["estimate_year"] = decennial["product_id"].str[-4:]
    decennial["release_date"] = decennial["product_id"].map(DECENNIAL_RELEASE_DATES)
    socioeconomic = pd.DataFrame(
        [
            {"product_id": product_id, **fields}
            for product_id, fields in DECENNIAL_SOCIO_PRODUCTS.items()
        ]
    )[acs.columns]
    metadata = pd.concat(
        [acs, decennial[acs.columns], socioeconomic], ignore_index=True
    ).drop_duplicates("product_id")
    metadata["estimate_year"] = metadata["estimate_year"].astype(int)
    for column in ("period_start", "period_end", "release_date"):
        metadata[column] = pd.to_datetime(metadata[column])
    return metadata


def select_source_product(
    election_date: pd.Timestamp,
    available_product_ids: Iterable[str],
    metadata: pd.DataFrame,
) -> dict[str, object]:
    """Select the latest product whose period and release precede the election."""
    candidates = metadata[
        metadata["product_id"].isin(set(available_product_ids))
    ].copy()
    if candidates.empty:
        raise ValueError("No source products are available for this plan")
    for column in ("period_start", "period_end", "release_date"):
        candidates[column] = pd.to_datetime(candidates[column])
    eligible = candidates[
        candidates["release_date"].le(election_date)
        & candidates["period_end"].le(election_date)
    ]
    if eligible.empty:
        products = sorted(candidates["product_id"].astype(str).tolist())
        raise ValueError(
            f"No cutoff-safe source product exists by {election_date.date()}: {products}"
        )
    selected = eligible.sort_values(
        ["period_end", "release_date", "estimate_year", "product_id"], kind="stable"
    ).iloc[-1]
    return {**selected.to_dict(), "source_timing": "latest_cutoff_safe_product"}


def build_panel_spine(root: Path, elections: pd.DataFrame) -> pd.DataFrame:
    """Expand actual election plans to every House and Senate district."""
    plans = gpd.read_parquet(root / PLANS_PATH)
    projected = plans.to_crs("EPSG:5070").copy()
    projected["district_total_area_sq_km"] = projected.geometry.area / 1_000_000
    fields = [
        "target_chamber",
        "target_plan_id",
        "target_plan_reference_vintage",
        "target_district_id",
        "district_total_area_sq_km",
    ]
    rows = []
    for election in elections.to_dict("records"):
        for chamber in ("house", "senate"):
            plan_id = str(election[f"{chamber}_plan_id"])
            districts = projected[projected["target_plan_id"].eq(plan_id)][fields]
            for district in districts.to_dict("records"):
                district_id = int(district["target_district_id"])
                scope = str(election[f"{chamber}_regular_contest_scope"])
                regular = chamber == "house" or district_id % 2 == (
                    0 if scope == "even" else 1
                )
                rows.append(
                    {
                        "election_id": f"pa_general_{election['election_year']}",
                        "election_year": int(election["election_year"]),
                        "election_date": election["election_date"],
                        "chamber": chamber,
                        "district_id": district_id,
                        "district_key": f"pa_{chamber}_{district_id:03d}",
                        "target_plan_id": district["target_plan_id"],
                        "target_plan_reference_vintage": district[
                            "target_plan_reference_vintage"
                        ],
                        "regular_contest": regular,
                        "district_total_area_sq_km": district[
                            "district_total_area_sq_km"
                        ],
                        "district_area_source_id": "legislative_plan_geometry",
                        "district_area_crs": "EPSG:5070",
                        "district_area_water_treatment": "includes_water",
                    }
                )
    return pd.DataFrame(rows).sort_values(
        ["chamber", "election_year", "district_id"], kind="stable"
    )


def build_population_features(
    root: Path,
    spine: pd.DataFrame,
    metadata: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    """Select and attach the cutoff-safe total-population series."""
    decennial = pd.read_parquet(root / DECENNIAL_PATH).rename(
        columns={
            "population_product_id": "product_id",
            "target_chamber": "chamber",
            "target_district_id": "district_id",
            "population": "total_population_estimate",
        }
    )
    decennial["total_population_moe"] = pd.NA
    acs = pd.read_parquet(root / ACS_PATH).rename(
        columns={
            "population_product_id": "product_id",
            "target_chamber": "chamber",
            "target_district_id": "district_id",
            "estimate": "total_population_estimate",
            "margin_of_error": "total_population_moe",
        }
    )
    values = pd.concat(
        [
            decennial[
                [
                    "product_id",
                    "chamber",
                    "target_plan_id",
                    "district_id",
                    "total_population_estimate",
                    "total_population_moe",
                ]
            ],
            acs[
                [
                    "product_id",
                    "chamber",
                    "target_plan_id",
                    "district_id",
                    "total_population_estimate",
                    "total_population_moe",
                ]
            ],
        ],
        ignore_index=True,
    )
    selections = []
    frames = []
    for key, election_rows in spine.groupby(
        ["election_year", "election_date", "chamber", "target_plan_id"],
        sort=False,
    ):
        election_year, election_date, chamber, plan_id = key
        candidates = values[
            values["chamber"].eq(chamber) & values["target_plan_id"].eq(plan_id)
        ]
        selected = select_source_product(
            election_date, candidates["product_id"].unique(), metadata
        )
        product_id = str(selected["product_id"])
        chosen = candidates[candidates["product_id"].eq(product_id)].copy()
        chosen["election_year"] = int(election_year)
        chosen = chosen.rename(
            columns={
                "product_id": "population_source_product_id",
                "estimate_year": "population_source_year",
            }
        )
        for source_field, output_field in (
            ("estimate_year", "population_source_year"),
            ("period_start", "population_source_period_start"),
            ("period_end", "population_source_period_end"),
            ("release_date", "population_source_release_date"),
            ("source_timing", "population_source_timing"),
        ):
            chosen[output_field] = selected[source_field]
        chosen["population_moe_status"] = (
            "acs_90_percent_moe"
            if product_id.startswith("acs5_")
            else "not_applicable_decennial_count"
        )
        frames.append(chosen)
        selections.append(
            _selection_record(
                election_year,
                chamber,
                plan_id,
                "total_population",
                selected,
            )
        )
    combined = pd.concat(frames, ignore_index=True)
    fields = [
        "election_year",
        "chamber",
        "target_plan_id",
        "district_id",
        "total_population_estimate",
        "total_population_moe",
        "population_source_product_id",
        "population_source_year",
        "population_source_period_start",
        "population_source_period_end",
        "population_source_release_date",
        "population_source_timing",
        "population_moe_status",
    ]
    return combined[fields], selections


def _selection_record(
    election_year: int,
    chamber: str,
    plan_id: str,
    family: str,
    selected: Mapping[str, object],
) -> dict[str, object]:
    return {
        "election_year": int(election_year),
        "chamber": chamber,
        "target_plan_id": plan_id,
        "metric_family": family,
        "source_product_id": selected["product_id"],
        "source_estimate_year": int(selected["estimate_year"]),
        "source_period_start": selected["period_start"],
        "source_period_end": selected["period_end"],
        "source_release_date": selected["release_date"],
        "source_timing": selected["source_timing"],
    }


def _socioeconomic_wide(frame: pd.DataFrame) -> pd.DataFrame:
    key = ["election_year", "chamber", "target_plan_id", "district_id"]
    output = frame[key].drop_duplicates().copy()
    for family, prefix in FAMILY_PREFIXES.items():
        family_rows = frame[frame["metric_family"].eq(family)]
        parent = PARENT_CATEGORIES[family]
        for category in sorted(family_rows["category"].unique()):
            selected = family_rows[family_rows["category"].eq(category)][
                [*key, "estimate", "margin_of_error", "share"]
            ].copy()
            category_prefix = f"{prefix}_{category}"
            rename = {
                "estimate": f"{category_prefix}_estimate",
                "margin_of_error": f"{category_prefix}_moe",
                "share": f"{category_prefix}_share",
            }
            selected = selected.rename(columns=rename)
            if category == parent:
                selected = selected.drop(columns=[f"{category_prefix}_share"])
            output = output.merge(selected, on=key, how="left", validate="one_to_one")
    return _add_derived_socioeconomic_features(output)


def _add_derived_socioeconomic_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    employed = result["employment_employed_estimate"]
    unemployed = result["employment_unemployed_estimate"]
    armed = result["employment_armed_forces_estimate"]
    population = result["employment_population_16_plus_estimate"]
    result["employment_to_population_rate"] = employed / population
    result["civilian_unemployment_rate"] = unemployed / (employed + unemployed)
    result["labor_force_participation_rate"] = (
        employed + unemployed + armed
    ) / population
    below_poverty = ["under_0_50", "ratio_0_50_0_99"]
    below_200 = [
        *below_poverty,
        "ratio_1_00_1_24",
        "ratio_1_25_1_49",
        "ratio_1_50_1_84",
        "ratio_1_85_1_99",
    ]
    for output, categories in (
        ("poverty_below_poverty_line", below_poverty),
        ("poverty_below_200_percent", below_200),
    ):
        estimates = [f"poverty_{category}_estimate" for category in categories]
        moes = [f"poverty_{category}_moe" for category in categories]
        result[f"{output}_estimate"] = result[estimates].sum(
            axis="columns", min_count=1
        )
        result[f"{output}_approx_moe"] = (
            result[moes].pow(2).sum(axis="columns", min_count=1).pow(0.5)
        )
        result[f"{output}_share"] = (
            result[f"{output}_estimate"]
            / result["poverty_poverty_status_determined_estimate"]
        )
    return result


def build_socioeconomic_features(
    root: Path,
    spine: pd.DataFrame,
    metadata: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, object]], dict[str, str]]:
    """Attach socioeconomic features from cutoff-safe decennial or ACS products."""
    accepted = pd.read_parquet(root / SOCIOECONOMIC_PATH)
    accepted["socioeconomic_moe_status"] = "acs_90_percent_moe"
    decennial = pd.read_parquet(root / DECENNIAL_SOCIOECONOMIC_PATH)
    values = pd.concat([accepted, decennial], ignore_index=True)
    values["geography_id"] = values["geography_id"].astype(int)
    selections = []
    frames = []
    for key, election_rows in spine.groupby(
        ["election_year", "election_date", "chamber", "target_plan_id"],
        sort=False,
    ):
        election_year, election_date, chamber, plan_id = key
        candidates = values[
            values["geography_type"].eq(chamber) & values["target_plan_id"].eq(plan_id)
        ]
        selected = select_source_product(
            election_date, candidates["population_product_id"].unique(), metadata
        )
        chosen = candidates[
            candidates["population_product_id"].eq(selected["product_id"])
        ].copy()
        chosen["election_year"] = int(election_year)
        chosen["chamber"] = chamber
        chosen["district_id"] = chosen["geography_id"]
        frames.append(chosen)
        selections.append(
            _selection_record(
                election_year,
                chamber,
                plan_id,
                "socioeconomic",
                selected,
            )
        )
    long = pd.concat(frames, ignore_index=True)
    wide = _socioeconomic_wide(long)
    selection_frame = pd.DataFrame(selections).rename(
        columns={
            "source_product_id": "socioeconomic_source_product_id",
            "source_estimate_year": "socioeconomic_source_year",
            "source_period_start": "socioeconomic_source_period_start",
            "source_period_end": "socioeconomic_source_period_end",
            "source_release_date": "socioeconomic_source_release_date",
            "source_timing": "socioeconomic_source_timing",
        }
    )
    selection_frame = selection_frame.drop(columns=["metric_family"])
    selection_frame["socioeconomic_moe_status"] = (
        selection_frame["socioeconomic_source_product_id"]
        .str.startswith("acs5_")
        .map(
            {
                True: "acs_90_percent_moe",
                False: "not_published_decennial_long_form_sample_estimate",
            }
        )
    )
    wide = wide.merge(
        selection_frame,
        on=["election_year", "chamber", "target_plan_id"],
        how="left",
        validate="many_to_one",
    )
    support_hashes = {
        DECENNIAL_SOCIOECONOMIC_PATH: sha256(root / DECENNIAL_SOCIOECONOMIC_PATH)
    }
    return wide, selections, support_hashes


def add_population_derivatives(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    keys = ["election_year", "chamber"]
    result["statewide_population_estimate"] = result.groupby(keys)[
        "total_population_estimate"
    ].transform("sum")
    result["population_statewide_share"] = (
        result["total_population_estimate"] / result["statewide_population_estimate"]
    )
    result["chamber_mean_district_population"] = result[
        "statewide_population_estimate"
    ] / result["chamber"].map(EXPECTED_DISTRICTS)
    result["population_deviation_from_chamber_mean_pct"] = 100 * (
        result["total_population_estimate"] / result["chamber_mean_district_population"]
        - 1
    )
    result["population_per_total_sq_km"] = (
        result["total_population_estimate"] / result["district_total_area_sq_km"]
    )
    result["log_population_per_total_sq_km"] = result["population_per_total_sq_km"].map(
        math.log
    )
    return result


def _write_versioned_csv(frame: pd.DataFrame, path: Path) -> str:
    content = frame.to_csv(
        index=False,
        lineterminator="\n",
        float_format="%.10g",
        na_rep="",
        date_format="%Y-%m-%d",
    ).encode("utf-8")
    if path.exists():
        if path.read_bytes() != content:
            raise RuntimeError(f"Refusing to overwrite changed versioned CSV: {path}")
        return "reused_identical"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return "created"


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_data_dictionary(columns: Iterable[str]) -> pd.DataFrame:
    """Create a compact machine-readable definition for every export column."""
    rows = []
    for column in columns:
        family = "identifier_or_provenance"
        unit = "text_or_flag"
        transformation = "selected or copied from canonical mapping"
        uncertainty = "not_applicable"
        if column.endswith(("_estimate", "_moe", "_approx_moe")):
            family = column.split("_", 1)[0]
            unit = "allocated_count"
            transformation = (
                "direct aggregate or sum of mutually exclusive cells after allocation"
            )
            uncertainty = "90% ACS MOE; approx_moe uses RSS and omits covariance"
        if column.endswith(("_share", "_rate")):
            family = column.split("_", 1)[0]
            unit = "proportion_0_to_1"
            transformation = "derived after district-level additive allocation"
            uncertainty = "no ratio MOE reported"
        if column.endswith("_pct"):
            family = "population"
            unit = "percentage_points"
            transformation = "derived from district and chamber totals"
        if column == "district_total_area_sq_km":
            family = "area"
            unit = "square_kilometers"
            transformation = (
                "EPSG:5070 area of the complete plan polygon, including water"
            )
        if column in {
            "district_area_source_id",
            "district_area_crs",
            "district_area_water_treatment",
        }:
            family = "area"
            unit = "provenance"
            transformation = "documents the legislative-plan GIS area calculation"
        if column in {"population_per_total_sq_km", "log_population_per_total_sq_km"}:
            family = "density"
            unit = (
                "people_per_total_square_kilometer"
                if not column.startswith("log_")
                else "natural_log"
            )
            transformation = (
                "population divided by total polygon area; natural log where named"
            )
        if column == "total_population_moe":
            family = "population"
            unit = "count"
            transformation = (
                "ACS 90% MOE when applicable; blank for decennial complete counts"
            )
            uncertainty = "interpret with population_moe_status"
        if column == "population_moe_status":
            family = "population"
            unit = "enum"
            transformation = "declares whether total_population_moe is an ACS MOE"
            uncertainty = "decennial count rows have no sampling MOE"
        if column == "socioeconomic_moe_status":
            family = "socioeconomic"
            unit = "enum"
            transformation = (
                "declares whether socioeconomic MOEs are published ACS MOEs"
            )
            uncertainty = "decennial long-form sample estimates have blank MOEs"
        if column == "regular_contest":
            family = "election"
            unit = "boolean"
            transformation = "true for every House row; Senate true only for the regular odd/even class"
        rows.append(
            {
                "column_name": column,
                "metric_family": family,
                "unit": unit,
                "transformation": transformation,
                "uncertainty": uncertainty,
            }
        )
    return pd.DataFrame(rows)


def panel_checks(frame: pd.DataFrame) -> list[dict[str, object]]:
    checks = []
    for chamber, expected_districts in EXPECTED_DISTRICTS.items():
        selected = frame[frame["chamber"].eq(chamber)]
        expected_rows = expected_districts * len(ELECTION_YEARS)
        checks.append(
            _check(
                f"{chamber}:row_count", len(selected) == expected_rows, len(selected)
            )
        )
        coverage = selected.groupby("election_year")["district_id"].nunique()
        checks.append(
            _check(
                f"{chamber}:district_coverage",
                bool(coverage.eq(expected_districts).all()),
                coverage.to_dict(),
            )
        )
    checks.extend(
        [
            _check(
                "unique_chamber_election_district_key",
                not frame.duplicated(["chamber", "election_year", "district_id"]).any(),
                int(
                    frame.duplicated(["chamber", "election_year", "district_id"]).sum()
                ),
            ),
            _check(
                "no_missing_required_values",
                _no_missing_required_values(frame),
                _missing_value_diagnostics(frame),
            ),
            _check(
                "positive_population_and_area",
                bool(
                    frame["total_population_estimate"].gt(0).all()
                    and frame["district_total_area_sq_km"].gt(0).all()
                ),
                {
                    "nonpositive_population": int(
                        frame["total_population_estimate"].le(0).sum()
                    ),
                    "nonpositive_area": int(
                        frame["district_total_area_sq_km"].le(0).sum()
                    ),
                },
            ),
            _check(
                "house_and_senate_statewide_population_agree",
                _statewide_chamber_totals_agree(frame),
                "zero chamber delta in every election year",
            ),
            _check(
                "house_and_senate_statewide_socioeconomic_counts_agree",
                _statewide_socioeconomic_totals_agree(frame),
                "maximum absolute count delta <= 1e-5 in every election year",
            ),
            _check(
                "population_moe_status_matches_product",
                _population_moe_status_matches(frame),
                frame.groupby(["population_source_product_id", "population_moe_status"])
                .size()
                .rename("row_count")
                .reset_index()
                .to_dict("records"),
            ),
            _check(
                "socioeconomic_moe_status_matches_product",
                _socioeconomic_moe_status_matches(frame),
                frame.groupby(
                    ["socioeconomic_source_product_id", "socioeconomic_moe_status"]
                )
                .size()
                .rename("row_count")
                .reset_index()
                .to_dict("records"),
            ),
            _check(
                "all_source_periods_end_by_election",
                _all_source_dates_precede_election(frame, "period_end"),
                _source_date_diagnostics(frame, "period_end"),
            ),
            _check(
                "all_source_products_released_by_election",
                _all_source_dates_precede_election(frame, "release_date"),
                _source_date_diagnostics(frame, "release_date"),
            ),
            _check(
                "plan_vintage_not_after_election",
                bool(
                    pd.to_numeric(frame["target_plan_reference_vintage"])
                    .le(frame["election_year"])
                    .all()
                ),
                frame.groupby(["election_year", "target_plan_reference_vintage"])
                .size()
                .rename("row_count")
                .reset_index()
                .to_dict("records"),
            ),
            _check(
                "area_provenance_is_explicit_and_consistent",
                bool(
                    frame["district_area_source_id"]
                    .eq("legislative_plan_geometry")
                    .all()
                    and frame["district_area_crs"].eq("EPSG:5070").all()
                    and frame["district_area_water_treatment"]
                    .eq("includes_water")
                    .all()
                ),
                "legislative-plan polygons; EPSG:5070; includes water",
            ),
            _check(
                "no_surrounding_whitespace_in_text",
                _no_surrounding_whitespace(frame),
                "all nonmissing text values equal their stripped form",
            ),
            _check(
                "shares_and_rates_in_range",
                bool(
                    frame[
                        [
                            column
                            for column in frame
                            if column.endswith(("_share", "_rate"))
                        ]
                    ]
                    .apply(lambda values: values.between(0, 1, inclusive="both"))
                    .all()
                    .all()
                ),
                "all bounded [0,1]",
            ),
            _check(
                "education_categories_conserve",
                _category_shares_conserve(
                    frame,
                    "education",
                    [
                        "below_high_school",
                        "high_school",
                        "some_college_associate",
                        "bachelors_plus",
                    ],
                ),
                "four education shares sum to one",
            ),
            _check(
                "employment_categories_conserve",
                _category_shares_conserve(
                    frame,
                    "employment",
                    ["employed", "unemployed", "armed_forces", "not_in_labor_force"],
                ),
                "four employment shares sum to one",
            ),
            _check(
                "poverty_categories_conserve",
                _category_shares_conserve(
                    frame,
                    "poverty",
                    [
                        "under_0_50",
                        "ratio_0_50_0_99",
                        "ratio_1_00_1_24",
                        "ratio_1_25_1_49",
                        "ratio_1_50_1_84",
                        "ratio_1_85_1_99",
                        "ratio_2_00_plus",
                    ],
                ),
                "seven poverty shares sum to one",
            ),
        ]
    )
    return checks


def _statewide_chamber_totals_agree(frame: pd.DataFrame) -> bool:
    totals = frame.pivot_table(
        index="election_year",
        columns="chamber",
        values="statewide_population_estimate",
        aggfunc="first",
    )
    return bool(totals["house"].sub(totals["senate"]).abs().le(1e-6).all())


def _statewide_socioeconomic_totals_agree(frame: pd.DataFrame) -> bool:
    columns = [
        column
        for column in frame
        if column.startswith(("education_", "employment_", "poverty_"))
        and column.endswith("_estimate")
    ]
    totals = frame.groupby(["election_year", "chamber"])[columns].sum()
    house = totals.xs("house", level="chamber")
    senate = totals.xs("senate", level="chamber")
    return bool(house.sub(senate).abs().le(1e-5).all().all())


def socioeconomic_transition_diagnostics(
    frame: pd.DataFrame,
) -> list[dict[str, object]]:
    """Summarize statewide rates around each historical source transition."""
    rows = []
    house = frame[frame["chamber"].eq("house")]
    for year, selected in house.groupby("election_year", sort=True):
        employed = selected["employment_employed_estimate"].sum()
        unemployed = selected["employment_unemployed_estimate"].sum()
        rows.append(
            {
                "election_year": int(year),
                "source_product_id": selected["socioeconomic_source_product_id"].iloc[
                    0
                ],
                "bachelors_plus_share": float(
                    selected["education_bachelors_plus_estimate"].sum()
                    / selected["education_population_25_plus_estimate"].sum()
                ),
                "employment_to_population_rate": float(
                    employed / selected["employment_population_16_plus_estimate"].sum()
                ),
                "civilian_unemployment_rate": float(
                    unemployed / (employed + unemployed)
                ),
                "below_poverty_line_share": float(
                    selected["poverty_below_poverty_line_estimate"].sum()
                    / selected["poverty_poverty_status_determined_estimate"].sum()
                ),
            }
        )
    transitions = pd.DataFrame(rows)
    measure_columns = [
        "bachelors_plus_share",
        "employment_to_population_rate",
        "civilian_unemployment_rate",
        "below_poverty_line_share",
    ]
    deltas = transitions[measure_columns].diff()
    for column in measure_columns:
        transitions[f"change_from_prior_election_{column}"] = deltas[column]
    selected_years = {1992, 2000, 2002, 2010, 2012, 2026}
    records = transitions[transitions["election_year"].isin(selected_years)].to_dict(
        "records"
    )
    return [
        {key: None if pd.isna(value) else value for key, value in record.items()}
        for record in records
    ]


def _moe_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame if column.endswith(("_moe", "_approx_moe"))]


def _no_missing_required_values(frame: pd.DataFrame) -> bool:
    required = frame.drop(columns=_moe_columns(frame))
    return bool(not required.isna().any().any())


def _missing_value_diagnostics(frame: pd.DataFrame) -> list[dict[str, object]]:
    counts = frame.isna().sum()
    return [
        {"column": column, "missing_count": int(count)}
        for column, count in counts.items()
        if count
    ]


def _population_moe_status_matches(frame: pd.DataFrame) -> bool:
    is_acs = frame["population_source_product_id"].str.startswith("acs5_")
    status_matches = frame["population_moe_status"].eq(
        is_acs.map(
            {
                True: "acs_90_percent_moe",
                False: "not_applicable_decennial_count",
            }
        )
    )
    missing_matches = frame["total_population_moe"].isna().eq(~is_acs)
    return bool(status_matches.all() and missing_matches.all())


def _socioeconomic_moe_status_matches(frame: pd.DataFrame) -> bool:
    is_acs = frame["socioeconomic_source_product_id"].str.startswith("acs5_")
    status_matches = frame["socioeconomic_moe_status"].eq(
        is_acs.map(
            {
                True: "acs_90_percent_moe",
                False: "not_published_decennial_long_form_sample_estimate",
            }
        )
    )
    moe_columns = [
        column for column in _moe_columns(frame) if column != "total_population_moe"
    ]
    missing_by_row = frame[moe_columns].isna().all(axis="columns")
    complete_by_row = frame[moe_columns].notna().all(axis="columns")
    uncertainty_matches = (is_acs & complete_by_row) | (~is_acs & missing_by_row)
    return bool(status_matches.all() and uncertainty_matches.all())


def _all_source_dates_precede_election(frame: pd.DataFrame, field: str) -> bool:
    election = pd.to_datetime(frame["election_date"])
    comparisons = []
    for prefix in ("population", "socioeconomic"):
        comparisons.append(
            pd.to_datetime(frame[f"{prefix}_source_{field}"]).le(election)
        )
    return bool(pd.concat(comparisons, axis="columns").all().all())


def _source_date_diagnostics(
    frame: pd.DataFrame, field: str
) -> list[dict[str, object]]:
    records = []
    election = pd.to_datetime(frame["election_date"])
    for prefix in ("population", "socioeconomic"):
        source = pd.to_datetime(frame[f"{prefix}_source_{field}"])
        records.append(
            {
                "source_family": prefix,
                "latest_days_after_election": int((source - election).dt.days.max()),
                "violating_rows": int(source.gt(election).sum()),
            }
        )
    return records


def _no_surrounding_whitespace(frame: pd.DataFrame) -> bool:
    text_columns = frame.select_dtypes(include=["object", "string"]).columns
    for column in text_columns:
        selected = frame[column].dropna().astype(str)
        if not selected.eq(selected.str.strip()).all():
            return False
    return True


def _category_shares_conserve(
    frame: pd.DataFrame, prefix: str, categories: Iterable[str]
) -> bool:
    columns = [f"{prefix}_{category}_share" for category in categories]
    return bool(frame[columns].sum(axis="columns").sub(1).abs().le(1e-8).all())


def _check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def run(root: Path) -> dict[str, object]:
    """Generate and validate complete House and Senate model CSVs."""
    root = root.resolve()
    elections = load_elections(root)
    metadata = load_product_metadata(root)
    spine = build_panel_spine(root, elections)
    population, population_selections = build_population_features(root, spine, metadata)
    socioeconomic, socioeconomic_selections, support_hashes = (
        build_socioeconomic_features(root, spine, metadata)
    )
    panel = spine.merge(
        population,
        on=["election_year", "chamber", "target_plan_id", "district_id"],
        how="left",
        validate="one_to_one",
    ).merge(
        socioeconomic,
        on=["election_year", "chamber", "target_plan_id", "district_id"],
        how="left",
        validate="one_to_one",
    )
    panel = add_population_derivatives(panel)
    panel["election_date"] = pd.to_datetime(panel["election_date"]).dt.strftime(
        "%Y-%m-%d"
    )
    for column in panel.select_dtypes(include="datetime").columns:
        panel[column] = panel[column].dt.strftime("%Y-%m-%d")
    output_dir = root / OUTPUT_ROOT
    output_dir.mkdir(parents=True, exist_ok=True)
    writes = {}
    hashes = {}
    for chamber in ("house", "senate"):
        path = output_dir / f"pa_{chamber}_district_election_features_v2.csv"
        selected = panel[panel["chamber"].eq(chamber)].reset_index(drop=True)
        writes[chamber] = _write_versioned_csv(selected, path)
        hashes[chamber] = _file_hash(path)
    selection = pd.DataFrame([*population_selections, *socioeconomic_selections])
    for column in ("source_period_start", "source_period_end", "source_release_date"):
        selection[column] = pd.to_datetime(selection[column]).dt.strftime("%Y-%m-%d")
    selection = selection.sort_values(
        ["election_year", "chamber", "metric_family"], kind="stable"
    )
    selection_path = output_dir / "source_selection_v2.csv"
    dictionary_path = output_dir / "data_dictionary_v2.csv"
    dictionary = build_data_dictionary(panel.columns)
    writes["source_selection"] = _write_versioned_csv(selection, selection_path)
    writes["data_dictionary"] = _write_versioned_csv(dictionary, dictionary_path)
    hashes["source_selection"] = _file_hash(selection_path)
    hashes["data_dictionary"] = _file_hash(dictionary_path)
    checks = panel_checks(panel)
    qa = {
        "task": "POC039",
        "stage": "model_ready_district_election_csv_v2",
        "election_years": list(ELECTION_YEARS),
        "row_counts": panel.groupby("chamber").size().to_dict(),
        "column_count": len(panel.columns),
        "temporal_cutoff_policy": (
            "Every source period ends on or before the election and every source "
            "product was released on or before the election; no future backfill."
        ),
        "density_definition": (
            "Total population divided by full plan-polygon EPSG:5070 area, "
            "including water; not Census land-area density."
        ),
        "excluded_incomplete_families": [
            "historical_vap_and_cvap",
            "age",
            "historical_race_ethnicity",
            "nativity_citizenship",
            "household_income",
            "housing_tenure",
            "census_land_area_density",
        ],
        "input_hashes": {
            path: sha256(root / path)
            for path in [
                ELECTIONS_PATH,
                PLANS_PATH,
                DECENNIAL_PATH,
                ACS_PATH,
                SOCIOECONOMIC_PATH,
                DECENNIAL_SOCIOECONOMIC_PATH,
                "mappings/acs5_products.csv",
                "mappings/population_periods.csv",
                "mappings/socioeconomic_metric_definitions_v1.csv",
            ]
        },
        "support_hashes": support_hashes,
        "smell_test_ranges": {
            column: {
                "minimum": float(panel[column].min()),
                "median": float(panel[column].median()),
                "maximum": float(panel[column].max()),
            }
            for column in [
                "education_bachelors_plus_share",
                "employment_to_population_rate",
                "civilian_unemployment_rate",
                "labor_force_participation_rate",
                "poverty_below_poverty_line_share",
                "poverty_below_200_percent_share",
                "population_per_total_sq_km",
            ]
        },
        "statewide_socioeconomic_transition_smell_test": (
            socioeconomic_transition_diagnostics(panel)
        ),
        "logical_panel_hash": logical_frame_hash(
            panel, ["chamber", "election_year", "district_id"]
        ),
        "csv_sha256": hashes,
        "artifact_writes": writes,
        "checks": checks,
        "passed": all_pass(checks),
    }
    write_json(root / QA_PATH, qa)
    if not qa["passed"]:
        raise RuntimeError(f"POC039 export checks failed; inspect {QA_PATH}")
    return qa


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC039 passed: {qa['row_counts']} rows, {qa['column_count']} columns")


if __name__ == "__main__":
    main()
