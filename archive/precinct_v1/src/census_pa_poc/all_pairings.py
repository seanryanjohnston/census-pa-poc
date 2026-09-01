"""Execute and index every POC016 population/election pairing."""

from __future__ import annotations

import argparse
import gc
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from census_pa_poc.fixed_geography import load_lrc_blocks
from census_pa_poc.senate_overlay import logical_geoframe_hash
from census_pa_poc.sources import (
    load_1990_2000_block_relationship,
    load_1990_stf1b_block_population,
    load_1990_tiger_blocks_and_faces,
    load_2000_2010_block_relationship,
    load_2000_census_blocks,
    load_2000_pl94_block_population,
    load_2010_2020_block_relationship,
    load_2010_census_blocks,
    load_2010_pl94_block_population,
    load_acs5_block_group_population,
    load_pl94_block_population_statewide,
    sha256,
    vsi_zip_member,
)
from census_pa_poc.statewide_1990 import (
    RELATIONSHIP_METHOD as METHOD_1990,
)
from census_pa_poc.statewide_1990 import (
    SOURCES as SOURCES_1990,
)
from census_pa_poc.statewide_1990 import (
    add_zero_population_exceptions as add_1990_exceptions,
)
from census_pa_poc.statewide_1990 import (
    apply_crosswalk_metadata as add_1990_metadata,
)
from census_pa_poc.statewide_1990 import (
    build_2000_atomic_bridge,
    build_tiger_face_weights,
)
from census_pa_poc.statewide_1990 import (
    build_relationship_atomic_crosswalk as build_1990_relationship_crosswalk,
)
from census_pa_poc.statewide_1990 import (
    normalize_crosswalk_dtypes as normalize_1990_crosswalk,
)
from census_pa_poc.statewide_2000 import (
    RELATIONSHIP_METHOD as METHOD_2000,
)
from census_pa_poc.statewide_2000 import (
    SOURCES as SOURCES_2000,
)
from census_pa_poc.statewide_2000 import (
    add_zero_population_exceptions as add_2000_exceptions,
)
from census_pa_poc.statewide_2000 import (
    apply_crosswalk_metadata as add_2000_metadata,
)
from census_pa_poc.statewide_2000 import (
    build_2010_atomic_crosswalk,
)
from census_pa_poc.statewide_2000 import (
    build_relationship_atomic_crosswalk as build_2000_relationship_crosswalk,
)
from census_pa_poc.statewide_2000 import (
    normalize_crosswalk_dtypes as normalize_2000_crosswalk,
)
from census_pa_poc.statewide_2010 import (
    SOURCES as SOURCES_2010,
)
from census_pa_poc.statewide_2010 import (
    add_zero_population_exceptions as add_2010_exceptions,
)
from census_pa_poc.statewide_2010 import (
    build_2020_atomic_crosswalk,
)
from census_pa_poc.statewide_2010 import (
    build_relationship_atomic_crosswalk as build_2010_relationship_crosswalk,
)
from census_pa_poc.statewide_2010 import (
    normalize_crosswalk_dtypes as normalize_2010_crosswalk,
)
from census_pa_poc.statewide_acs5_2015 import build_simple_area_crosswalk
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

WEIGHT_TOLERANCE = 1e-12
RESULT_TOLERANCE = 1e-6
PRECINCT_PLAN_INVARIANCE_TOLERANCE = 1e-3
FIXED_TARGET_ID = "pa_lrc_2021_release_1b_geography"
FIXED_TARGET_VINTAGE = "2021-10-05"
NO_PRODUCT_PAIRING_ID = "pa_general_1990__no_available_product"

PLAN_VINTAGES = {
    "pa_senate_1991_final": "1991",
    "pa_senate_2001_final": "2001",
    "pa_senate_2012_revised_final": "2012",
    "pa_senate_2021_final": "2021",
}
PLAN_SLUGS = {
    "pa_senate_1991_final": "1991_final",
    "pa_senate_2001_final": "2001_final",
    "pa_senate_2012_revised_final": "2012_revised_final",
    "pa_senate_2021_final": "2021_final",
}
PLAN_PATHS = {
    plan_id: (
        f"data/processed/senate_overlays/{plan_id}_fixed_precinct_overlay_v3.parquet"
    )
    for plan_id in PLAN_VINTAGES
}

DECENNIAL_METHODS = {
    "dec_1990": METHOD_1990,
    "dec_2000": METHOD_2000,
    "dec_2010": "relationship_atomic_area_2010_v1",
    "dec_2020": "lrc_published_split_v1",
}
DECENNIAL_LIMITS = {
    "dec_1990": (
        "Geometry-only same-topology TIGER face area allocation; official "
        "relationship files contain pairs but no weights."
    ),
    "dec_2000": (
        "Geometry-only relationship/atomic-area allocation; area is not "
        "observed within-block population."
    ),
    "dec_2010": (
        "Geometry-only relationship/atomic-area allocation; area is not "
        "observed within-block population."
    ),
    "dec_2020": (
        "Published LRC corrected-fragment population assignment on the fixed target."
    ),
}

ACS_METHODS = {
    2009: "simple_atomic_area_acs5_2009_v1",
    2010: "simple_atomic_area_acs5_2010_v1",
    2011: "census2010_population_atomic_acs5_2010_geography_v1",
    2020: "census2010_population_atomic_acs5_2020_geography_v1",
}
ACS_LIMIT_SIMPLE = (
    "Simple EPSG:5070 block-group/atomic area allocation; area is a weak "
    "population support model. Target MOEs use weighted-source RSS and omit "
    "covariance and allocation-weight uncertainty."
)
ACS_LIMIT_INFORMED = (
    "2010 Census population support predates the ACS period but may be stale; "
    "zero-support groups use typed simple-area fallback. Target MOEs use "
    "weighted-source RSS and omit covariance and allocation-weight uncertainty."
)


