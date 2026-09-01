"""Reconcile POC population allocations to trusted Census county/state totals."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from census_pa_poc.precinct_inventory import COUNTIES
from census_pa_poc.sources import (
    PublishedPopulationTotalsUnavailableError,
    load_1990_stf1b_block_population,
    load_2000_pl94_block_population,
    load_2010_pl94_block_population,
    load_acs5_block_group_population,
    load_acs5_published_population_totals,
    load_pl94_block_population_statewide,
    sha256,
)
from census_pa_poc.statewide_1990 import SOURCES as SOURCES_1990
from census_pa_poc.statewide_2000 import SOURCES as SOURCES_2000
from census_pa_poc.statewide_2010 import SOURCES as SOURCES_2010
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

RESULT_TOLERANCE = 0.001
EXPECTED_GEOGRAPHIES = 68
ALLOCATED_POPULATION_PATH = Path(
    "data/processed/poc016/fixed_precinct_population_products_v1.parquet"
)
OUTPUT_PATH = Path("data/processed/poc027/population_trusted_reconciliation_v1.parquet")


def run(root: Path) -> dict[str, object]:
    """Build and validate all product-plan county/state reconciliation rows."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc027"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    allocated = pd.read_parquet(root / ALLOCATED_POPULATION_PATH)
    source_totals = load_all_source_totals(root)
    reconciliation = build_reconciliation(allocated, source_totals)
    output_path = root / OUTPUT_PATH
    write_status = write_immutable_parquet(
        reconciliation,
        output_path,
        [
            "population_product_id",
            "senate_plan_id",
            "geography_level",
            "geography_id",
        ],
    )

    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    checks = build_checks(allocated, source_totals, reconciliation)
    qa = {
        "task": "POC027",
        "created_at": datetime.now(UTC).isoformat(),
        "result_tolerance_people": RESULT_TOLERANCE,
        "artifact_write": write_status,
        "output_relative_path": OUTPUT_PATH.as_posix(),
        "logical_sha256": logical_frame_hash(
            reconciliation,
            [
                "population_product_id",
                "senate_plan_id",
                "geography_level",
                "geography_id",
            ],
        ),
        "rows": len(reconciliation),
        "product_plan_partitions": int(
            reconciliation[["population_product_id", "senate_plan_id"]]
            .drop_duplicates()
            .shape[0]
        ),
        "maximum_absolute_allocation_delta": float(
            reconciliation["allocated_minus_source_sum"].abs().max()
        ),
        "maximum_absolute_source_to_published_delta": float(
            reconciliation["source_sum_minus_published_aggregate"]
            .abs()
            .max(skipna=True)
        ),
        "checks": checks,
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(render_report(qa))
    if not qa["passed"]:
        raise RuntimeError("POC027 QA failed; inspect artifacts/poc027/qa_results.json")
    return qa


def load_all_source_totals(root: Path) -> pd.DataFrame:
    """Load source-unit sums and independent published ACS aggregates."""
    frames = [
        source_totals_for_product(
            "dec_1990",
            load_1990_stf1b_block_population(
                root / SOURCES_1990["census_population"]["relative_path"]
            ),
            "source_block_geoid",
            "P0010001",
            provenance_for_decennial("dec_1990"),
        ),
        source_totals_for_product(
            "dec_2000",
            load_2000_pl94_block_population(
                root / SOURCES_2000["census_population_geography"]["relative_path"],
                root / SOURCES_2000["census_population_file01"]["relative_path"],
            ),
            "source_block_geoid",
            "P0010001",
            provenance_for_decennial("dec_2000"),
        ),
        source_totals_for_product(
            "dec_2010",
            load_2010_pl94_block_population(
                root / SOURCES_2010["census_population"]["relative_path"]
            ),
            "source_block_geoid",
            "P0010001",
            provenance_for_decennial("dec_2010"),
        ),
        source_totals_for_product(
            "dec_2020",
            load_pl94_block_population_statewide(
                root / "data/raw/census_2020_pa_pl/pa2020.pl.zip"
            ),
            "source_block_geoid",
            "P0010001",
            provenance_for_decennial("dec_2020"),
        ),
    ]
    acs_catalog = pd.read_csv(root / "mappings/acs5_products.csv", dtype="string")
    for year in range(2009, 2025):
        product_id = f"acs5_{year}"
        directory = root / f"data/raw/acs5_all_pa/{year}"
        source_units = load_acs5_block_group_population(year, directory)
        published_unavailable_status = None
        try:
            published = load_acs5_published_population_totals(year, directory)
        except PublishedPopulationTotalsUnavailableError:
            published = None
            published_unavailable_status = (
                "not_present_in_accepted_tract_block_group_extract"
            )
        catalog_row = acs_catalog[acs_catalog["product_id"].eq(product_id)]
        if len(catalog_row) != 1:
            raise ValueError(f"expected one ACS catalog row for {product_id}")
        frames.append(
            source_totals_for_product(
                product_id,
                source_units,
                "source_block_group_geoid",
                "B01003_001E",
                provenance_for_acs(catalog_row.iloc[0]),
                published,
                published_unavailable_status,
            )
        )
    return normalize_source_totals(pd.concat(frames, ignore_index=True))


def source_totals_for_product(
    product_id: str,
    source_units: pd.DataFrame,
    source_id_column: str,
    value_column: str,
    provenance: dict[str, object],
    published: pd.DataFrame | None = None,
    published_unavailable_status: str | None = None,
) -> pd.DataFrame:
    """Aggregate accepted source units to all PA counties and the state."""
    units = source_units[[source_id_column, value_column]].copy()
    units["county_fips"] = units[source_id_column].astype("string").str.slice(2, 5)
    county = units.groupby("county_fips", as_index=False)[value_column].sum()
    county = county.rename(
        columns={
            "county_fips": "geography_id",
            value_column: "official_source_unit_sum",
        }
    )
    county["geography_level"] = "county"
    county["geography_name"] = county["geography_id"].map(COUNTIES)
    state = pd.DataFrame(
        {
            "geography_id": ["42"],
            "official_source_unit_sum": [units[value_column].sum()],
            "geography_level": ["state"],
            "geography_name": ["Pennsylvania"],
        }
    )
    result = pd.concat([state, county], ignore_index=True)
    result["population_product_id"] = product_id
    result["source_unit_count"] = result.apply(
        lambda row: (
            len(units)
            if row["geography_level"] == "state"
            else int(units["county_fips"].eq(row["geography_id"]).sum())
        ),
        axis=1,
    )
    result["source_sum_status"] = "available"
    result["published_aggregate"] = pd.NA
    result["published_margin_of_error"] = pd.NA
    result["published_margin_of_error_status"] = pd.NA
    result["published_aggregate_status"] = "not_loaded_for_decennial_product"
    if published_unavailable_status is not None:
        result["published_aggregate_status"] = published_unavailable_status
    result["published_source_record_geoid"] = pd.NA
    if published is not None:
        result = result.drop(
            columns=[
                "published_aggregate",
                "published_margin_of_error",
                "published_margin_of_error_status",
                "published_aggregate_status",
                "published_source_record_geoid",
            ]
        ).merge(
            published.rename(
                columns={
                    "published_estimate": "published_aggregate",
                    "margin_of_error_status": "published_margin_of_error_status",
                    "source_record_geoid": "published_source_record_geoid",
                }
            )[
                [
                    "geography_level",
                    "geography_id",
                    "published_aggregate",
                    "published_margin_of_error",
                    "published_margin_of_error_status",
                    "published_source_record_geoid",
                ]
            ],
            on=["geography_level", "geography_id"],
            how="left",
            validate="one_to_one",
        )
        result["published_aggregate_status"] = (
            result["published_aggregate"]
            .notna()
            .map({True: "available", False: "missing_from_official_product"})
        )
    for field, value in provenance.items():
        result[field] = value
    return result


def build_reconciliation(
    allocated: pd.DataFrame, source_totals: pd.DataFrame
) -> pd.DataFrame:
    """Compare every product-plan allocation to its trusted source totals."""
    required = {
        "population_product_id",
        "senate_plan_id",
        "target_precinct_geoid",
        "estimate",
    }
    missing = required.difference(allocated.columns)
    if missing:
        raise ValueError(f"allocated population is missing columns: {sorted(missing)}")
    rows = allocated[list(required)].copy()
    rows["geography_id"] = (
        rows["target_precinct_geoid"].astype("string").str.slice(2, 5)
    )
    county = (
        rows.groupby(
            ["population_product_id", "senate_plan_id", "geography_id"],
            as_index=False,
        )["estimate"]
        .sum()
        .rename(columns={"estimate": "allocated_estimate"})
    )
    county["geography_level"] = "county"
    state = (
        rows.groupby(["population_product_id", "senate_plan_id"], as_index=False)[
            "estimate"
        ]
        .sum()
        .rename(columns={"estimate": "allocated_estimate"})
    )
    state["geography_id"] = "42"
    state["geography_level"] = "state"
    allocation_totals = pd.concat([state, county], ignore_index=True)
    result = allocation_totals.merge(
        source_totals,
        on=["population_product_id", "geography_level", "geography_id"],
        how="left",
        validate="many_to_one",
    )
    if result["official_source_unit_sum"].isna().any():
        raise ValueError("allocated partition has no trusted source total")
    result["allocated_minus_source_sum"] = (
        result["allocated_estimate"] - result["official_source_unit_sum"]
    )
    result["allocation_comparison_status"] = (
        result["allocated_minus_source_sum"]
        .abs()
        .le(RESULT_TOLERANCE)
        .map({True: "within_tolerance", False: "outside_tolerance"})
    )
    result["allocated_minus_published_aggregate"] = (
        result["allocated_estimate"] - result["published_aggregate"]
    )
    result["source_sum_minus_published_aggregate"] = (
        result["official_source_unit_sum"] - result["published_aggregate"]
    )
    result["source_to_published_comparison_status"] = result.apply(
        source_to_published_status, axis=1
    )
    result["comparison_tolerance_people"] = RESULT_TOLERANCE
    return normalize_reconciliation(result)


def source_to_published_status(row: pd.Series) -> str:
    if row["published_aggregate_status"] != "available":
        return "not_applicable_or_unavailable"
    if abs(row["source_sum_minus_published_aggregate"]) <= RESULT_TOLERANCE:
        return "within_tolerance"
    return "outside_tolerance"


def normalize_source_totals(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    string_columns = [
        "population_product_id",
        "geography_level",
        "geography_id",
        "geography_name",
        "source_sum_status",
        "published_aggregate_status",
        "published_margin_of_error_status",
        "published_source_record_geoid",
        "producer",
        "source_product",
        "source_unit_geography",
        "metric",
        "population_universe",
        "reference_start",
        "reference_end",
        "release_date",
        "source_url",
        "published_aggregate_source_url",
        "license_access",
    ]
    for column in string_columns:
        result[column] = result[column].astype("string")
    result["source_unit_count"] = result["source_unit_count"].astype("int64")
    result["official_source_unit_sum"] = pd.to_numeric(
        result["official_source_unit_sum"], errors="raise"
    ).astype("float64")
    result["published_aggregate"] = pd.to_numeric(
        result["published_aggregate"], errors="coerce"
    ).astype("Float64")
    result["published_margin_of_error"] = pd.to_numeric(
        result["published_margin_of_error"], errors="coerce"
    ).astype("Float64")
    return result.sort_values(
        ["population_product_id", "geography_level", "geography_id"], kind="stable"
    ).reset_index(drop=True)


def normalize_reconciliation(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in [
        "population_product_id",
        "senate_plan_id",
        "geography_level",
        "geography_id",
        "geography_name",
        "allocation_comparison_status",
        "source_to_published_comparison_status",
    ]:
        result[column] = result[column].astype("string")
    for column in [
        "allocated_estimate",
        "official_source_unit_sum",
        "published_aggregate",
        "allocated_minus_source_sum",
        "allocated_minus_published_aggregate",
        "source_sum_minus_published_aggregate",
        "comparison_tolerance_people",
    ]:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "Float64"
        )
    return result.sort_values(
        [
            "population_product_id",
            "senate_plan_id",
            "geography_level",
            "geography_id",
        ],
        kind="stable",
    ).reset_index(drop=True)


def provenance_for_decennial(product_id: str) -> dict[str, object]:
    sources = {
        "dec_1990": SOURCES_1990["census_population"],
        "dec_2000": SOURCES_2000["census_population_file01"],
        "dec_2010": SOURCES_2010["census_population"],
        "dec_2020": {
            "producer": "U.S. Census Bureau",
            "product": "2020 Census State Redistricting Data PL 94-171 Summary File",
            "population_universe": "Standard total population, P0010001",
            "reference_vintage": "2020-04-01",
            "release_date": "2021-08-12",
            "url": (
                "https://www2.census.gov/programs-surveys/decennial/2020/data/"
                "01-Redistricting_File--PL_94-171/Pennsylvania/pa2020.pl.zip"
            ),
            "license_access": "Public federal data; cite U.S. Census Bureau",
        },
    }
    source = sources[product_id]
    metric = "POP100" if product_id == "dec_1990" else "P0010001"
    reference = str(source["reference_vintage"])
    return {
        "producer": source["producer"],
        "source_product": source["product"],
        "source_unit_geography": "census_block",
        "metric": metric,
        "population_universe": source["population_universe"],
        "reference_start": reference,
        "reference_end": reference,
        "release_date": source["release_date"],
        "source_url": source["url"],
        "published_aggregate_source_url": pd.NA,
        "license_access": source["license_access"],
    }


def provenance_for_acs(row: pd.Series) -> dict[str, object]:
    return {
        "producer": "U.S. Census Bureau",
        "source_product": row["product_family"],
        "source_unit_geography": "census_block_group",
        "metric": row["estimate_variable"],
        "population_universe": row["population_universe"],
        "reference_start": row["period_start"],
        "reference_end": row["period_end"],
        "release_date": row["release_date"],
        "source_url": row["summary_file_url"],
        "published_aggregate_source_url": row["summary_file_url"],
        "license_access": "Public federal data; cite U.S. Census Bureau",
    }


def build_checks(
    allocated: pd.DataFrame,
    source_totals: pd.DataFrame,
    reconciliation: pd.DataFrame,
) -> list[dict[str, object]]:
    partitions = allocated[
        ["population_product_id", "senate_plan_id"]
    ].drop_duplicates()
    expected_rows = len(partitions) * EXPECTED_GEOGRAPHIES
    statewide = reconciliation[reconciliation["geography_level"].eq("state")]
    counties = reconciliation[reconciliation["geography_level"].eq("county")]
    county_balance = counties.groupby(["population_product_id", "senate_plan_id"])[
        "allocated_minus_source_sum"
    ].sum()
    published = reconciliation[
        reconciliation["published_aggregate_status"].eq("available")
    ]
    return [
        check(
            "all_products_have_68_trusted_geographies",
            source_totals.groupby("population_product_id")
            .size()
            .eq(EXPECTED_GEOGRAPHIES)
            .all(),
            source_totals.groupby("population_product_id").size().to_dict(),
        ),
        check(
            "all_product_plan_partitions_have_68_comparisons",
            len(reconciliation) == expected_rows
            and reconciliation.groupby(["population_product_id", "senate_plan_id"])
            .size()
            .eq(EXPECTED_GEOGRAPHIES)
            .all(),
            {"observed": len(reconciliation), "expected": expected_rows},
        ),
        check(
            "allocated_statewide_totals_conserved",
            statewide["allocated_minus_source_sum"].abs().le(RESULT_TOLERANCE).all(),
            {
                "maximum_absolute_delta": float(
                    statewide["allocated_minus_source_sum"].abs().max()
                ),
                "tolerance": RESULT_TOLERANCE,
            },
        ),
        check(
            "county_deltas_are_complete_and_balance_statewide",
            counties["allocated_minus_source_sum"].notna().all()
            and county_balance.abs().le(RESULT_TOLERANCE).all(),
            {
                "county_comparisons": len(counties),
                "outside_tolerance": int(
                    counties["allocated_minus_source_sum"]
                    .abs()
                    .gt(RESULT_TOLERANCE)
                    .sum()
                ),
                "maximum_absolute_county_delta": float(
                    counties["allocated_minus_source_sum"].abs().max()
                ),
                "maximum_absolute_partition_balance": float(county_balance.abs().max()),
                "tolerance": RESULT_TOLERANCE,
            },
        ),
        check(
            "acs_direct_aggregate_availability_is_typed",
            source_totals[
                source_totals["population_product_id"].str.startswith("acs5_")
            ]["published_aggregate_status"]
            .isin(
                {
                    "available",
                    "not_present_in_accepted_tract_block_group_extract",
                }
            )
            .all()
            and source_totals[
                source_totals["population_product_id"].str.startswith("acs5_")
                & source_totals["published_aggregate_status"].eq("available")
            ]["published_aggregate"]
            .notna()
            .all(),
            source_totals[
                source_totals["population_product_id"].str.startswith("acs5_")
            ]["published_aggregate_status"]
            .value_counts()
            .to_dict(),
        ),
        check(
            "source_unit_sums_match_published_acs_aggregates",
            published["source_sum_minus_published_aggregate"]
            .abs()
            .le(RESULT_TOLERANCE)
            .all(),
            {
                "published_comparisons": len(published),
                "maximum_absolute_delta": float(
                    published["source_sum_minus_published_aggregate"].abs().max()
                ),
                "tolerance": RESULT_TOLERANCE,
            },
        ),
    ]


def build_manifest(root: Path) -> dict[str, object]:
    allocated_path = root / ALLOCATED_POPULATION_PATH
    sources = [
        root / SOURCES_1990["census_population"]["relative_path"],
        root / SOURCES_2000["census_population_geography"]["relative_path"],
        root / SOURCES_2000["census_population_file01"]["relative_path"],
        root / SOURCES_2010["census_population"]["relative_path"],
        root / "data/raw/census_2020_pa_pl/pa2020.pl.zip",
    ]
    sources.extend(sorted((root / "data/raw/acs5_all_pa").glob("*/*")))
    return {
        "task": "POC027",
        "created_at": datetime.now(UTC).isoformat(),
        "derived_input": {
            "producer": "POC016",
            "exact_product": ALLOCATED_POPULATION_PATH.name,
            "relative_path": ALLOCATED_POPULATION_PATH.as_posix(),
            "sha256": sha256(allocated_path),
            "schema": "fixed precinct population products v1",
            "geographic_universe": "Pennsylvania fixed 2021 LRC precinct target",
        },
        "official_source_files": [
            {
                "producer": "U.S. Census Bureau",
                "exact_product": path.name,
                "relative_path": path.relative_to(root).as_posix(),
                "retrieval_timestamp": datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ).isoformat(),
                "sha256": sha256(path),
                "license_access": "Public federal data; cite U.S. Census Bureau",
                "crs": None,
                "geographic_universe": "Pennsylvania",
            }
            for path in sources
            if path.is_file()
        ],
    }


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(qa: dict[str, object]) -> str:
    passed = sum(check_row["passed"] for check_row in qa["checks"])
    return f"""# POC027 trusted Census reconciliation

- Passed: `{qa["passed"]}`
- Product/plan partitions: `{qa["product_plan_partitions"]}`
- County/state comparison rows: `{qa["rows"]}`
- Maximum allocation-to-source-sum delta: `{qa["maximum_absolute_allocation_delta"]}` people
- Maximum source-sum-to-published-ACS delta: `{qa["maximum_absolute_source_to_published_delta"]}` people
- QA checks passed: `{passed}` of `{len(qa["checks"])}`
- Result logical SHA-256: `{qa["logical_sha256"]}`

The source-unit benchmark is the exact sum of the accepted Census blocks or
block groups used by the allocation. The published aggregate is a separate,
direct Census B01003 county/state record for ACS products. Decennial direct
aggregate rows are intentionally typed as not loaded. The accepted 2009–2020
tract/block-group extracts omit direct aggregate cells; 2021–2024 table products
contain them. Unavailable values are never inferred from the source-unit sum.

## Reproduce

```bash
.venv/bin/python -m census_pa_poc.source_reconciliation --root .
```
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run(args.root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
