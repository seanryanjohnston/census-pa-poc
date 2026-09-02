"""Prove direct, chamber-neutral Census-to-legislative crosswalks for POC028."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

from census_pa_poc.sources import (
    load_pl94_block_population_statewide,
    sha256,
    vsi_zip_member,
)
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

AREA_CRS = "EPSG:5070"
WEIGHT_TOLERANCE = 1e-12
EXPECTED_PARENT_BLOCKS = 336_985
EXPECTED_ATOMIC_FRAGMENTS = 337_039
EXPECTED_POPULATION = 13_002_700

LRC_SOURCE = {
    "source_id": "pa_lrc_2021_release_1b_geography",
    "producer": "Pennsylvania Legislative Reapportionment Commission",
    "product": "2021-10-05 LRC Data Release No. 1b Data Set 1 geography",
    "reference_vintage": "2020",
    "effective_vintage": "2021-10-05",
    "url": (
        "https://www.redistricting.state.pa.us/resources/GISData/Census/2021/"
        "2021-DataSet1-WithoutPrisoner/"
        "2021%20LRC%20Data%20Release%201b%20-%20Geography.zip"
    ),
    "sha256": "14187001c627c6a16bf967415059408c4ef7007d366fd9105b5be30763250e3b",
    "license_access": "Public download; redistribution terms not stated",
    "crs": "EPSG:4269",
    "schema": {
        "format": "ESRI Shapefile",
        "member": "Geography/WP_Blocks.shp",
        "atomic_id": "GEOID20",
        "support_metric": "P0010001",
    },
    "geographic_universe": "Pennsylvania corrected 2020 block fragments",
    "population_universe": "Standard total population, P0010001",
    "relative_path": (
        "data/raw/pa_lrc_2021_release_1b_geography/"
        "2021 LRC Data Release 1b - Geography.zip"
    ),
}

CENSUS_SOURCE = {
    "source_id": "census_2020_pa_pl",
    "producer": "U.S. Census Bureau",
    "product": "2020 Census State Redistricting Data PL 94-171 Summary File",
    "reference_vintage": "2020-04-01",
    "effective_vintage": "2020-04-01",
    "release_date": "2021-08-12",
    "url": (
        "https://www2.census.gov/programs-surveys/decennial/2020/data/"
        "01-Redistricting_File--PL_94-171/Pennsylvania/pa2020.pl.zip"
    ),
    "sha256": "2d33a7dab29c8dd5692bbde203d253e06eebbc44fcbaa96b1caa958d454026ae",
    "license_access": "Public federal data; cite U.S. Census Bureau",
    "crs": None,
    "schema": {
        "format": "pipe-delimited legacy summary file",
        "geography_member": "pageo2020.pl",
        "file01_member": "pa000012020.pl",
        "join": "LOGRECNO",
        "metric": "P0010001",
    },
    "geographic_universe": "2020 Census tabulation blocks in Pennsylvania",
    "population_universe": "Standard total population, P0010001",
    "relative_path": "data/raw/census_2020_pa_pl/pa2020.pl.zip",
}

PLAN_CONFIGS = {
    "pa_house_2021_final": {
        "chamber": "house",
        "expected_districts": 203,
        "plan": {
            "source_id": "pa_house_2021_final",
            "producer": "Pennsylvania Legislative Reapportionment Commission",
            "product": "2021 Final State House district plan SHAPE",
            "reference_vintage": "2021",
            "effective_vintage": "used for 2022-2026 elections",
            "url": (
                "https://www.redistricting.state.pa.us/Resources/GISData/"
                "Districts/Legislative/House/2021-Final/SHAPE/"
                "2022%20LRC-House-Final.zip"
            ),
            "sha256": "11960e83f61416276d46205785adaf5dee1995ab21f05a1b5113b649e6c329f6",
            "license_access": (
                "Public official download; redistribution terms not stated"
            ),
            "crs": "EPSG:4269",
            "schema": {
                "format": "ESRI Shapefile",
                "member": "2022 LRC-House-Final.shp",
                "district_field": "DISTRICT",
            },
            "geographic_universe": "Pennsylvania State House districts",
            "relative_path": (
                "data/raw/pa_house_plans/2021_final/2022 LRC-House-Final.zip"
            ),
        },
        "equivalency": {
            "source_id": "pa_house_2021_final_block_equivalency",
            "producer": "Pennsylvania Legislative Reapportionment Commission",
            "product": "2021 Final State House block equivalency",
            "reference_vintage": "2021",
            "effective_vintage": "used for 2022-2026 elections",
            "url": (
                "https://redistricting.state.pa.us/Resources/GISData/Districts/"
                "Legislative/House/2021-Final/CSV/"
                "2022%20LRC-House-Final.csv"
            ),
            "sha256": "17e11f451196cf0b6253c01386592426f867949b76b189c084f04bbf24a92e15",
            "license_access": (
                "Public official download; redistribution terms not stated"
            ),
            "crs": None,
            "schema": {
                "format": "headerless CSV",
                "columns": ["source_atomic_geoid", "target_district_id"],
            },
            "geographic_universe": "LRC corrected 2020 block fragments",
            "relative_path": (
                "data/raw/pa_house_2021_block_equivalency/2022 LRC-House-Final.csv"
            ),
        },
    },
    "pa_senate_2021_final": {
        "chamber": "senate",
        "expected_districts": 50,
        "plan": {
            "source_id": "pa_senate_2021_final",
            "producer": "Pennsylvania Legislative Reapportionment Commission",
            "product": "2021 Final State Senate district plan SHAPE",
            "reference_vintage": "2021",
            "effective_vintage": "used for 2022-2026 elections",
            "url": (
                "https://www.redistricting.state.pa.us/Resources/GISData/"
                "Districts/Legislative/Senate/2021-Final/SHAPE/"
                "2022%20LRC-Senate-Final.zip"
            ),
            "sha256": "4dcfd5f111ddf7de58484585205ecc5b01631e4a1b20c0745889f741ec137e14",
            "license_access": (
                "Public official download; redistribution terms not stated"
            ),
            "crs": "EPSG:4269",
            "schema": {
                "format": "ESRI Shapefile",
                "member": "2022 LRC-Senate-Final.shp",
                "district_field": "DISTRICT",
            },
            "geographic_universe": "Pennsylvania State Senate districts",
            "relative_path": (
                "data/raw/pa_senate_plans/2021_final/2022 LRC-Senate-Final.zip"
            ),
        },
        "equivalency": {
            "source_id": "pa_senate_2021_final_block_equivalency",
            "producer": "Pennsylvania Legislative Reapportionment Commission",
            "product": "2021 Final State Senate block equivalency",
            "reference_vintage": "2021",
            "effective_vintage": "used for 2022-2026 elections",
            "url": (
                "https://www.redistricting.state.pa.us/Resources/GISData/"
                "Districts/Legislative/Senate/2021-Final/CSV/"
                "2022%20LRC%20Senate%20Final.csv"
            ),
            "sha256": "ff7a79d2da3df2094bebe9ab0f19d91bc2bfec8537f8d07a034b6b0d1b3dfbef",
            "license_access": (
                "Public official download; redistribution terms not stated"
            ),
            "crs": None,
            "schema": {
                "format": "headerless CSV",
                "columns": ["source_atomic_geoid", "target_district_id"],
            },
            "geographic_universe": "LRC corrected 2020 block fragments",
            "relative_path": (
                "data/raw/pa_senate_2021_block_equivalency/2022 LRC Senate Final.csv"
            ),
        },
    },
}


def run(root: Path) -> dict[str, object]:
    """Build and validate direct 2020 House and Senate crosswalk products."""
    root = root.resolve()
    artifact_dir = root / "artifacts/work/poc028"
    processed_dir = root / "data/processed/direct_legislative"

    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    require_manifest_hashes(manifest)

    atoms = load_lrc_atoms(root / LRC_SOURCE["relative_path"])
    population = load_pl94_block_population_statewide(
        root / CENSUS_SOURCE["relative_path"]
    )

    atomic_frames = []
    crosswalk_frames = []
    result_frames = []
    comparison_frames = []
    checks = []
    profiles = []

    for plan_id, config in PLAN_CONFIGS.items():
        plan = load_plan(root, config["plan"])
        equivalency = load_equivalency(root / config["equivalency"]["relative_path"])
        atomic = build_atomic_assignments(atoms, equivalency, plan_id, config)
        atomic = attach_geometry_diagnostics(atomic, atoms, plan)
        crosswalk = build_parent_crosswalk(atomic)
        result = aggregate_population(population, crosswalk)
        comparison = compare_with_atomic_support(result, atomic)
        profile = profile_plan(plan_id, config, plan, atomic, crosswalk)

        atomic_frames.append(atomic)
        crosswalk_frames.append(crosswalk)
        result_frames.append(result)
        comparison_frames.append(comparison)
        profiles.append(profile)
        checks.extend(
            validate_partition(
                plan_id,
                config,
                atoms,
                population,
                plan,
                equivalency,
                atomic,
                crosswalk,
                result,
                comparison,
            )
        )

    atomic_all = pd.concat(atomic_frames, ignore_index=True)
    crosswalk_all = pd.concat(crosswalk_frames, ignore_index=True)
    results_all = pd.concat(result_frames, ignore_index=True)
    comparisons_all = pd.concat(comparison_frames, ignore_index=True)

    writes = {
        "atomic_assignments": write_immutable_parquet(
            atomic_all,
            processed_dir / "lrc_fragment_to_2021_legislative_plan_v1.parquet",
            ["target_chamber", "source_atomic_geoid"],
        ),
        "p001_crosswalk": write_immutable_parquet(
            crosswalk_all,
            processed_dir / "census_2020_p001_to_2021_legislative_plan_v1.parquet",
            ["target_chamber", "source_geography_id", "target_district_id"],
        ),
        "p001_results": write_immutable_parquet(
            results_all,
            processed_dir / "census_2020_p001_legislative_results_v1.parquet",
            ["target_chamber", "target_district_id"],
        ),
        "method_comparison": write_immutable_parquet(
            comparisons_all,
            processed_dir / "census_2020_p001_legislative_comparison_v1.parquet",
            ["target_chamber", "target_district_id"],
        ),
    }
    qa = {
        "task": "POC028",
        "method_id": "lrc_fragment_p001_direct_legislative_v1",
        "assignment_method_id": "lrc_2021_final_block_equivalency_v1",
        "source_geography": "2020 Census parent block",
        "atomic_geography": "LRC corrected 2020 block fragment",
        "weighting_universe": "standard 2020 total population P0010001",
        "zero_support_fallback": "atomic area only when one parent crosses districts",
        "area_crs": AREA_CRS,
        "profiles": profiles,
        "checks": checks,
        "artifact_writes": writes,
        "hashes": {
            "atomic_assignments": logical_frame_hash(
                atomic_all, ["target_chamber", "source_atomic_geoid"]
            ),
            "p001_crosswalk": logical_frame_hash(
                crosswalk_all,
                ["target_chamber", "source_geography_id", "target_district_id"],
            ),
            "p001_results": logical_frame_hash(
                results_all, ["target_chamber", "target_district_id"]
            ),
            "method_comparison": logical_frame_hash(
                comparisons_all, ["target_chamber", "target_district_id"]
            ),
        },
        "uses_precinct_input": False,
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(render_report(qa))
    if not qa["passed"]:
        raise RuntimeError(
            "POC028 QA failed; inspect artifacts/work/poc028/qa_results.json"
        )
    return qa


def load_lrc_atoms(path: Path) -> gpd.GeoDataFrame:
    atoms = gpd.read_file(
        vsi_zip_member(path, "Geography/WP_Blocks.shp"),
        columns=["GEOID20", "P0010001"],
    ).rename(
        columns={
            "GEOID20": "source_atomic_geoid",
            "P0010001": "atomic_support_value",
        }
    )
    atoms["source_atomic_geoid"] = atoms["source_atomic_geoid"].astype("string")
    atoms["source_geography_id"] = atoms["source_atomic_geoid"].str.slice(0, 15)
    atoms["atomic_support_value"] = atoms["atomic_support_value"].astype("int64")
    atoms["atomic_area_square_meters"] = atoms.to_crs(AREA_CRS).geometry.area
    return atoms


def load_plan(root: Path, source: dict[str, object]) -> gpd.GeoDataFrame:
    plan = gpd.read_file(
        vsi_zip_member(root / str(source["relative_path"]), source["schema"]["member"]),
        columns=[source["schema"]["district_field"]],
    )
    district_field = source["schema"]["district_field"]
    plan["target_district_id"] = plan[district_field].astype("int64").astype("string")
    return plan[["target_district_id", "geometry"]]


def load_equivalency(path: Path) -> pd.DataFrame:
    result = pd.read_csv(
        path,
        header=None,
        names=["source_atomic_geoid", "target_district_id"],
        dtype={"source_atomic_geoid": "string", "target_district_id": "string"},
    )
    result["target_district_id"] = (
        result["target_district_id"].astype("int64").astype("string")
    )
    return result.sort_values("source_atomic_geoid").reset_index(drop=True)


def build_atomic_assignments(
    atoms: gpd.GeoDataFrame,
    equivalency: pd.DataFrame,
    plan_id: str,
    config: dict[str, object],
) -> pd.DataFrame:
    """Attach a published plan assignment to each reusable atomic fragment."""
    columns = [
        "source_atomic_geoid",
        "source_geography_id",
        "atomic_support_value",
        "atomic_area_square_meters",
    ]
    result = equivalency.merge(
        atoms[columns],
        on="source_atomic_geoid",
        how="left",
        validate="one_to_one",
    )
    return result.assign(
        source_dataset_id=LRC_SOURCE["source_id"],
        source_reference_vintage="2020",
        target_plan_id=plan_id,
        target_plan_reference_vintage="2021",
        target_chamber=config["chamber"],
        assignment_method_id="lrc_2021_final_block_equivalency_v1",
        assignment_status="assigned",
    )


def attach_geometry_diagnostics(
    atomic: pd.DataFrame,
    atoms: gpd.GeoDataFrame,
    plan: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Compare published assignments with independent representative points."""
    points = atoms[["source_atomic_geoid", "geometry"]].copy()
    points.geometry = shapely.point_on_surface(points.geometry.array)
    candidates = gpd.sjoin(
        points,
        plan[["target_district_id", "geometry"]],
        how="left",
        predicate="within",
    )
    grouped = candidates.groupby("source_atomic_geoid", as_index=False).agg(
        geometry_candidate_count=("target_district_id", "count"),
        geometry_district_ids=(
            "target_district_id",
            lambda values: "|".join(sorted(values.dropna().astype(str).unique())),
        ),
    )
    result = atomic.merge(
        grouped, on="source_atomic_geoid", how="left", validate="one_to_one"
    )
    result["geometry_matches_published"] = result.apply(
        lambda row: (
            row["target_district_id"] in row["geometry_district_ids"].split("|")
        ),
        axis=1,
    )
    return result


