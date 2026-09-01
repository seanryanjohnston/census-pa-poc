"""Prove the current-plan 2020 P2 race/ethnicity stage of POC035."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from census_pa_poc.direct_legislative import (
    AREA_CRS,
    CENSUS_SOURCE,
    EXPECTED_ATOMIC_FRAGMENTS,
    EXPECTED_PARENT_BLOCKS,
    LRC_SOURCE,
    PLAN_CONFIGS,
    WEIGHT_TOLERANCE,
    check,
    load_equivalency,
    load_plan,
    manifest_entry,
    require_manifest_hashes,
)
from census_pa_poc.sources import (
    load_pl94_block_race_ethnicity_statewide,
    vsi_zip_member,
)
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

TABLE_ID = "P2"
METHOD_ID = "lrc_fragment_p002_race_ethnicity_direct_legislative_v1"
WEIGHTING_UNIVERSE = "2020_p2_category_specific_lrc_fragment_support"
MOE_TREATMENT = "not_applicable_exact_decennial_count"
EXPECTED_TOTAL = 13_002_700
CATEGORIES = (
    "hispanic",
    "nh_white",
    "nh_black",
    "nh_aian",
    "nh_asian_pacific",
    "nh_other_multiracial",
)
P2_COLUMNS = (
    "P0020002",
    "P0020005",
    "P0020006",
    "P0020007",
    "P0020008",
    "P0020009",
    "P0020010",
    "P0020011",
)


def _p2_source(source: dict[str, object], role: str) -> dict[str, object]:
    result = deepcopy(source)
    result["population_universe"] = "Total population"
    schema = dict(result["schema"])
    if role == "census":
        schema.update(
            {
                "file01_member": "pa000012020.pl",
                "table": TABLE_ID,
                "selected_cells": list(P2_COLUMNS),
            }
        )
    else:
        schema["support_metrics"] = list(P2_COLUMNS)
    result["schema"] = schema
    return result


CENSUS_P2_SOURCE = _p2_source(CENSUS_SOURCE, "census")
LRC_P2_SOURCE = _p2_source(LRC_SOURCE, "lrc")


def run(root: Path) -> dict[str, object]:
    """Build and validate the POC035 current-plan P2 substage."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc035"
    processed_dir = root / "data/processed/direct_legislative/poc035"
    manifest = build_manifest(root)
    write_json(artifact_dir / "race_2020_input_manifest.json", manifest)
    require_manifest_hashes(manifest)

    atoms = load_p2_atoms(root / str(LRC_P2_SOURCE["relative_path"]))
    source = load_pl94_block_race_ethnicity_statewide(
        root / str(CENSUS_P2_SOURCE["relative_path"])
    )
    source_long = source.melt(
        id_vars="source_block_geoid",
        value_vars=list(CATEGORIES),
        var_name="metric_category",
        value_name="source_estimate",
    ).rename(columns={"source_block_geoid": "source_geography_id"})

    crosswalks = []
    results = []
    comparisons = []
    profiles = []
    checks = []
    for plan_id, config in PLAN_CONFIGS.items():
        plan = load_plan(root, config["plan"])
        equivalency = load_equivalency(
            root / str(config["equivalency"]["relative_path"])
        )
        atomic = build_atomic_assignments(atoms, equivalency, plan_id, config)
        crosswalk = build_crosswalk(atomic)
        result = aggregate_categories(source_long, crosswalk)
        comparison = compare_with_atomic(result, atomic)
        crosswalks.append(crosswalk)
        results.append(result)
        comparisons.append(comparison)
        profiles.append(profile_partition(plan_id, config, plan, crosswalk))
        checks.extend(
            validate_partition(
                config,
                plan,
                atoms,
                source_long,
                atomic,
                crosswalk,
                result,
                comparison,
            )
        )

    crosswalk_all = pd.concat(crosswalks, ignore_index=True)
    results_all = pd.concat(results, ignore_index=True)
    comparisons_all = pd.concat(comparisons, ignore_index=True)
    crosswalk_keys = [
        "target_chamber",
        "source_geography_id",
        "metric_category",
        "target_district_id",
    ]
    result_keys = ["target_chamber", "metric_category", "target_district_id"]
    comparison_keys = result_keys
    writes = {
        "crosswalk": write_immutable_parquet(
            crosswalk_all,
            processed_dir / "census_2020_p002_race_to_2021_plans_v1.parquet",
            crosswalk_keys,
        ),
        "results": write_immutable_parquet(
            results_all,
            processed_dir / "census_2020_p002_race_legislative_results_v1.parquet",
            result_keys,
        ),
        "comparison": write_immutable_parquet(
            comparisons_all,
            processed_dir / "census_2020_p002_race_comparison_v1.parquet",
            comparison_keys,
        ),
    }
    hashes = {
        "crosswalk": logical_frame_hash(crosswalk_all, crosswalk_keys),
        "results": logical_frame_hash(results_all, result_keys),
        "comparison": logical_frame_hash(comparisons_all, comparison_keys),
    }
    qa = {
        "task": "POC035",
        "stage": "current_2020_p2_race_ethnicity",
        "table_id": TABLE_ID,
        "categories": list(CATEGORIES),
        "method_id": METHOD_ID,
        "weighting_universe": WEIGHTING_UNIVERSE,
        "moe_treatment": MOE_TREATMENT,
        "uses_p001_weights": False,
        "uses_p003_weights": False,
        "profiles": profiles,
        "checks": checks,
        "artifact_writes": writes,
        "hashes": hashes,
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "race_2020_qa.json", qa)
    if not qa["passed"]:
        raise RuntimeError("POC035 P2 stage failed; inspect race_2020_qa.json")
    return qa


