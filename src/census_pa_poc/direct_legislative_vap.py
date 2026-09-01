"""Prove direct 2020 voting-age population legislative allocations for POC031."""

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
from census_pa_poc.sources import load_pl94_block_vap_statewide, vsi_zip_member
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

METRIC_ID = "P0030001"
TABLE_ID = "P3"
EXPECTED_VAP = 10_353_548
METHOD_ID = "lrc_fragment_p003_vap_direct_legislative_v1"
WEIGHTING_UNIVERSE = "2020_population_18_years_and_over_on_lrc_fragments"
MOE_TREATMENT = "not_applicable_exact_decennial_count"
TECHNICAL_DOCUMENTATION_URL = (
    "https://www2.census.gov/programs-surveys/decennial/2020/"
    "technical-documentation/complete-tech-docs/summary-file/"
    "2020Census_PL94_171Redistricting_StatesTechDoc_English.pdf"
)


def _metric_source(source: dict[str, object], role: str) -> dict[str, object]:
    result = deepcopy(source)
    result["population_universe"] = "Total population 18 years and over"
    schema = dict(result["schema"])
    if role == "census":
        schema.update(
            {
                "file02_member": "pa000022020.pl",
                "metric": METRIC_ID,
                "table": TABLE_ID,
                "metric_position_zero_based": 5,
                "technical_documentation_url": TECHNICAL_DOCUMENTATION_URL,
            }
        )
        schema.pop("file01_member", None)
    else:
        schema["support_metric"] = METRIC_ID
    result["schema"] = schema
    return result


CENSUS_VAP_SOURCE = _metric_source(CENSUS_SOURCE, "census")
LRC_VAP_SOURCE = _metric_source(LRC_SOURCE, "lrc")