def build_parent_crosswalk(atomic: pd.DataFrame) -> pd.DataFrame:
    """Build metric-specific parent weights from reusable atomic assignments."""
    keys = [
        "target_chamber",
        "target_plan_id",
        "target_plan_reference_vintage",
        "source_geography_id",
        "target_district_id",
    ]
    grouped = atomic.groupby(keys, as_index=False).agg(
        district_support_value=("atomic_support_value", "sum"),
        district_atomic_area_square_meters=("atomic_area_square_meters", "sum"),
        atomic_fragment_count=("source_atomic_geoid", "size"),
    )
    parent_keys = [
        "target_chamber",
        "target_plan_id",
        "source_geography_id",
    ]
    grouped["parent_support_value"] = grouped.groupby(parent_keys)[
        "district_support_value"
    ].transform("sum")
    grouped["parent_atomic_area_square_meters"] = grouped.groupby(parent_keys)[
        "district_atomic_area_square_meters"
    ].transform("sum")
    grouped["parent_target_count"] = grouped.groupby(parent_keys)[
        "target_district_id"
    ].transform("nunique")
    grouped["weight"] = grouped.apply(parent_weight, axis=1)
    grouped["weight_method"] = grouped.apply(parent_weight_method, axis=1)
    return grouped.assign(
        source_dataset_id="census_2020_pa_blocks",
        source_reference_vintage="2020",
        source_metric_id="P0010001",
        weighting_universe="standard_2020_total_population_on_lrc_fragments",
        method_id="lrc_fragment_p001_direct_legislative_v1",
        assignment_status="assigned",
    )