def load_p2_atoms(path: Path) -> gpd.GeoDataFrame:
    """Load and bridge published P2 cells on corrected LRC fragments."""
    atoms = gpd.read_file(
        vsi_zip_member(path, "Geography/WP_Blocks.shp"),
        columns=["GEOID20", *P2_COLUMNS],
    ).rename(columns={"GEOID20": "source_atomic_geoid"})
    atoms["source_atomic_geoid"] = atoms["source_atomic_geoid"].astype("string")
    atoms["source_geography_id"] = atoms["source_atomic_geoid"].str.slice(0, 15)
    atoms["hispanic"] = atoms["P0020002"]
    atoms["nh_white"] = atoms["P0020005"]
    atoms["nh_black"] = atoms["P0020006"]
    atoms["nh_aian"] = atoms["P0020007"]
    atoms["nh_asian_pacific"] = atoms["P0020008"] + atoms["P0020009"]
    atoms["nh_other_multiracial"] = atoms["P0020010"] + atoms["P0020011"]
    atoms["atomic_area_square_meters"] = atoms.to_crs(AREA_CRS).geometry.area
    return atoms[["source_atomic_geoid", "source_geography_id", *CATEGORIES, "atomic_area_square_meters", "geometry"]]


def build_atomic_assignments(
    atoms: gpd.GeoDataFrame,
    equivalency: pd.DataFrame,
    plan_id: str,
    config: dict[str, object],
) -> pd.DataFrame:
    columns = [
        "source_atomic_geoid",
        "source_geography_id",
        *CATEGORIES,
        "atomic_area_square_meters",
    ]
    assigned = equivalency.merge(
        atoms[columns], on="source_atomic_geoid", how="left", validate="one_to_one"
    )
    long = assigned.melt(
        id_vars=[
            "source_atomic_geoid",
            "source_geography_id",
            "target_district_id",
            "atomic_area_square_meters",
        ],
        value_vars=list(CATEGORIES),
        var_name="metric_category",
        value_name="atomic_category_support",
    )
    return long.assign(
        target_chamber=config["chamber"],
        target_plan_id=plan_id,
        target_plan_reference_vintage="2021",
        source_table_id=TABLE_ID,
    )