def run(root: Path) -> dict[str, object]:
    """Build, validate, and freeze the POC031 VAP proof."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc031"
    processed_dir = root / "data/processed/direct_legislative"

    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    require_manifest_hashes(manifest)

    atoms = load_vap_atoms(root / str(LRC_VAP_SOURCE["relative_path"]))
    vap = load_pl94_block_vap_statewide(
        root / str(CENSUS_VAP_SOURCE["relative_path"])
    )

    crosswalk_frames = []
    result_frames = []
    comparison_frames = []
    profiles = []
    checks = []
    for plan_id, config in PLAN_CONFIGS.items():
        plan = load_plan(root, config["plan"])
        equivalency = load_equivalency(
            root / str(config["equivalency"]["relative_path"])
        )
        atomic = build_vap_atomic_assignments(atoms, equivalency, plan_id, config)
        crosswalk = build_vap_crosswalk(atomic)
        result = aggregate_vap(vap, crosswalk)
        comparison = compare_with_atomic_vap(result, atomic)

        crosswalk_frames.append(crosswalk)
        result_frames.append(result)
        comparison_frames.append(comparison)
        profiles.append(profile_partition(plan_id, config, plan, atomic, crosswalk))
        checks.extend(
            validate_partition(
                plan_id,
                config,
                plan,
                equivalency,
                atoms,
                vap,
                atomic,
                crosswalk,
                result,
                comparison,
            )
        )

    crosswalk_all = pd.concat(crosswalk_frames, ignore_index=True)
    results_all = pd.concat(result_frames, ignore_index=True)
    comparisons_all = pd.concat(comparison_frames, ignore_index=True)
    writes = {
        "vap_crosswalk": write_immutable_parquet(
            crosswalk_all,
            processed_dir / "census_2020_p003_vap_to_2021_legislative_plan_v1.parquet",
            ["target_chamber", "source_geography_id", "target_district_id"],
        ),
        "vap_results": write_immutable_parquet(
            results_all,
            processed_dir / "census_2020_p003_vap_legislative_results_v1.parquet",
            ["target_chamber", "target_district_id"],
        ),
        "atomic_comparison": write_immutable_parquet(
            comparisons_all,
            processed_dir / "census_2020_p003_vap_legislative_comparison_v1.parquet",
            ["target_chamber", "target_district_id"],
        ),
    }
    hashes = {
        "vap_crosswalk": logical_frame_hash(
            crosswalk_all,
            ["target_chamber", "source_geography_id", "target_district_id"],
        ),
        "vap_results": logical_frame_hash(
            results_all, ["target_chamber", "target_district_id"]
        ),
        "atomic_comparison": logical_frame_hash(
            comparisons_all, ["target_chamber", "target_district_id"]
        ),
    }
    qa = {
        "task": "POC031",
        "metric": {
            "table_id": TABLE_ID,
            "metric_id": METRIC_ID,
            "label": "Voting-age population",
            "universe": "Total population 18 years and over",
            "source_geography": "2020 Census tabulation block",
            "support_metric_id": METRIC_ID,
        },
        "method_id": METHOD_ID,
        "weighting_universe": WEIGHTING_UNIVERSE,
        "zero_support_fallback": (
            "atomic area only for a zero-VAP parent split across districts; "
            "no such fallback affects the accepted results"
        ),
        "uncertainty": (
            "Exact decennial count with no sampling MOE; Census disclosure-"
            "avoidance and nonsampling limitations remain, and no allocation-"
            "weight uncertainty is quantified"
        ),
        "moe_treatment": MOE_TREATMENT,
        "uses_total_population_weights": False,
        "uses_precinct_input": False,
        "uses_nearest_assignment": False,
        "profiles": profiles,
        "checks": checks,
        "artifact_writes": writes,
        "hashes": hashes,
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(render_report(qa))
    if not qa["passed"]:
        raise RuntimeError("POC031 QA failed; inspect artifacts/poc031/qa_results.json")
    return qa


def load_vap_atoms(path: Path) -> gpd.GeoDataFrame:
    """Load P3 VAP support on LRC corrected fragments."""
    atoms = gpd.read_file(
        vsi_zip_member(path, "Geography/WP_Blocks.shp"),
        columns=["GEOID20", "P0010001", METRIC_ID],
    ).rename(
        columns={
            "GEOID20": "source_atomic_geoid",
            "P0010001": "atomic_total_population",
            METRIC_ID: "atomic_vap_support",
        }
    )
    atoms["source_atomic_geoid"] = atoms["source_atomic_geoid"].astype("string")
    atoms["source_geography_id"] = atoms["source_atomic_geoid"].str.slice(0, 15)
    atoms["atomic_total_population"] = atoms["atomic_total_population"].astype(
        "int64"
    )
    atoms["atomic_vap_support"] = atoms["atomic_vap_support"].astype("int64")
    atoms["atomic_area_square_meters"] = atoms.to_crs(AREA_CRS).geometry.area
    return atoms


def build_vap_atomic_assignments(
    atoms: gpd.GeoDataFrame,
    equivalency: pd.DataFrame,
    plan_id: str,
    config: dict[str, object],
) -> pd.DataFrame:
    """Attach each VAP-support fragment to its published legislative district."""
    columns = [
        "source_atomic_geoid",
        "source_geography_id",
        "atomic_total_population",
        "atomic_vap_support",
        "atomic_area_square_meters",
    ]
    result = equivalency.merge(
        atoms[columns], on="source_atomic_geoid", how="left", validate="one_to_one"
    )
    return result.assign(
        source_dataset_id=LRC_VAP_SOURCE["source_id"],
        source_reference_vintage="2020",
        source_metric_id=METRIC_ID,
        target_plan_id=plan_id,
        target_plan_reference_vintage="2021",
        target_chamber=config["chamber"],
        assignment_method_id="lrc_2021_final_block_equivalency_v1",
        assignment_status="assigned",
    )


def build_vap_crosswalk(atomic: pd.DataFrame) -> pd.DataFrame:
    """Create parent/district weights from P003 VAP, never P001 weights."""
    keys = [
        "target_chamber",
        "target_plan_id",
        "target_plan_reference_vintage",
        "source_geography_id",
        "target_district_id",
    ]
    grouped = atomic.groupby(keys, as_index=False).agg(
        district_vap_support=("atomic_vap_support", "sum"),
        district_atomic_area_square_meters=("atomic_area_square_meters", "sum"),
        atomic_fragment_count=("source_atomic_geoid", "size"),
    )
    parent_keys = ["target_chamber", "target_plan_id", "source_geography_id"]
    grouped["parent_vap_support"] = grouped.groupby(parent_keys)[
        "district_vap_support"
    ].transform("sum")
    grouped["parent_atomic_area_square_meters"] = grouped.groupby(parent_keys)[
        "district_atomic_area_square_meters"
    ].transform("sum")
    grouped["parent_target_count"] = grouped.groupby(parent_keys)[
        "target_district_id"
    ].transform("nunique")
    grouped["weight"] = grouped.apply(vap_weight, axis=1)
    grouped["weight_method"] = grouped.apply(vap_weight_method, axis=1)
    return grouped.assign(
        source_dataset_id="census_2020_pa_blocks",
        source_reference_vintage="2020",
        source_metric_id=METRIC_ID,
        weighting_universe=WEIGHTING_UNIVERSE,
        method_id=METHOD_ID,
        assignment_status="assigned",
    )


def vap_weight(row: pd.Series) -> float:
    if row["parent_target_count"] == 1:
        return 1.0
    if row["parent_vap_support"] > 0:
        return float(row["district_vap_support"] / row["parent_vap_support"])
    return float(
        row["district_atomic_area_square_meters"]
        / row["parent_atomic_area_square_meters"]
    )


def vap_weight_method(row: pd.Series) -> str:
    if row["parent_target_count"] == 1:
        return "single_target_identity"
    if row["parent_vap_support"] > 0:
        return "published_fragment_p003"
    return "zero_vap_atomic_area_fallback"


def aggregate_vap(vap: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    allocated = crosswalk.merge(
        vap[["source_block_geoid", METRIC_ID]],
        left_on="source_geography_id",
        right_on="source_block_geoid",
        how="left",
        validate="many_to_one",
    )
    allocated["estimate"] = allocated[METRIC_ID] * allocated["weight"]
    keys = ["target_chamber", "target_plan_id", "target_district_id"]
    result = allocated.groupby(keys, as_index=False)["estimate"].sum()
    return result.assign(
        population_product_id="census_2020_pa_pl",
        population_reference_date="2020-04-01",
        population_release_date="2021-08-12",
        source_table_id=TABLE_ID,
        source_metric_id=METRIC_ID,
        metric_label="Voting-age population",
        population_universe="total_population_18_years_and_over",
        moe=pd.NA,
        moe_treatment=MOE_TREATMENT,
        crosswalk_method_id=METHOD_ID,
        applicable_general_elections="2022-11-08|2024-11-05|2026-11-03",
    )


def compare_with_atomic_vap(
    result: pd.DataFrame, atomic: pd.DataFrame
) -> pd.DataFrame:
    direct = (
        atomic.groupby(
            ["target_chamber", "target_plan_id", "target_district_id"],
            as_index=False,
        )["atomic_vap_support"]
        .sum()
        .rename(columns={"atomic_vap_support": "published_atomic_vap"})
    )
    comparison = result.merge(
        direct,
        on=["target_chamber", "target_plan_id", "target_district_id"],
        how="outer",
        validate="one_to_one",
    )
    comparison["difference"] = (
        comparison["estimate"] - comparison["published_atomic_vap"]
    )
    return comparison[
        [
            "target_chamber",
            "target_plan_id",
            "target_district_id",
            "estimate",
            "published_atomic_vap",
            "difference",
        ]
    ]


def profile_partition(
    plan_id: str,
    config: dict[str, object],
    plan: gpd.GeoDataFrame,
    atomic: pd.DataFrame,
    crosswalk: pd.DataFrame,
) -> dict[str, object]:
    return {
        "target_plan_id": plan_id,
        "target_chamber": config["chamber"],
        "district_count": int(plan["target_district_id"].nunique()),
        "atomic_assignment_rows": len(atomic),
        "parent_crosswalk_rows": len(crosswalk),
        "split_parent_count": int(
            crosswalk.groupby("source_geography_id")["target_district_id"]
            .nunique()
            .gt(1)
            .sum()
        ),
        "published_fragment_p003_rows": int(
            crosswalk["weight_method"].eq("published_fragment_p003").sum()
        ),
        "zero_vap_area_fallback_rows": int(
            crosswalk["weight_method"].eq("zero_vap_atomic_area_fallback").sum()
        ),
    }


def validate_partition(
    plan_id: str,
    config: dict[str, object],
    plan: gpd.GeoDataFrame,
    equivalency: pd.DataFrame,
    atoms: gpd.GeoDataFrame,
    vap: pd.DataFrame,
    atomic: pd.DataFrame,
    crosswalk: pd.DataFrame,
    result: pd.DataFrame,
    comparison: pd.DataFrame,
) -> list[dict[str, object]]:
    prefix = config["chamber"]
    expected_districts = {
        str(value) for value in range(1, config["expected_districts"] + 1)
    }
    weight_sums = crosswalk.groupby("source_geography_id")["weight"].sum()
    atom_parent_vap = atoms.groupby("source_geography_id")[
        "atomic_vap_support"
    ].sum()
    census_vap = vap.set_index("source_block_geoid")[METRIC_ID]
    support_difference = atom_parent_vap.sub(census_vap).abs()
    forbidden_columns = [column for column in crosswalk if "precinct" in column]
    allowed_methods = {
        "single_target_identity",
        "published_fragment_p003",
        "zero_vap_atomic_area_fallback",
    }
    return [
        check(
            f"{prefix}:plan_districts",
            set(plan["target_district_id"]) == expected_districts,
            int(plan["target_district_id"].nunique()),
        ),
        check(
            f"{prefix}:equivalency_rows",
            len(equivalency) == EXPECTED_ATOMIC_FRAGMENTS,
            len(equivalency),
        ),
        check(
            f"{prefix}:equivalency_atom_coverage",
            set(equivalency["source_atomic_geoid"])
            == set(atoms["source_atomic_geoid"]),
            len(
                set(equivalency["source_atomic_geoid"])
                ^ set(atoms["source_atomic_geoid"])
            ),
        ),
        check(
            f"{prefix}:parent_coverage",
            crosswalk["source_geography_id"].nunique() == EXPECTED_PARENT_BLOCKS,
            int(crosswalk["source_geography_id"].nunique()),
        ),
        check(
            f"{prefix}:vap_not_greater_than_total_population",
            bool((atomic["atomic_vap_support"] <= atomic["atomic_total_population"]).all()),
            int(
                (atomic["atomic_vap_support"] > atomic["atomic_total_population"]).sum()
            ),
        ),
        check(
            f"{prefix}:fragment_support_matches_census_p3",
            bool(support_difference.eq(0).all()),
            int(support_difference.ne(0).sum()),
        ),
        check(
            f"{prefix}:weights_in_range",
            bool(crosswalk["weight"].between(0, 1, inclusive="both").all()),
            int((~crosswalk["weight"].between(0, 1, inclusive="both")).sum()),
        ),
        check(
            f"{prefix}:weights_sum_to_one",
            bool(weight_sums.sub(1).abs().le(WEIGHT_TOLERANCE).all()),
            float(weight_sums.sub(1).abs().max()),
        ),
        check(
            f"{prefix}:metric_specific_support",
            crosswalk["source_metric_id"].eq(METRIC_ID).all()
            and crosswalk["weighting_universe"].eq(WEIGHTING_UNIVERSE).all()
            and set(crosswalk["weight_method"]).issubset(allowed_methods),
            sorted(crosswalk["weight_method"].unique()),
        ),
        check(
            f"{prefix}:no_precinct_columns", not forbidden_columns, forbidden_columns
        ),
        check(
            f"{prefix}:result_districts",
            set(result["target_district_id"]) == expected_districts,
            len(result),
        ),
        check(
            f"{prefix}:vap_conserved",
            abs(float(result["estimate"].sum()) - EXPECTED_VAP) <= WEIGHT_TOLERANCE,
            float(result["estimate"].sum()),
        ),
        check(
            f"{prefix}:published_atomic_vap_exact",
            bool(comparison["difference"].abs().le(WEIGHT_TOLERANCE).all()),
            float(comparison["difference"].abs().max()),
        ),
        check(
            f"{prefix}:moe_not_applicable",
            result["moe"].isna().all()
            and result["moe_treatment"].eq(MOE_TREATMENT).all(),
            MOE_TREATMENT,
        ),
        check(
            f"{prefix}:plan_identity",
            atomic["target_plan_id"].eq(plan_id).all()
            and crosswalk["target_plan_id"].eq(plan_id).all(),
            plan_id,
        ),
    ]


def build_manifest(root: Path) -> dict[str, object]:
    sources = [CENSUS_VAP_SOURCE, LRC_VAP_SOURCE]
    for config in PLAN_CONFIGS.values():
        sources.extend([config["plan"], config["equivalency"]])
    return {
        "manifest_version": "1.0.0",
        "created_timestamp": datetime.now(UTC).isoformat(),
        "sources": [manifest_entry(root, source) for source in sources],
    }


def render_report(qa: dict[str, object]) -> str:
    status = "PASS" if qa["passed"] else "FAIL"
    profile_lines = "\n".join(
        (
            f"- {profile['target_chamber']}: {profile['district_count']} districts, "
            f"{profile['parent_crosswalk_rows']:,} parent/district rows, "
            f"{profile['split_parent_count']} split parent blocks, "
            f"{profile['zero_vap_area_fallback_rows']} zero-VAP fallback rows"
        )
        for profile in qa["profiles"]
    )
    return f"""# POC031 direct voting-age population proof

Status: **{status}**

The selected additive metric is 2020 PL 94-171 table P3 cell `P0030001`,
voting-age population with the universe "Total population 18 years and over."
The crosswalk uses published fragment-level `P0030001` support rather than
relabeling the accepted `P0010001` total-population weights.

{profile_lines}

Both chambers conserve {EXPECTED_VAP:,} voting-age residents and agree exactly
with direct sums of the published fragment P3 support. As a decennial count,
the metric has no sampling MOE; disclosure-avoidance, nonsampling, and
allocation-support limitations remain explicit.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC031 passed: {qa['passed']}")


if __name__ == "__main__":
    main()