def parent_weight(row: pd.Series) -> float:
    if row["parent_target_count"] == 1:
        return 1.0
    if row["parent_support_value"] > 0:
        return float(row["district_support_value"] / row["parent_support_value"])
    return float(
        row["district_atomic_area_square_meters"]
        / row["parent_atomic_area_square_meters"]
    )


def parent_weight_method(row: pd.Series) -> str:
    if row["parent_target_count"] == 1:
        return "single_target_identity"
    if row["parent_support_value"] > 0:
        return "published_fragment_p001"
    return "zero_support_atomic_area_fallback"


def aggregate_population(
    population: pd.DataFrame, crosswalk: pd.DataFrame
) -> pd.DataFrame:
    allocated = crosswalk.merge(
        population[["source_block_geoid", "P0010001"]],
        left_on="source_geography_id",
        right_on="source_block_geoid",
        how="left",
        validate="many_to_one",
    )
    allocated["population"] = allocated["P0010001"] * allocated["weight"]
    keys = ["target_chamber", "target_plan_id", "target_district_id"]
    result = allocated.groupby(keys, as_index=False)["population"].sum()
    return result.assign(
        population_product_id="census_2020_pa_pl",
        population_reference_date="2020-04-01",
        population_release_date="2021-08-12",
        source_metric_id="P0010001",
        population_universe="standard_total_population",
        crosswalk_method_id="lrc_fragment_p001_direct_legislative_v1",
        applicable_general_elections="2022-11-08|2024-11-05|2026-11-03",
    )