def build_crosswalk(atomic: pd.DataFrame) -> pd.DataFrame:
    """Build one P2-support weight set per mutually exclusive category."""
    keys = [
        "target_chamber",
        "target_plan_id",
        "target_plan_reference_vintage",
        "source_geography_id",
        "metric_category",
        "target_district_id",
    ]
    grouped = atomic.groupby(keys, as_index=False).agg(
        district_category_support=("atomic_category_support", "sum"),
        district_atomic_area_square_meters=("atomic_area_square_meters", "sum"),
        atomic_fragment_count=("source_atomic_geoid", "size"),
    )
    parent_keys = [
        "target_chamber",
        "target_plan_id",
        "source_geography_id",
        "metric_category",
    ]
    grouped["parent_category_support"] = grouped.groupby(parent_keys)[
        "district_category_support"
    ].transform("sum")
    grouped["parent_atomic_area_square_meters"] = grouped.groupby(parent_keys)[
        "district_atomic_area_square_meters"
    ].transform("sum")
    grouped["parent_target_count"] = grouped.groupby(parent_keys)[
        "target_district_id"
    ].transform("nunique")
    grouped["weight"] = grouped.apply(category_weight, axis="columns")
    grouped["weight_method"] = grouped.apply(category_weight_method, axis="columns")
    return grouped.assign(
        source_dataset_id="census_2020_pa_blocks",
        source_reference_vintage="2020",
        weighting_universe=WEIGHTING_UNIVERSE,
        method_id=METHOD_ID,
        assignment_status="assigned",
    )


def category_weight(row: pd.Series) -> float:
    if row["parent_target_count"] == 1:
        return 1.0
    if row["parent_category_support"] > 0:
        return float(row["district_category_support"] / row["parent_category_support"])
    return float(
        row["district_atomic_area_square_meters"]
        / row["parent_atomic_area_square_meters"]
    )


def category_weight_method(row: pd.Series) -> str:
    if row["parent_target_count"] == 1:
        return "single_target_identity"
    if row["parent_category_support"] > 0:
        return "published_fragment_p002_category"
    return "zero_category_atomic_area_fallback"