def run(root: Path) -> dict[str, object]:
    """Run 39 unique product-plan allocations and index 114 election pairings."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc016"
    processed_dir = root / "data/processed/poc016"
    crosswalk_dir = processed_dir / "crosswalks"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    crosswalk_dir.mkdir(parents=True, exist_ok=True)

    availability = pd.read_csv(
        root / "mappings/population_election_availability_v1.csv", dtype="string"
    )
    candidates = availability[availability["candidate_for_poc016"].eq("true")].copy()
    product_plans = candidates[
        ["product_id", "product_family", "senate_plan_id"]
    ].drop_duplicates()
    plan_atoms = {plan: load_plan_atoms(root, plan) for plan in PLAN_VINTAGES}

    manifest_inputs = build_input_manifest(root, plan_atoms)
    write_json(artifact_dir / "input_manifest.json", manifest_inputs)

    crosswalk_index: dict[tuple[str, str], dict[str, object]] = {}
    precinct_frames: list[pd.DataFrame] = []
    senate_frames: list[pd.DataFrame] = []
    diagnostics: dict[str, object] = {}

    decennial = execute_decennial_products(
        root,
        product_plans[~product_plans["product_id"].str.startswith("acs5_")],
        plan_atoms,
        crosswalk_dir,
    )
    crosswalk_index.update(decennial["crosswalk_index"])
    precinct_frames.extend(decennial["precinct_results"])
    senate_frames.extend(decennial["senate_results"])
    diagnostics["decennial"] = decennial["diagnostics"]
    gc.collect()

    acs = execute_acs_products(
        root,
        product_plans[product_plans["product_id"].str.startswith("acs5_")],
        plan_atoms,
        crosswalk_dir,
    )
    crosswalk_index.update(acs["crosswalk_index"])
    precinct_frames.extend(acs["precinct_results"])
    senate_frames.extend(acs["senate_results"])
    diagnostics["acs"] = acs["diagnostics"]

    precinct_results = normalize_results(pd.concat(precinct_frames, ignore_index=True))
    senate_results = normalize_results(pd.concat(senate_frames, ignore_index=True))
    precinct_path = processed_dir / "fixed_precinct_population_products_v1.parquet"
    senate_path = processed_dir / "senate_population_products_v1.parquet"
    precinct_write = write_immutable_parquet(
        precinct_results,
        precinct_path,
        ["population_product_id", "senate_plan_id", "target_precinct_geoid"],
    )
    senate_write = write_immutable_parquet(
        senate_results,
        senate_path,
        ["population_product_id", "senate_plan_id", "senate_district"],
    )
    result_hashes = {
        "fixed_precinct": logical_frame_hash(
            precinct_results,
            ["population_product_id", "senate_plan_id", "target_precinct_geoid"],
        ),
        "senate": logical_frame_hash(
            senate_results,
            ["population_product_id", "senate_plan_id", "senate_district"],
        ),
    }

    execution_manifest = build_execution_manifest(
        candidates,
        crosswalk_index,
        precinct_path.relative_to(root).as_posix(),
        senate_path.relative_to(root).as_posix(),
        result_hashes,
    )
    manifest_path = root / "mappings/population_election_execution_v1.csv"
    manifest_status = write_immutable_csv(
        execution_manifest,
        manifest_path,
        ["election_date", "pairing_id"],
    )
    manifest_hash = logical_frame_hash(
        execution_manifest, ["election_date", "pairing_id"]
    )

    source_totals = load_source_totals(root)
    checks = build_checks(
        availability,
        candidates,
        product_plans,
        execution_manifest,
        crosswalk_index,
        precinct_results,
        senate_results,
        source_totals,
    )
    qa = {
        "task": "POC016",
        "candidate_pairings": len(candidates),
        "unique_product_plan_allocations": len(product_plans),
        "zero_product_elections": ["pa_general_1990"],
        "fixed_target_id": FIXED_TARGET_ID,
        "crosswalk_weight_tolerance": WEIGHT_TOLERANCE,
        "result_tolerance": RESULT_TOLERANCE,
        "precinct_plan_invariance_tolerance": PRECINCT_PLAN_INVARIANCE_TOLERANCE,
        "diagnostics": diagnostics,
        "checks": checks,
        "artifact_writes": {
            "execution_manifest": manifest_status,
            "fixed_precinct_results": precinct_write,
            "senate_results": senate_write,
        },
        "hashes": {
            "execution_manifest": manifest_hash,
            **result_hashes,
        },
        "nearest_assignment_count": 0,
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(render_report(qa))
    if not qa["passed"]:
        raise RuntimeError("POC016 QA failed; inspect artifacts/poc016/qa_results.json")
    return qa


def load_plan_atoms(root: Path, plan_id: str) -> gpd.GeoDataFrame:
    return gpd.read_parquet(root / PLAN_PATHS[plan_id])[
        ["target_precinct_geoid", "senate_district", "geometry"]
    ]


def execute_decennial_products(
    root: Path,
    product_plans: pd.DataFrame,
    plan_atoms: dict[str, gpd.GeoDataFrame],
    crosswalk_dir: Path,
) -> dict[str, object]:
    index = {}
    precinct_results = []
    senate_results = []
    diagnostics = {}
    for product_id, group in product_plans.groupby("product_id", sort=True):
        plans = sorted(group["senate_plan_id"].tolist())
        result = execute_decennial_product(
            root, product_id, plans, plan_atoms, crosswalk_dir
        )
        index.update(result["crosswalk_index"])
        precinct_results.extend(result["precinct_results"])
        senate_results.extend(result["senate_results"])
        diagnostics[product_id] = result["diagnostics"]
        gc.collect()
    return {
        "crosswalk_index": index,
        "precinct_results": precinct_results,
        "senate_results": senate_results,
        "diagnostics": diagnostics,
    }


def execute_decennial_product(
    root: Path,
    product_id: str,
    plans: list[str],
    plan_atoms: dict[str, gpd.GeoDataFrame],
    crosswalk_dir: Path,
) -> dict[str, object]:
    if product_id == "dec_1990":
        return execute_1990(root, plans, plan_atoms, crosswalk_dir)
    if product_id == "dec_2000":
        return execute_2000(root, plans, plan_atoms, crosswalk_dir)
    if product_id == "dec_2010":
        return execute_2010(root, plans, plan_atoms, crosswalk_dir)
    if product_id == "dec_2020":
        return execute_2020(root, plans, crosswalk_dir)
    raise ValueError(f"Unknown decennial product: {product_id}")


def execute_1990(
    root: Path,
    plans: list[str],
    plan_atoms: dict[str, gpd.GeoDataFrame],
    crosswalk_dir: Path,
) -> dict[str, object]:
    population = load_1990_stf1b_block_population(
        root / SOURCES_1990["census_population"]["relative_path"]
    )
    published = load_1990_2000_block_relationship(
        root / SOURCES_1990["published_relationship_collection"]["relative_path"]
    )
    blocks_all, faces = load_1990_tiger_blocks_and_faces(
        root / SOURCES_1990["tiger_collection"]["relative_path"]
    )
    blocks = blocks_all[
        blocks_all["source_block_geoid"].isin(population["source_block_geoid"])
    ].copy()
    source_to_2000, source_diagnostics = build_tiger_face_weights(
        blocks, faces, population, published
    )
    blocks_2000 = load_2000_census_blocks(
        root / SOURCES_1990["census_2000_blocks"]["relative_path"]
    )
    return execute_relationship_plans(
        root,
        "dec_1990",
        population,
        plans,
        plan_atoms,
        crosswalk_dir,
        lambda atoms: build_1990_for_plan(
            source_to_2000, blocks_2000, population, atoms
        ),
        {"source_relationship": source_diagnostics},
    )


def build_1990_for_plan(
    source_to_2000: pd.DataFrame,
    blocks_2000: gpd.GeoDataFrame,
    population: pd.DataFrame,
    atoms: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    target, target_diagnostics = build_2000_atomic_bridge(blocks_2000, atoms)
    crosswalk, diagnostics = build_1990_relationship_crosswalk(source_to_2000, target)
    crosswalk = add_1990_metadata(crosswalk, METHOD_1990)
    crosswalk = add_1990_exceptions(crosswalk, population)
    diagnostics["target_atomic"] = target_diagnostics
    return normalize_1990_crosswalk(crosswalk), diagnostics


def execute_2000(
    root: Path,
    plans: list[str],
    plan_atoms: dict[str, gpd.GeoDataFrame],
    crosswalk_dir: Path,
) -> dict[str, object]:
    population = load_2000_pl94_block_population(
        root / SOURCES_2000["census_population_geography"]["relative_path"],
        root / SOURCES_2000["census_population_file01"]["relative_path"],
    )
    relationship = load_2000_2010_block_relationship(
        root / SOURCES_2000["block_relationship"]["relative_path"]
    )
    blocks_2010 = load_2010_census_blocks(
        root / SOURCES_2000["census_2010_blocks"]["relative_path"]
    )
    return execute_relationship_plans(
        root,
        "dec_2000",
        population,
        plans,
        plan_atoms,
        crosswalk_dir,
        lambda atoms: build_2000_for_plan(relationship, blocks_2010, population, atoms),
        {},
    )


def build_2000_for_plan(
    relationship: pd.DataFrame,
    blocks_2010: gpd.GeoDataFrame,
    population: pd.DataFrame,
    atoms: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    target, target_diagnostics = build_2010_atomic_crosswalk(blocks_2010, atoms)
    crosswalk, diagnostics = build_2000_relationship_crosswalk(
        relationship, target, population
    )
    crosswalk = add_2000_metadata(crosswalk, METHOD_2000)
    crosswalk = add_2000_exceptions(crosswalk, population)
    crosswalk["intersection_area_square_meters"] = pd.NA
    diagnostics["target_atomic"] = target_diagnostics
    return normalize_2000_crosswalk(crosswalk), diagnostics


def execute_2010(
    root: Path,
    plans: list[str],
    plan_atoms: dict[str, gpd.GeoDataFrame],
    crosswalk_dir: Path,
) -> dict[str, object]:
    population = load_2010_pl94_block_population(
        root / SOURCES_2010["census_population"]["relative_path"]
    )
    relationship = load_2010_2020_block_relationship(
        root / SOURCES_2010["block_relationship"]["relative_path"]
    )
    lrc_blocks = load_lrc_blocks(root / SOURCES_2010["lrc_geography"]["relative_path"])
    return execute_relationship_plans(
        root,
        "dec_2010",
        population,
        plans,
        plan_atoms,
        crosswalk_dir,
        lambda atoms: build_2010_for_plan(relationship, lrc_blocks, population, atoms),
        {},
    )


def build_2010_for_plan(
    relationship: pd.DataFrame,
    lrc_blocks: gpd.GeoDataFrame,
    population: pd.DataFrame,
    atoms: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    target, target_diagnostics = build_2020_atomic_crosswalk(lrc_blocks, atoms)
    crosswalk, diagnostics = build_2010_relationship_crosswalk(
        relationship, target, set(population["source_block_geoid"])
    )
    crosswalk = add_2010_exceptions(crosswalk, population)
    crosswalk["intersection_area_square_meters"] = pd.NA
    diagnostics["target_atomic"] = target_diagnostics
    return normalize_2010_crosswalk(crosswalk), diagnostics


def execute_relationship_plans(
    root: Path,
    product_id: str,
    population: pd.DataFrame,
    plans: list[str],
    plan_atoms: dict[str, gpd.GeoDataFrame],
    crosswalk_dir: Path,
    builder,
    base_diagnostics: dict[str, object],
) -> dict[str, object]:
    index = {}
    precinct_results = []
    senate_results = []
    diagnostics = dict(base_diagnostics)
    for plan_id in plans:
        path = crosswalk_path(crosswalk_dir, product_id, plan_id)
        if path.exists():
            crosswalk = pd.read_parquet(path)
            plan_diagnostics = {"crosswalk_artifact": "reused_existing"}
        else:
            crosswalk, plan_diagnostics = builder(plan_atoms[plan_id])
            crosswalk = set_plan_metadata(crosswalk, plan_id)
            write_immutable_parquet(
                crosswalk,
                path,
                ["source_block_geoid", "target_precinct_geoid", "senate_district"],
            )
        validate_decennial_crosswalk(crosswalk, population)
        precinct, senate = aggregate_decennial(population, crosswalk)
        precinct_results.append(
            add_result_metadata(precinct, product_id, plan_id, "fixed_precinct")
        )
        senate_results.append(
            add_result_metadata(senate, product_id, plan_id, "state_senate_district")
        )
        index[(product_id, plan_id)] = crosswalk_entry(root, path, crosswalk)
        diagnostics[plan_id] = plan_diagnostics
    return {
        "crosswalk_index": index,
        "precinct_results": precinct_results,
        "senate_results": senate_results,
        "diagnostics": diagnostics,
    }


def execute_2020(
    root: Path, plans: list[str], crosswalk_dir: Path
) -> dict[str, object]:
    if plans != ["pa_senate_2021_final"]:
        raise ValueError(f"Unexpected 2020 plans: {plans}")
    crosswalk_path_value = (
        root / "data/processed/statewide_2020/"
        "block_to_fixed_precinct_lrc_published_split_v1.parquet"
    )
    crosswalk = pd.read_parquet(crosswalk_path_value)
    precinct_source = pd.read_parquet(
        root / "data/processed/statewide_2020/fixed_precinct_population_2020_v1.parquet"
    )
    senate_source = pd.read_parquet(
        root / "data/processed/statewide_2020/"
        "senate_population_2020_2021_plan_v1.parquet"
    )
    precinct = precinct_source[["target_precinct_geoid", "population"]].copy()
    senate = senate_source[
        senate_source["method_id"].eq("lrc_senate_block_equivalency_v1")
    ][["senate_district", "population"]].copy()
    plan_id = plans[0]
    return {
        "crosswalk_index": {
            ("dec_2020", plan_id): crosswalk_entry(
                root, crosswalk_path_value, crosswalk
            )
        },
        "precinct_results": [
            add_result_metadata(precinct, "dec_2020", plan_id, "fixed_precinct")
        ],
        "senate_results": [
            add_result_metadata(senate, "dec_2020", plan_id, "state_senate_district")
        ],
        "diagnostics": {plan_id: {"accepted_poc010_artifacts": "reused"}},
    }


def execute_acs_products(
    root: Path,
    product_plans: pd.DataFrame,
    plan_atoms: dict[str, gpd.GeoDataFrame],
    crosswalk_dir: Path,
) -> dict[str, object]:
    needed = set(map(tuple, product_plans[["product_id", "senate_plan_id"]].values))
    crosswalks, support_diagnostics = build_acs_crosswalks(
        root, needed, plan_atoms, crosswalk_dir
    )
    index = {}
    precinct_results = []
    senate_results = []
    product_diagnostics = {}
    for product_id, plan_id in sorted(needed):
        year = int(product_id.rsplit("_", 1)[1])
        population = load_acs5_block_group_population(
            year, root / f"data/raw/acs5_all_pa/{year}"
        )
        crosswalk_key = acs_crosswalk_key(year, plan_id)
        crosswalk = crosswalks[crosswalk_key]
        entry = support_diagnostics[crosswalk_key]["entry"]
        if product_id == "acs5_2015" and plan_id == "pa_senate_2012_revised_final":
            accepted_path = (
                root / "data/processed/statewide_acs5_2015/"
                "block_group_to_fixed_precinct_2012_senate_v1.parquet"
            )
            crosswalk = pd.read_parquet(accepted_path)
            crosswalk = crosswalk[
                crosswalk["method_id"].eq("census2010_population_atomic_acs5_2015_v1")
            ].reset_index(drop=True)
            entry = crosswalk_entry(root, accepted_path, crosswalk)
        validate_acs_crosswalk(crosswalk, population)
        precinct, senate = aggregate_acs(population, crosswalk)
        precinct_results.append(
            add_result_metadata(precinct, product_id, plan_id, "fixed_precinct")
        )
        senate_results.append(
            add_result_metadata(senate, product_id, plan_id, "state_senate_district")
        )
        index[(product_id, plan_id)] = entry
        product_diagnostics[f"{product_id}__{plan_id}"] = {
            "source_block_groups": len(population),
            "estimate": int(population["B01003_001E"].sum()),
            "source_moe_linear_sum": int(population["B01003_001M"].sum()),
            "crosswalk_id": entry["crosswalk_id"],
        }
    return {
        "crosswalk_index": index,
        "precinct_results": precinct_results,
        "senate_results": senate_results,
        "diagnostics": {
            "support_crosswalks": {
                f"{key[0]}__{key[1]}": value
                for key, value in support_diagnostics.items()
            },
            "products": product_diagnostics,
        },
    }


def build_acs_crosswalks(
    root: Path,
    needed: set[tuple[str, str]],
    plan_atoms: dict[str, gpd.GeoDataFrame],
    crosswalk_dir: Path,
) -> tuple[dict[tuple[str, str], pd.DataFrame], dict[tuple[str, str], dict]]:
    keys = {
        acs_crosswalk_key(int(product.rsplit("_", 1)[1]), plan)
        for product, plan in needed
    }
    block_groups = {
        "2009": load_block_groups(
            root / "data/raw/census_2009_pa_block_groups/tl_2009_42_bg00.zip",
            "tl_2009_42_bg00.shp",
            "BKGPIDFP00",
        ),
        "2010": load_block_groups(
            root / "data/raw/census_2010_pa_block_groups/tl_2010_42_bg10.zip",
            "tl_2010_42_bg10.shp",
            "GEOID10",
        ),
        "2020": load_block_groups(
            root / "data/raw/census_2020_pa_block_groups/tl_2020_42_bg.zip",
            "tl_2020_42_bg.shp",
            "GEOID",
        ),
    }
    simple_cache = {}
    crosswalks = {}
    diagnostics = {}
    for key in sorted(keys):
        regime, plan_id = key
        path = crosswalk_path(crosswalk_dir, f"acs_{regime}", plan_id)
        if path.exists():
            crosswalk = pd.read_parquet(path)
            detail = {"crosswalk_artifact": "reused_existing"}
        else:
            if regime in {"simple_2009", "simple_2010"}:
                vintage = regime.rsplit("_", 1)[1]
                crosswalk, detail = build_simple_acs_crosswalk(
                    block_groups[vintage], plan_atoms[plan_id], int(vintage), plan_id
                )
            elif regime == "population_2010_bg":
                simple = get_simple_crosswalk(
                    simple_cache,
                    block_groups["2010"],
                    plan_atoms[plan_id],
                    2010,
                    plan_id,
                )
                crosswalk, detail = build_2010_population_support_2010_bg(
                    root, plan_atoms[plan_id], simple, plan_id
                )
            elif regime == "population_2020_bg":
                simple = get_simple_crosswalk(
                    simple_cache,
                    block_groups["2020"],
                    plan_atoms[plan_id],
                    2020,
                    plan_id,
                )
                crosswalk, detail = build_2010_population_support_2020_bg(
                    root, plan_atoms[plan_id], simple, plan_id
                )
            else:
                raise ValueError(f"Unknown ACS crosswalk regime: {regime}")
            write_immutable_parquet(
                crosswalk,
                path,
                [
                    "source_block_group_geoid",
                    "target_precinct_geoid",
                    "senate_district",
                ],
            )
        entry = crosswalk_entry(root, path, crosswalk)
        detail["entry"] = entry
        crosswalks[key] = crosswalk
        diagnostics[key] = detail
    return crosswalks, diagnostics


def acs_crosswalk_key(year: int, plan_id: str) -> tuple[str, str]:
    if year == 2009:
        return "simple_2009", plan_id
    if year == 2010:
        return "simple_2010", plan_id
    if 2011 <= year <= 2019:
        return "population_2010_bg", plan_id
    if 2020 <= year <= 2024:
        return "population_2020_bg", plan_id
    raise ValueError(year)


def load_block_groups(path: Path, member: str, id_column: str) -> gpd.GeoDataFrame:
    frame = gpd.read_file(vsi_zip_member(path, member))[[id_column, "geometry"]]
    return frame.rename(columns={id_column: "GEOID"})


def get_simple_crosswalk(
    cache: dict[tuple[int, str], pd.DataFrame],
    block_groups: gpd.GeoDataFrame,
    atoms: gpd.GeoDataFrame,
    vintage: int,
    plan_id: str,
) -> pd.DataFrame:
    key = (vintage, plan_id)
    if key not in cache:
        cache[key] = build_simple_acs_crosswalk(block_groups, atoms, vintage, plan_id)[
            0
        ]
    return cache[key]


def build_simple_acs_crosswalk(
    block_groups: gpd.GeoDataFrame,
    atoms: gpd.GeoDataFrame,
    vintage: int,
    plan_id: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    crosswalk, diagnostics = build_simple_area_crosswalk(block_groups, atoms)
    method_id = ACS_METHODS[2009 if vintage == 2009 else 2010]
    crosswalk = set_acs_metadata(crosswalk, method_id, plan_id)
    return normalize_acs_crosswalk(crosswalk), diagnostics


def build_2010_population_support_2010_bg(
    root: Path,
    atoms: gpd.GeoDataFrame,
    simple: pd.DataFrame,
    plan_id: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    population, related, diagnostics = build_2010_atomic_support(root, atoms)
    assigned = related[related["assignment_status"].eq("assigned")].merge(
        population, on="source_block_geoid", validate="many_to_one"
    )
    assigned["source_block_group_geoid"] = assigned["source_block_geoid"].str.slice(
        0, 12
    )
    assigned["raw_support_value"] = assigned["P0010001"] * assigned["weight"]
    grouped = assigned.groupby(
        ["source_block_group_geoid", "target_precinct_geoid", "senate_district"],
        as_index=False,
    )["raw_support_value"].sum()
    crosswalk, fallback = normalize_support_with_fallback(grouped, simple)
    diagnostics["zero_support_fallback_block_groups"] = fallback
    crosswalk = set_acs_metadata(crosswalk, ACS_METHODS[2011], plan_id)
    return normalize_acs_crosswalk(crosswalk), diagnostics


def build_2010_population_support_2020_bg(
    root: Path,
    atoms: gpd.GeoDataFrame,
    simple: pd.DataFrame,
    plan_id: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    population = load_2010_pl94_block_population(
        root / SOURCES_2010["census_population"]["relative_path"]
    )
    relationship = load_2010_2020_block_relationship(
        root / SOURCES_2010["block_relationship"]["relative_path"]
    )
    lrc_blocks = load_lrc_blocks(root / SOURCES_2010["lrc_geography"]["relative_path"])
    target, target_diagnostics = build_2020_atomic_crosswalk(lrc_blocks, atoms)
    relation = relationship[
        [
            "source_block_geoid",
            "target_2020_block_geoid",
            "AREALAND_INT",
            "AREAWATER_INT",
        ]
    ].copy()
    relation["relationship_area"] = relation["AREALAND_INT"] + relation["AREAWATER_INT"]
    totals = relation.groupby("source_block_geoid")["relationship_area"].transform(
        "sum"
    )
    relation["relationship_weight"] = relation["relationship_area"] / totals
    support = relation.merge(
        population, on="source_block_geoid", validate="many_to_one"
    )
    support = support.merge(
        target, on="target_2020_block_geoid", validate="many_to_many"
    )
    support["source_block_group_geoid"] = support["target_2020_block_geoid"].str.slice(
        0, 12
    )
    support["raw_support_value"] = (
        support["P0010001"]
        * support["relationship_weight"]
        * support["target_atomic_weight"]
    )
    grouped = support.groupby(
        ["source_block_group_geoid", "target_precinct_geoid", "senate_district"],
        as_index=False,
    )["raw_support_value"].sum()
    crosswalk, fallback = normalize_support_with_fallback(grouped, simple)
    crosswalk = set_acs_metadata(crosswalk, ACS_METHODS[2020], plan_id)
    return normalize_acs_crosswalk(crosswalk), {
        "target_2020_atomic": target_diagnostics,
        "zero_support_fallback_block_groups": fallback,
        "nearest_assignment_count": 0,
    }


def build_2010_atomic_support(
    root: Path, atoms: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    population = load_2010_pl94_block_population(
        root / SOURCES_2010["census_population"]["relative_path"]
    )
    relationship = load_2010_2020_block_relationship(
        root / SOURCES_2010["block_relationship"]["relative_path"]
    )
    lrc_blocks = load_lrc_blocks(root / SOURCES_2010["lrc_geography"]["relative_path"])
    target, target_diagnostics = build_2020_atomic_crosswalk(lrc_blocks, atoms)
    crosswalk, diagnostics = build_2010_relationship_crosswalk(
        relationship, target, set(population["source_block_geoid"])
    )
    crosswalk = add_2010_exceptions(crosswalk, population)
    diagnostics["target_2020_atomic"] = target_diagnostics
    return population, crosswalk, diagnostics


def normalize_support_with_fallback(
    grouped: pd.DataFrame, simple: pd.DataFrame
) -> tuple[pd.DataFrame, int]:
    totals = grouped.groupby("source_block_group_geoid")["raw_support_value"].transform(
        "sum"
    )
    informed = grouped[totals.gt(0)].copy()
    informed["weight"] = informed["raw_support_value"] / totals[totals.gt(0)]
    informed["fallback_basis"] = "none"
    all_ids = set(simple["source_block_group_geoid"])
    supported_ids = set(informed["source_block_group_geoid"])
    fallback_ids = all_ids - supported_ids
    fallback = simple[simple["source_block_group_geoid"].isin(fallback_ids)].copy()
    fallback["fallback_basis"] = "zero_2010_population_simple_area"
    return pd.concat([informed, fallback], ignore_index=True), len(fallback_ids)


def set_acs_metadata(frame: pd.DataFrame, method_id: str, plan_id: str) -> pd.DataFrame:
    result = frame.copy()
    result["source_dataset_id"] = "acs5_pa_b01003_summary_file"
    result["source_reference_period"] = "product_specific"
    result["target_precinct_dataset_id"] = FIXED_TARGET_ID
    result["target_precinct_effective_vintage"] = FIXED_TARGET_VINTAGE
    result["target_senate_plan_id"] = plan_id
    result["target_senate_plan_reference_vintage"] = PLAN_VINTAGES[plan_id]
    result["method_id"] = method_id
    result["method_version"] = "1.0.0"
    result["weighting_universe"] = acs_weighting_universe(method_id)
    result["assignment_status"] = "assigned"
    result["nearest_assignment_used"] = False
    return result


def acs_weighting_universe(method_id: str) -> str:
    if method_id.startswith("simple_atomic_area"):
        return "normalized EPSG:5070 block-group/atomic intersection area"
    return (
        "2010 P0010001 block population through official relationship-area and "
        "geometry-only atomic support; simple area fallback for zero-support groups"
    )


def normalize_acs_crosswalk(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in [
        "source_block_group_geoid",
        "target_precinct_geoid",
        "fallback_basis",
        "source_dataset_id",
        "source_reference_period",
        "target_precinct_dataset_id",
        "target_precinct_effective_vintage",
        "target_senate_plan_id",
        "target_senate_plan_reference_vintage",
        "method_id",
        "method_version",
        "weighting_universe",
        "assignment_status",
    ]:
        result[column] = result[column].astype("string")
    result["senate_district"] = result["senate_district"].astype("Int64")
    for column in ["raw_support_value", "weight"]:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "float64"
        )
    result["nearest_assignment_used"] = result["nearest_assignment_used"].astype("bool")
    return result.sort_values(
        ["source_block_group_geoid", "target_precinct_geoid", "senate_district"],
        kind="stable",
    ).reset_index(drop=True)


def set_plan_metadata(frame: pd.DataFrame, plan_id: str) -> pd.DataFrame:
    result = frame.copy()
    result["target_senate_plan_id"] = plan_id
    result["target_senate_plan_reference_vintage"] = PLAN_VINTAGES[plan_id]
    return result


def validate_decennial_crosswalk(
    crosswalk: pd.DataFrame, population: pd.DataFrame
) -> None:
    assigned = crosswalk[crosswalk["assignment_status"].eq("assigned")]
    sums = assigned.groupby("source_block_geoid")["weight"].sum()
    populated = set(population.loc[population["P0010001"].gt(0), "source_block_geoid"])
    if not populated.issubset(set(assigned["source_block_geoid"])):
        raise ValueError("Material uncovered populated decennial sources")
    if sums.sub(1).abs().gt(WEIGHT_TOLERANCE).any():
        raise ValueError("Decennial crosswalk weights fail conservation")


def validate_acs_crosswalk(crosswalk: pd.DataFrame, population: pd.DataFrame) -> None:
    ids = set(population["source_block_group_geoid"])
    observed = set(crosswalk["source_block_group_geoid"])
    if ids != observed:
        raise ValueError(
            f"ACS crosswalk universe mismatch: missing={len(ids - observed)} "
            f"unexpected={len(observed - ids)}"
        )
    sums = crosswalk.groupby("source_block_group_geoid")["weight"].sum()
    if sums.sub(1).abs().gt(WEIGHT_TOLERANCE).any():
        raise ValueError("ACS crosswalk weights fail conservation")


def aggregate_decennial(
    population: pd.DataFrame, crosswalk: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    assigned = crosswalk[crosswalk["assignment_status"].eq("assigned")]
    allocated = assigned.merge(
        population[["source_block_geoid", "P0010001"]],
        on="source_block_geoid",
        validate="many_to_one",
    )
    allocated["population"] = allocated["P0010001"] * allocated["weight"]
    precinct = allocated.groupby("target_precinct_geoid", as_index=False)[
        "population"
    ].sum()
    senate = allocated.groupby("senate_district", as_index=False)["population"].sum()
    return precinct, senate


def aggregate_acs(
    population: pd.DataFrame, crosswalk: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    allocated = crosswalk.merge(
        population,
        on="source_block_group_geoid",
        validate="many_to_one",
    )
    allocated["estimate"] = allocated["B01003_001E"] * allocated["weight"]
    allocated["moe_component"] = allocated["B01003_001M"] * allocated["weight"]
    return (
        aggregate_acs_geography(allocated, "target_precinct_geoid"),
        aggregate_acs_geography(allocated, "senate_district"),
    )


def aggregate_acs_geography(frame: pd.DataFrame, geography: str) -> pd.DataFrame:
    return frame.groupby(geography, as_index=False).agg(
        estimate=("estimate", "sum"),
        margin_of_error=("moe_component", lambda values: math.sqrt((values**2).sum())),
        contributing_source_block_groups=("source_block_group_geoid", "nunique"),
    )


def add_result_metadata(
    frame: pd.DataFrame, product_id: str, plan_id: str, level: str
) -> pd.DataFrame:
    result = frame.copy()
    result["population_product_id"] = product_id
    result["senate_plan_id"] = plan_id
    result["senate_plan_reference_vintage"] = PLAN_VINTAGES[plan_id]
    result["target_snapshot_id"] = FIXED_TARGET_ID
    result["target_effective_vintage"] = FIXED_TARGET_VINTAGE
    result["geography_level"] = level
    if product_id.startswith("acs5_"):
        result["metric"] = "B01003_001E"
        result["moe_metric"] = "B01003_001M"
        result["moe_confidence_level"] = 0.90
        result["moe_aggregation_method"] = "weighted_source_moe_then_rss_v1"
        result["population_universe"] = "total_population"
    else:
        result["metric"] = "total_population"
        result["moe_metric"] = pd.NA
        result["moe_confidence_level"] = pd.NA
        result["moe_aggregation_method"] = pd.NA
        result["population_universe"] = "standard_total_population"
        result["estimate"] = result.pop("population")
        result["margin_of_error"] = pd.NA
        result["contributing_source_block_groups"] = pd.NA
    return result


def normalize_results(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    string_columns = [
        "target_precinct_geoid",
        "population_product_id",
        "senate_plan_id",
        "senate_plan_reference_vintage",
        "target_snapshot_id",
        "target_effective_vintage",
        "geography_level",
        "metric",
        "moe_metric",
        "moe_aggregation_method",
        "population_universe",
    ]
    for column in string_columns:
        if column not in result:
            result[column] = pd.NA
        result[column] = result[column].astype("string")
    if "senate_district" not in result:
        result["senate_district"] = pd.NA
    result["senate_district"] = result["senate_district"].astype("Int64")
    for column in ["estimate", "margin_of_error", "moe_confidence_level"]:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "float64"
        )
    result["contributing_source_block_groups"] = pd.to_numeric(
        result["contributing_source_block_groups"], errors="coerce"
    ).astype("Int64")
    return result


def crosswalk_path(directory: Path, product_id: str, plan_id: str) -> Path:
    return directory / f"{product_id}__{PLAN_SLUGS[plan_id]}__v1.parquet"


def crosswalk_entry(root: Path, path: Path, frame: pd.DataFrame) -> dict[str, object]:
    source_column = (
        "source_block_group_geoid"
        if "source_block_group_geoid" in frame
        else "source_block_geoid"
    )
    sort_columns = [source_column, "target_precinct_geoid"]
    if "senate_district" in frame:
        sort_columns.append("senate_district")
    method_id = (
        str(frame["method_id"].dropna().iloc[0])
        if "method_id" in frame and not frame["method_id"].dropna().empty
        else "lrc_published_split_v1"
    )
    return {
        "crosswalk_id": path.stem,
        "crosswalk_path": path.relative_to(root).as_posix(),
        "crosswalk_logical_sha256": logical_frame_hash(frame, sort_columns),
        "crosswalk_method_id": method_id,
        "crosswalk_allocation_rows": len(frame),
        "nearest_assignment_count": int(
            frame["nearest_assignment_used"].sum()
            if "nearest_assignment_used" in frame
            else 0
        ),
    }


def build_execution_manifest(
    candidates: pd.DataFrame,
    crosswalk_index: dict[tuple[str, str], dict[str, object]],
    precinct_path: str,
    senate_path: str,
    result_hashes: dict[str, str],
) -> pd.DataFrame:
    rows = []
    for row in candidates.to_dict("records"):
        entry = crosswalk_index[(row["product_id"], row["senate_plan_id"])]
        is_acs = row["product_id"].startswith("acs5_")
        input_reference = population_input_reference(row["product_id"])
        rows.append(
            {
                "pairing_id": row["pairing_id"],
                "execution_status": "executed_available_pairing",
                "election_id": row["election_id"],
                "election_date": row["election_date"],
                "cutoff_policy": row["cutoff_policy"],
                "fixed_precinct_snapshot_id": row["fixed_precinct_snapshot_id"],
                "senate_plan_id": row["senate_plan_id"],
                "population_product_id": row["product_id"],
                "population_product_family": row["product_family"],
                "population_reference_start": row["reference_start"],
                "population_reference_end": row["reference_end"],
                "population_release_date": row["release_date_published"],
                "population_input_id": row["source_geography_id"],
                **input_reference,
                **entry,
                "fixed_precinct_result_path": precinct_path,
                "fixed_precinct_result_logical_sha256": result_hashes["fixed_precinct"],
                "senate_result_path": senate_path,
                "senate_result_logical_sha256": result_hashes["senate"],
                "result_partition_key": (
                    f"{row['product_id']}__{row['senate_plan_id']}"
                ),
                "qa_report_path": "artifacts/poc016/qa_results.json",
                "known_limitation": (
                    acs_limitation(row["product_id"])
                    if is_acs
                    else DECENNIAL_LIMITS[row["product_id"]]
                ),
            }
        )
    rows.append(
        {
            "pairing_id": NO_PRODUCT_PAIRING_ID,
            "execution_status": "no_product_available_by_cutoff",
            "election_id": "pa_general_1990",
            "election_date": "1990-11-06",
            "cutoff_policy": "general_election_day",
            "fixed_precinct_snapshot_id": FIXED_TARGET_ID,
            "senate_plan_id": "pa_senate_1981_plan",
            "known_limitation": (
                "No cataloged Census/ACS population product was released by the "
                "1990 general-election cutoff; no post-election substitution or "
                "interpolation is made."
            ),
        }
    )
    result = pd.DataFrame(rows)
    for column in result.columns:
        result[column] = result[column].astype("string")
    return result.sort_values(
        ["election_date", "pairing_id"], kind="stable"
    ).reset_index(drop=True)


def acs_limitation(product_id: str) -> str:
    year = int(product_id.rsplit("_", 1)[1])
    return ACS_LIMIT_SIMPLE if year <= 2010 else ACS_LIMIT_INFORMED


def population_input_reference(product_id: str) -> dict[str, str]:
    decennial_manifests = {
        "dec_1990": "artifacts/poc013/input_manifest.json",
        "dec_2000": "artifacts/poc012/input_manifest.json",
        "dec_2010": "artifacts/poc011/input_manifest.json",
        "dec_2020": "artifacts/poc010/input_manifest.json",
    }
    if product_id in decennial_manifests:
        return {
            "population_input_manifest_path": decennial_manifests[product_id],
            "population_input_manifest_selector": product_id,
        }
    year = product_id.rsplit("_", 1)[1]
    return {
        "population_input_manifest_path": "artifacts/poc016/input_manifest.json",
        "population_input_manifest_selector": f"data/raw/acs5_all_pa/{year}/",
    }


def build_checks(
    availability: pd.DataFrame,
    candidates: pd.DataFrame,
    product_plans: pd.DataFrame,
    manifest: pd.DataFrame,
    crosswalk_index: dict[tuple[str, str], dict[str, object]],
    precinct: pd.DataFrame,
    senate: pd.DataFrame,
    source_totals: dict[str, float],
) -> list[dict[str, object]]:
    executed = manifest[manifest["execution_status"].eq("executed_available_pairing")]
    no_product = manifest[
        manifest["execution_status"].eq("no_product_available_by_cutoff")
    ]
    expected_keys = set(
        map(tuple, product_plans[["product_id", "senate_plan_id"]].values)
    )
    precinct_keys = set(
        map(
            tuple,
            precinct[["population_product_id", "senate_plan_id"]]
            .drop_duplicates()
            .values,
        )
    )
    senate_keys = set(
        map(
            tuple,
            senate[["population_product_id", "senate_plan_id"]]
            .drop_duplicates()
            .values,
        )
    )
    precinct_totals = precinct.groupby(["population_product_id", "senate_plan_id"])[
        "estimate"
    ].sum()
    senate_totals = senate.groupby(["population_product_id", "senate_plan_id"])[
        "estimate"
    ].sum()
    expected = precinct_totals.index.get_level_values("population_product_id").map(
        source_totals
    )
    precinct_source_delta = precinct_totals.to_numpy() - expected
    senate_source_delta = senate_totals.to_numpy() - expected
    precinct_plan_ranges = precinct.pivot_table(
        index=["population_product_id", "target_precinct_geoid"],
        columns="senate_plan_id",
        values="estimate",
    ).pipe(lambda frame: frame.max(axis=1) - frame.min(axis=1))
    acs_precinct = precinct[precinct["population_product_id"].str.startswith("acs5_")]
    acs_senate = senate[senate["population_product_id"].str.startswith("acs5_")]
    return [
        check("availability_matrix_rows", len(availability) == 380, len(availability)),
        check("candidate_pairings", len(candidates) == 114, len(candidates)),
        check(
            "unique_product_plan_allocations",
            len(product_plans) == 39,
            len(product_plans),
        ),
        check("execution_manifest_rows", len(manifest) == 115, len(manifest)),
        check("all_candidates_executed", len(executed) == 114, len(executed)),
        check("one_zero_product_cycle", len(no_product) == 1, len(no_product)),
        check(
            "zero_product_cycle_is_1990",
            no_product["election_id"].tolist() == ["pa_general_1990"],
            no_product["election_id"].tolist(),
        ),
        check(
            "crosswalk_index_complete",
            set(crosswalk_index) == expected_keys,
            len(crosswalk_index),
        ),
        check(
            "precinct_product_plan_keys",
            precinct_keys == expected_keys,
            len(precinct_keys),
        ),
        check(
            "senate_product_plan_keys", senate_keys == expected_keys, len(senate_keys)
        ),
        check(
            "all_precinct_partitions_complete",
            precinct.groupby(["population_product_id", "senate_plan_id"])
            .size()
            .eq(9_178)
            .all(),
            precinct.groupby(["population_product_id", "senate_plan_id"])
            .size()
            .describe()
            .to_dict(),
        ),
        check(
            "all_senate_partitions_complete",
            senate.groupby(["population_product_id", "senate_plan_id"])
            .size()
            .eq(50)
            .all(),
            senate.groupby(["population_product_id", "senate_plan_id"])
            .size()
            .describe()
            .to_dict(),
        ),
        check(
            "fixed_target_constant",
            set(manifest["fixed_precinct_snapshot_id"].dropna()) == {FIXED_TARGET_ID},
            sorted(manifest["fixed_precinct_snapshot_id"].dropna().unique()),
        ),
        check(
            "no_nearest_assignments",
            all(
                entry["nearest_assignment_count"] == 0
                for entry in crosswalk_index.values()
            ),
            sum(
                entry["nearest_assignment_count"] for entry in crosswalk_index.values()
            ),
        ),
        check(
            "precinct_state_totals_conserved",
            abs(precinct_source_delta).max() <= RESULT_TOLERANCE,
            {
                "maximum_absolute_delta": float(abs(precinct_source_delta).max()),
                "tolerance": RESULT_TOLERANCE,
            },
        ),
        check(
            "senate_state_totals_conserved",
            abs(senate_source_delta).max() <= RESULT_TOLERANCE,
            {
                "maximum_absolute_delta": float(abs(senate_source_delta).max()),
                "tolerance": RESULT_TOLERANCE,
            },
        ),
        check(
            "precinct_and_senate_totals_agree",
            (precinct_totals - senate_totals).abs().max() <= RESULT_TOLERANCE,
            float((precinct_totals - senate_totals).abs().max()),
        ),
        check(
            "fixed_precinct_results_plan_invariant_within_precision",
            precinct_plan_ranges.max() <= PRECINCT_PLAN_INVARIANCE_TOLERANCE,
            {
                "maximum_absolute_person_range": float(precinct_plan_ranges.max()),
                "tolerance": PRECINCT_PLAN_INVARIANCE_TOLERANCE,
            },
        ),
        check(
            "acs_moes_complete_nonnegative",
            acs_precinct["margin_of_error"].notna().all()
            and acs_senate["margin_of_error"].notna().all()
            and acs_precinct["margin_of_error"].ge(0).all()
            and acs_senate["margin_of_error"].ge(0).all(),
            {
                "precinct_null": int(acs_precinct["margin_of_error"].isna().sum()),
                "senate_null": int(acs_senate["margin_of_error"].isna().sum()),
            },
        ),
    ]


def load_source_totals(root: Path) -> dict[str, float]:
    totals = {
        "dec_1990": float(
            load_1990_stf1b_block_population(
                root / SOURCES_1990["census_population"]["relative_path"]
            )["P0010001"].sum()
        ),
        "dec_2000": float(
            load_2000_pl94_block_population(
                root / SOURCES_2000["census_population_geography"]["relative_path"],
                root / SOURCES_2000["census_population_file01"]["relative_path"],
            )["P0010001"].sum()
        ),
        "dec_2010": float(
            load_2010_pl94_block_population(
                root / SOURCES_2010["census_population"]["relative_path"]
            )["P0010001"].sum()
        ),
        "dec_2020": float(
            load_pl94_block_population_statewide(
                root / "data/raw/census_2020_pa_pl/pa2020.pl.zip"
            )["P0010001"].sum()
        ),
    }
    for year in range(2009, 2025):
        totals[f"acs5_{year}"] = float(
            load_acs5_block_group_population(
                year, root / f"data/raw/acs5_all_pa/{year}"
            )["B01003_001E"].sum()
        )
    return totals


def build_input_manifest(
    root: Path, plan_atoms: dict[str, gpd.GeoDataFrame]
) -> dict[str, object]:
    files = []
    for path in sorted((root / "data/raw/acs5_all_pa").glob("*/*")):
        if not path.is_file():
            continue
        files.append(file_manifest_entry(root, path, "U.S. Census Bureau"))
    for relative in [
        "data/raw/census_2009_pa_block_groups/tl_2009_42_bg00.zip",
        "data/raw/census_2010_pa_block_groups/tl_2010_42_bg10.zip",
        "data/raw/census_2020_pa_block_groups/tl_2020_42_bg.zip",
        "mappings/population_election_availability_v1.csv",
    ]:
        files.append(file_manifest_entry(root, root / relative, "U.S. Census Bureau"))
    overlays = []
    for plan_id, atoms in plan_atoms.items():
        overlays.append(
            {
                "artifact_id": f"{plan_id}_fixed_precinct_overlay_v3",
                "producer": "POC022",
                "relative_path": PLAN_PATHS[plan_id],
                "reference_vintage": PLAN_VINTAGES[plan_id],
                "target_vintage": FIXED_TARGET_VINTAGE,
                "method_id": "fixed_precinct_senate_overlay_v3",
                "logical_sha256": logical_geoframe_hash(
                    atoms, ["target_precinct_geoid", "senate_district"]
                ),
                "crs": str(atoms.crs),
                "geographic_universe": "Pennsylvania fixed precinct/Senate atoms",
            }
        )
    return {
        "task": "POC016",
        "created_at": datetime.now(UTC).isoformat(),
        "source_files": files,
        "derived_inputs": overlays,
    }


def file_manifest_entry(root: Path, path: Path, producer: str) -> dict[str, object]:
    return {
        "producer": producer,
        "exact_product": path.name,
        "retrieval_timestamp": datetime.fromtimestamp(
            path.stat().st_mtime, UTC
        ).isoformat(),
        "reference_vintage": path.parent.name,
        "source_url": source_url_for_path(path),
        "sha256": sha256(path),
        "license_access": "Public federal data; cite U.S. Census Bureau",
        "crs": None,
        "schema": "product-specific official Summary File or TIGER archive",
        "geographic_universe": "Pennsylvania",
        "relative_path": path.relative_to(root).as_posix(),
    }


def source_url_for_path(path: Path) -> str:
    name = path.name
    if "population_election_availability" in name:
        return "derived from checksum-frozen POC019 inputs"
    if name == "tl_2009_42_bg00.zip":
        return "https://www2.census.gov/geo/tiger/TIGER2009/42_PENNSYLVANIA/tl_2009_42_bg00.zip"
    if name == "tl_2010_42_bg10.zip":
        return "https://www2.census.gov/geo/tiger/TIGER2010/BG/2010/tl_2010_42_bg10.zip"
    if name == "tl_2020_42_bg.zip":
        return "https://www2.census.gov/geo/tiger/TIGER2020/BG/tl_2020_42_bg.zip"
    year = path.parent.name
    if name.startswith("acsdt5y"):
        return (
            "https://www2.census.gov/programs-surveys/acs/summary_file/"
            f"{year}/table-based-SF/data/5YRData/{name}"
        )
    if name == "sequence_lookup.txt":
        suffix = (
            "documentation/5_year/user_tools/Sequence_Number_and_Table_Number_Lookup.txt"
            if int(year) <= 2012
            else "documentation/user_tools/ACS_5yr_Seq_Table_Number_Lookup.txt"
        )
        return (
            f"https://www2.census.gov/programs-surveys/acs/summary_file/{year}/{suffix}"
        )
    return (
        "https://www2.census.gov/programs-surveys/acs/summary_file/"
        f"{year}/data/5_year_seq_by_state/Pennsylvania/Tracts_Block_Groups_Only/{name}"
    )


def write_immutable_csv(frame: pd.DataFrame, path: Path, sort_by: list[str]) -> str:
    expected = logical_frame_hash(frame, sort_by)
    if path.exists():
        observed = logical_frame_hash(pd.read_csv(path, dtype="string"), sort_by)
        if observed != expected:
            raise RuntimeError(
                f"Refusing to overwrite changed versioned artifact: {path}"
            )
        return "reused_identical"
    frame.to_csv(path, index=False, lineterminator="\n")
    return "created"


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(qa: dict[str, object]) -> str:
    passed = sum(check["passed"] for check in qa["checks"])
    return f"""# POC016 run report

- Passed: `{qa["passed"]}`
- Available election/product pairings executed: `{qa["candidate_pairings"]}`
- Unique product/plan allocations: `{qa["unique_product_plan_allocations"]}`
- Explicit zero-product elections: `{len(qa["zero_product_elections"])}`
- QA checks passed: `{passed}` of `{len(qa["checks"])}`
- Nearest assignments: `{qa["nearest_assignment_count"]}`
- Execution-manifest logical SHA-256: `{qa["hashes"]["execution_manifest"]}`
- Fixed-precinct result logical SHA-256: `{qa["hashes"]["fixed_precinct"]}`
- Senate result logical SHA-256: `{qa["hashes"]["senate"]}`
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(json.dumps(qa, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