def compare_with_atomic_support(
    result: pd.DataFrame, atomic: pd.DataFrame
) -> pd.DataFrame:
    direct = (
        atomic.groupby(
            ["target_chamber", "target_plan_id", "target_district_id"],
            as_index=False,
        )["atomic_support_value"]
        .sum()
        .rename(columns={"atomic_support_value": "published_atomic_population"})
    )
    comparison = result.merge(
        direct,
        on=["target_chamber", "target_plan_id", "target_district_id"],
        how="outer",
        validate="one_to_one",
    )
    comparison["difference"] = (
        comparison["population"] - comparison["published_atomic_population"]
    )
    return comparison[
        [
            "target_chamber",
            "target_plan_id",
            "target_district_id",
            "population",
            "published_atomic_population",
            "difference",
        ]
    ]


def profile_plan(
    plan_id: str,
    config: dict[str, object],
    plan: gpd.GeoDataFrame,
    atomic: pd.DataFrame,
    crosswalk: pd.DataFrame,
) -> dict[str, object]:
    return {
        "target_plan_id": plan_id,
        "target_chamber": config["chamber"],
        "plan_rows": len(plan),
        "district_count": int(plan["target_district_id"].nunique()),
        "plan_crs": plan.crs.to_string(),
        "invalid_plan_geometry_count": int((~plan.geometry.is_valid).sum()),
        "atomic_assignment_rows": len(atomic),
        "geometry_mismatch_count": int((~atomic["geometry_matches_published"]).sum()),
        "parent_crosswalk_rows": len(crosswalk),
        "split_parent_count": int(
            crosswalk.groupby("source_geography_id")["target_district_id"]
            .nunique()
            .gt(1)
            .sum()
        ),
        "zero_support_area_fallback_rows": int(
            crosswalk["weight_method"].eq("zero_support_atomic_area_fallback").sum()
        ),
    }