def aggregate_categories(source: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    allocated = crosswalk.merge(
        source,
        on=["source_geography_id", "metric_category"],
        how="left",
        validate="many_to_one",
    )
    allocated["estimate"] = allocated["source_estimate"] * allocated["weight"]
    keys = [
        "target_chamber",
        "target_plan_id",
        "target_district_id",
        "metric_category",
    ]
    result = allocated.groupby(keys, as_index=False)["estimate"].sum()
    return result.assign(
        population_product_id="census_2020_pa_pl",
        population_reference_date="2020-04-01",
        population_release_date="2021-08-12",
        source_table_id=TABLE_ID,
        population_universe="total_population",
        moe=pd.NA,
        moe_treatment=MOE_TREATMENT,
        crosswalk_method_id=METHOD_ID,
        applicable_general_elections="2022-11-08|2024-11-05|2026-11-03",
    )


def compare_with_atomic(result: pd.DataFrame, atomic: pd.DataFrame) -> pd.DataFrame:
    direct = (
        atomic.groupby(
            [
                "target_chamber",
                "target_plan_id",
                "target_district_id",
                "metric_category",
            ],
            as_index=False,
        )["atomic_category_support"]
        .sum()
        .rename(columns={"atomic_category_support": "published_atomic_estimate"})
    )
    comparison = result.merge(
        direct,
        on=[
            "target_chamber",
            "target_plan_id",
            "target_district_id",
            "metric_category",
        ],
        validate="one_to_one",
    )
    comparison["difference"] = comparison["estimate"] - comparison["published_atomic_estimate"]
    return comparison


def profile_partition(
    plan_id: str,
    config: dict[str, object],
    plan: gpd.GeoDataFrame,
    crosswalk: pd.DataFrame,
) -> dict[str, object]:
    return {
        "target_plan_id": plan_id,
        "target_chamber": config["chamber"],
        "district_count": int(plan["target_district_id"].nunique()),
        "crosswalk_rows": len(crosswalk),
        "split_parent_category_rows": int(
            crosswalk["parent_target_count"].gt(1).sum()
        ),
        "published_fragment_rows": int(
            crosswalk["weight_method"].eq("published_fragment_p002_category").sum()
        ),
        "zero_category_fallback_rows": int(
            crosswalk["weight_method"].eq("zero_category_atomic_area_fallback").sum()
        ),
    }


def validate_partition(
    config: dict[str, object],
    plan: gpd.GeoDataFrame,
    atoms: gpd.GeoDataFrame,
    source: pd.DataFrame,
    atomic: pd.DataFrame,
    crosswalk: pd.DataFrame,
    result: pd.DataFrame,
    comparison: pd.DataFrame,
) -> list[dict[str, object]]:
    chamber = str(config["chamber"])
    expected_districts = {
        str(value) for value in range(1, int(config["expected_districts"]) + 1)
    }
    weight_sums = crosswalk.groupby(
        ["source_geography_id", "metric_category"]
    )["weight"].sum()
    atom_parent = atomic.groupby(
        ["source_geography_id", "metric_category"]
    )["atomic_category_support"].sum()
    source_parent = source.set_index(["source_geography_id", "metric_category"])[
        "source_estimate"
    ]
    category_source_totals = source.groupby("metric_category")["source_estimate"].sum()
    category_result_totals = result.groupby("metric_category")["estimate"].sum()
    return [
        check(
            f"{chamber}:plan_districts",
            set(plan["target_district_id"]) == expected_districts,
            int(plan["target_district_id"].nunique()),
        ),
        check(
            f"{chamber}:fragment_count",
            atoms["source_atomic_geoid"].nunique() == EXPECTED_ATOMIC_FRAGMENTS,
            int(atoms["source_atomic_geoid"].nunique()),
        ),
        check(
            f"{chamber}:parent_coverage",
            crosswalk["source_geography_id"].nunique() == EXPECTED_PARENT_BLOCKS,
            int(crosswalk["source_geography_id"].nunique()),
        ),
        check(
            f"{chamber}:fragment_support_matches_census_p2",
            atom_parent.sub(source_parent).eq(0).all(),
            int(atom_parent.sub(source_parent).ne(0).sum()),
        ),
        check(
            f"{chamber}:weights_sum_to_one",
            weight_sums.sub(1).abs().le(WEIGHT_TOLERANCE).all(),
            float(weight_sums.sub(1).abs().max()),
        ),
        check(
            f"{chamber}:category_conservation",
            category_result_totals.sub(category_source_totals)
            .abs()
            .le(WEIGHT_TOLERANCE)
            .all(),
            category_result_totals.sub(category_source_totals).to_dict(),
        ),
        check(
            f"{chamber}:categories_sum_total_population",
            abs(float(category_result_totals.sum()) - EXPECTED_TOTAL)
            <= WEIGHT_TOLERANCE,
            float(category_result_totals.sum()),
        ),
        check(
            f"{chamber}:published_atomic_exact",
            comparison["difference"].abs().le(WEIGHT_TOLERANCE).all(),
            float(comparison["difference"].abs().max()),
        ),
        check(
            f"{chamber}:metric_specific_support",
            crosswalk["weighting_universe"].eq(WEIGHTING_UNIVERSE).all()
            and crosswalk["method_id"].eq(METHOD_ID).all(),
            sorted(crosswalk["weight_method"].unique()),
        ),
        check(
            f"{chamber}:no_moe_for_decennial",
            result["moe"].isna().all()
            and result["moe_treatment"].eq(MOE_TREATMENT).all(),
            MOE_TREATMENT,
        ),
    ]


def build_manifest(root: Path) -> dict[str, object]:
    sources = [CENSUS_P2_SOURCE, LRC_P2_SOURCE]
    for config in PLAN_CONFIGS.values():
        sources.extend([config["plan"], config["equivalency"]])
    return {
        "manifest_version": "1.0.0",
        "created_timestamp": datetime.now(UTC).isoformat(),
        "sources": [manifest_entry(root, source) for source in sources],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC035 P2 stage passed: {qa['passed']}")


if __name__ == "__main__":
    main()