def validate_partition(
    plan_id: str,
    config: dict[str, object],
    atoms: gpd.GeoDataFrame,
    population: pd.DataFrame,
    plan: gpd.GeoDataFrame,
    equivalency: pd.DataFrame,
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
    atom_parent_support = atoms.groupby("source_geography_id")[
        "atomic_support_value"
    ].sum()
    population_support = population.set_index("source_block_geoid")["P0010001"]
    parent_difference = atom_parent_support.sub(population_support).abs()
    forbidden_columns = [column for column in crosswalk if "precinct" in column]
    return [
        check(
            f"{prefix}:plan_rows", len(plan) == config["expected_districts"], len(plan)
        ),
        check(
            f"{prefix}:plan_districts",
            set(plan["target_district_id"]) == expected_districts,
            int(plan["target_district_id"].nunique()),
        ),
        check(
            f"{prefix}:plan_crs",
            plan.crs.to_string() == "EPSG:4269",
            plan.crs.to_string(),
        ),
        check(
            f"{prefix}:plan_geometry_valid",
            bool(plan.geometry.is_valid.all()),
            int((~plan.geometry.is_valid).sum()),
        ),
        check(
            f"{prefix}:equivalency_rows",
            len(equivalency) == EXPECTED_ATOMIC_FRAGMENTS,
            len(equivalency),
        ),
        check(
            f"{prefix}:equivalency_unique",
            equivalency["source_atomic_geoid"].is_unique,
            int(equivalency["source_atomic_geoid"].nunique()),
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
            f"{prefix}:equivalency_districts",
            set(equivalency["target_district_id"]) == expected_districts,
            int(equivalency["target_district_id"].nunique()),
        ),
        check(
            f"{prefix}:geometry_matches_published",
            bool(atomic["geometry_matches_published"].all()),
            int((~atomic["geometry_matches_published"]).sum()),
        ),
        check(
            f"{prefix}:parent_coverage",
            crosswalk["source_geography_id"].nunique() == EXPECTED_PARENT_BLOCKS,
            int(crosswalk["source_geography_id"].nunique()),
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
            f"{prefix}:parent_support_matches_census",
            bool(parent_difference.eq(0).all()),
            int(parent_difference.ne(0).sum()),
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
            f"{prefix}:population_conserved",
            abs(float(result["population"].sum()) - EXPECTED_POPULATION)
            <= WEIGHT_TOLERANCE,
            float(result["population"].sum()),
        ),
        check(
            f"{prefix}:published_method_exact",
            bool(comparison["difference"].abs().le(WEIGHT_TOLERANCE).all()),
            float(comparison["difference"].abs().max()),
        ),
        check(
            f"{prefix}:plan_identity",
            atomic["target_plan_id"].eq(plan_id).all()
            and crosswalk["target_plan_id"].eq(plan_id).all(),
            plan_id,
        ),
    ]


def build_manifest(root: Path) -> dict[str, object]:
    sources = [CENSUS_SOURCE, LRC_SOURCE]
    for config in PLAN_CONFIGS.values():
        sources.extend([config["plan"], config["equivalency"]])
    return {
        "manifest_version": "1.0.0",
        "created_timestamp": datetime.now(UTC).isoformat(),
        "sources": [manifest_entry(root, source) for source in sources],
    }


def manifest_entry(root: Path, source: dict[str, object]) -> dict[str, object]:
    path = root / str(source["relative_path"])
    result = dict(source)
    result["retrieval_timestamp"] = datetime.fromtimestamp(
        path.stat().st_mtime, UTC
    ).isoformat()
    result["size_bytes"] = path.stat().st_size
    result["observed_sha256"] = sha256(path)
    return result


def require_manifest_hashes(manifest: dict[str, object]) -> None:
    failures = [
        source["source_id"]
        for source in manifest["sources"]
        if source["sha256"] != source["observed_sha256"]
    ]
    if failures:
        raise ValueError(f"POC028 source checksum mismatch: {failures}")


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(qa: dict[str, object]) -> str:
    status = "PASS" if qa["passed"] else "FAIL"
    profile_lines = "\n".join(
        (
            f"- {profile['target_chamber']}: {profile['district_count']} districts, "
            f"{profile['parent_crosswalk_rows']:,} parent/district rows, "
            f"{profile['split_parent_count']} split parent blocks, "
            f"{profile['geometry_mismatch_count']} geometry mismatches"
        )
        for profile in qa["profiles"]
    )
    return f"""# POC028 direct legislative crosswalk proof

Status: **{status}**

The proof assigns LRC corrected 2020 atomic fragments directly to the official
2021 Final House and Senate plans, then derives a separately versioned
`P0010001` parent-block crosswalk. No precinct artifact or precinct identifier is
an input.

{profile_lines}

Both chambers conserve {EXPECTED_POPULATION:,} standard Census residents. The
published equivalencies agree with independent plan-polygon representative-point
diagnostics for every atomic fragment. Atomic assignment is reusable; the
`P0010001` weights are explicitly metric-specific and must not be relabeled for
another variable without a new support proof.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC028 passed: {qa['passed']}")


if __name__ == "__main__":
    main()
