"""Build direct ACS block-group-to-legislative partitions for POC029."""

from __future__ import annotations

import argparse
import gc
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from census_pa_poc.direct_legislative_decennial import (
    WEIGHT_TOLERANCE,
    build_atomic_area_weights,
)
from census_pa_poc.legislative_plans import NORMALIZED_PLAN_PATH
from census_pa_poc.sources import (
    load_2010_2020_block_relationship,
    load_2010_pl94_block_population,
    load_acs5_block_group_population,
    sha256,
    vsi_zip_member,
)
from census_pa_poc.statewide_2010 import SOURCES as SOURCES_2010
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

RESULT_TOLERANCE = 1e-6
ACS_PRODUCT_PREFIX = "acs5_"
PARTITION_MAPPING_PATH = "mappings/legislative_population_partitions_v1.csv"
EXPECTED_DISTRICTS = {"house": 203, "senate": 50}
PLAN_VINTAGES = {
    "pa_senate_2001_final": "2001",
    "pa_senate_2012_revised_final": "2012",
    "pa_senate_2021_final": "2021",
}
BLOCK_GROUP_SOURCES = {
    "2009": {
        "relative_path": ("data/raw/census_2009_pa_block_groups/tl_2009_42_bg00.zip"),
        "member": "tl_2009_42_bg00.shp",
        "id_column": "BKGPIDFP00",
        "source_dataset_id": "census_2009_pa_2000_block_groups",
        "source_geography_vintage": "2000",
    },
    "2010": {
        "relative_path": ("data/raw/census_2010_pa_block_groups/tl_2010_42_bg10.zip"),
        "member": "tl_2010_42_bg10.shp",
        "id_column": "GEOID10",
        "source_dataset_id": "census_2010_pa_block_groups",
        "source_geography_vintage": "2010",
    },
    "2020": {
        "relative_path": "data/raw/census_2020_pa_block_groups/tl_2020_42_bg.zip",
        "member": "tl_2020_42_bg.shp",
        "id_column": "GEOID",
        "source_dataset_id": "census_2020_pa_block_groups",
        "source_geography_vintage": "2020",
    },
}
REGIME_METHODS = {
    "simple_2009": "simple_area_direct_legislative_acs5_2009_v2",
    "simple_2010": "simple_area_direct_legislative_acs5_2010_v2",
    "simple_2020": "simple_area_direct_legislative_acs5_2020_fallback_v2",
    "population_2010_bg": (
        "census2010_population_direct_legislative_acs5_2010_geography_v2"
    ),
    "population_2020_bg": (
        "census2010_population_direct_legislative_acs5_2020_geography_v2"
    ),
}
REGIME_WEIGHTING_UNIVERSES = {
    "simple_2009": (
        "normalized EPSG:5070 Census 2000 block-group/legislative-plan area"
    ),
    "simple_2010": (
        "normalized EPSG:5070 Census 2010 block-group/legislative-plan area"
    ),
    "simple_2020": (
        "normalized EPSG:5070 Census 2020 block-group/legislative-plan area"
    ),
    "population_2010_bg": (
        "2010 P0010001 block population allocated by accepted direct 2010-block/"
        "legislative-plan weights; simple area fallback for zero-support groups"
    ),
    "population_2020_bg": (
        "2010 P0010001 block population through official 2010-to-2020 relationship "
        "area and source-local 2020-block/legislative-plan area; simple area "
        "fallback for zero-support groups"
    ),
}
UNCERTAINTY = (
    "Target 90% MOEs use weighted source MOE components combined by root-sum-"
    "square; source covariance and allocation-weight uncertainty are omitted."
)


def run(root: Path) -> dict[str, object]:
    """Execute and validate all 56 direct ACS partitions."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc029"
    processed_dir = root / "data/processed/direct_legislative/poc029"
    crosswalk_dir = processed_dir / "acs_crosswalks"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    crosswalk_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_acs_manifest(root)
    require_manifest_hashes(manifest)
    write_json(artifact_dir / "acs_input_manifest.json", manifest)

    plans = gpd.read_parquet(root / NORMALIZED_PLAN_PATH)
    partitions = build_partition_registry(root, plans)
    populations = load_acs_populations(root, partitions)
    crosswalks, crosswalk_profiles = build_crosswalks(
        root, plans, partitions, populations, crosswalk_dir
    )

    results = []
    profiles = []
    checks = []
    for partition in partitions.to_dict("records"):
        product_id = partition["population_product_id"]
        regime = partition["support_regime"]
        plan_id = partition["target_plan_id"]
        crosswalk = crosswalks[(regime, plan_id)]
        population = populations[product_id]
        validate_crosswalk(crosswalk, population)
        result = aggregate_acs(population, crosswalk, partition)
        profile = profile_partition(
            partition,
            population,
            crosswalk,
            result,
            crosswalk_profiles[(regime, plan_id)],
        )
        results.append(result)
        profiles.append(profile)
        checks.extend(partition_checks(profile))

    combined = pd.concat(results, ignore_index=True).sort_values(
        ["population_product_id", "target_plan_id", "target_district_id"]
    )
    result_path = processed_dir / "acs_legislative_results_v1.parquet"
    result_write = write_immutable_parquet(
        combined,
        result_path,
        ["population_product_id", "target_plan_id", "target_district_id"],
    )
    result_hash = logical_frame_hash(
        combined,
        ["population_product_id", "target_plan_id", "target_district_id"],
    )
    qa = {
        "task": "POC029",
        "stage": "direct_acs_partitions",
        "partition_count": len(partitions),
        "product_count": int(partitions["population_product_id"].nunique()),
        "crosswalk_count": len(crosswalks),
        "chambers": sorted(partitions["target_chamber"].unique().tolist()),
        "plan_vintages": sorted(
            partitions["target_plan_reference_vintage"].unique().tolist()
        ),
        "support_regimes": sorted(partitions["support_regime"].unique().tolist()),
        "profiles": profiles,
        "crosswalk_profiles": list(crosswalk_profiles.values()),
        "checks": checks,
        "artifact_writes": {"combined_results": result_write},
        "hashes": {"combined_results": result_hash},
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "acs_qa.json", qa)
    (artifact_dir / "acs_report.md").write_text(render_report(qa))
    if not qa["passed"]:
        raise RuntimeError(
            "POC029 ACS stage failed; inspect artifacts/poc029/acs_qa.json"
        )
    return qa


def build_partition_registry(root: Path, plans: gpd.GeoDataFrame) -> pd.DataFrame:
    """Expand accepted ACS product/plan applicability to both chambers."""
    accepted = pd.read_csv(root / PARTITION_MAPPING_PATH, dtype="string")
    accepted = accepted[
        accepted["population_product_id"].str.startswith(ACS_PRODUCT_PREFIX)
    ]
    rows = []
    for partition in accepted.to_dict("records"):
        product_id = partition["population_product_id"]
        vintage = partition["target_plan_reference_vintage"]
        year = int(product_id.rsplit("_", 1)[1])
        for chamber in ("house", "senate"):
            matching = plans[
                plans["target_chamber"].eq(chamber)
                & plans["target_plan_reference_vintage"].eq(vintage)
            ]
            rows.append(
                {
                    "population_product_id": product_id,
                    "population_product_year": year,
                    "source_geography_grain": source_grain_for_year(year),
                    "source_geography_vintage": source_vintage_for_year(year),
                    "support_regime": regime_for_year(year),
                    "target_chamber": chamber,
                    "target_plan_id": matching["target_plan_id"].iloc[0],
                    "target_plan_reference_vintage": vintage,
                    "first_applicable_election": partition[
                        "first_applicable_election"
                    ],
                    "last_applicable_election": partition[
                        "last_applicable_election"
                    ],
                    "expected_district_count": EXPECTED_DISTRICTS[chamber],
                    "uncertainty": UNCERTAINTY,
                }
            )
    return pd.DataFrame(rows).sort_values(["population_product_id", "target_plan_id"])


def regime_for_year(year: int) -> str:
    if year == 2009:
        return "simple_2009"
    if year == 2010:
        return "simple_2010"
    if 2011 <= year <= 2019:
        return "population_2010_bg"
    if 2020 <= year <= 2024:
        return "population_2020_bg"
    raise ValueError(f"Unsupported ACS year: {year}")


def source_vintage_for_year(year: int) -> str:
    if year == 2009:
        return "2000"
    if year <= 2019:
        return "2010"
    return "2020"


def source_grain_for_year(year: int) -> str:
    return f"Census {source_vintage_for_year(year)} block group"


def load_acs_populations(
    root: Path, partitions: pd.DataFrame
) -> dict[str, pd.DataFrame]:
    return {
        product_id: load_acs5_block_group_population(
            int(product_id.rsplit("_", 1)[1]),
            root / f"data/raw/acs5_all_pa/{product_id.rsplit('_', 1)[1]}",
        )
        for product_id in sorted(partitions["population_product_id"].unique())
    }


def build_crosswalks(
    root: Path,
    plans: gpd.GeoDataFrame,
    partitions: pd.DataFrame,
    populations: dict[str, pd.DataFrame],
    crosswalk_dir: Path,
) -> tuple[
    dict[tuple[str, str], pd.DataFrame],
    dict[tuple[str, str], dict[str, object]],
]:
    """Build each reusable source-grain/support-regime/plan crosswalk once."""
    keys = sorted(
        set(
            map(
                tuple,
                partitions[["support_regime", "target_plan_id"]].itertuples(
                    index=False, name=None
                ),
            )
        )
    )
    geometries: dict[str, gpd.GeoDataFrame] = {}
    simple_cache: dict[tuple[str, str], tuple[pd.DataFrame, dict[str, object]]] = {}
    crosswalks = {}
    profiles = {}
    for regime, plan_id in keys:
        path = crosswalk_dir / f"{regime}__{plan_id}__v2.parquet"
        if path.exists():
            crosswalk = pd.read_parquet(path)
            diagnostics = {"crosswalk_artifact": "reused_existing"}
        else:
            plan = plans[plans["target_plan_id"].eq(plan_id)]
            if regime in {"simple_2009", "simple_2010"}:
                vintage = regime.rsplit("_", 1)[1]
                crosswalk, diagnostics = get_simple_crosswalk(
                    root,
                    geometries,
                    simple_cache,
                    vintage,
                    plan,
                    zero_estimate_ids(populations, vintage),
                )
            elif regime == "population_2010_bg":
                simple, _ = get_simple_crosswalk(
                    root,
                    geometries,
                    simple_cache,
                    "2010",
                    plan,
                    zero_estimate_ids(populations, "2010"),
                )
                crosswalk, diagnostics = build_population_2010_bg_crosswalk(
                    root, plan_id, simple
                )
            elif regime == "population_2020_bg":
                simple, _ = get_simple_crosswalk(
                    root,
                    geometries,
                    simple_cache,
                    "2020",
                    plan,
                    zero_estimate_ids(populations, "2020"),
                )
                crosswalk, diagnostics = build_population_2020_bg_crosswalk(
                    root, plan_id, simple
                )
            else:
                raise ValueError(f"Unknown ACS support regime: {regime}")
            status = write_immutable_parquet(
                crosswalk,
                path,
                ["source_geography_id", "target_district_id"],
            )
            diagnostics["crosswalk_write"] = status
        crosswalk_hash = logical_frame_hash(
            crosswalk, ["source_geography_id", "target_district_id"]
        )
        profile = profile_crosswalk(
            regime,
            plan_id,
            crosswalk,
            diagnostics,
            path.relative_to(root).as_posix(),
            crosswalk_hash,
        )
        crosswalks[(regime, plan_id)] = crosswalk
        profiles[(regime, plan_id)] = profile
        gc.collect()
    return crosswalks, profiles


def get_simple_crosswalk(
    root: Path,
    geometries: dict[str, gpd.GeoDataFrame],
    cache: dict[tuple[str, str], tuple[pd.DataFrame, dict[str, object]]],
    vintage: str,
    plan: gpd.GeoDataFrame,
    zero_ids: set[str],
) -> tuple[pd.DataFrame, dict[str, object]]:
    plan_id = str(plan["target_plan_id"].iloc[0])
    key = (vintage, plan_id)
    if key not in cache:
        if vintage not in geometries:
            geometries[vintage] = load_block_groups(root, vintage)
        cache[key] = build_simple_crosswalk(
            geometries[vintage], plan, vintage, zero_ids
        )
    return cache[key]


def load_block_groups(root: Path, vintage: str) -> gpd.GeoDataFrame:
    source = BLOCK_GROUP_SOURCES[vintage]
    frame = gpd.read_file(
        vsi_zip_member(root / source["relative_path"], source["member"])
    )[[source["id_column"], "geometry"]]
    return frame.rename(columns={source["id_column"]: "GEOID"})


def build_simple_crosswalk(
    block_groups: gpd.GeoDataFrame,
    plan: gpd.GeoDataFrame,
    vintage: str,
    zero_estimate_ids: set[str],
) -> tuple[pd.DataFrame, dict[str, object]]:
    atomic, diagnostics = build_atomic_area_weights(block_groups, plan, "GEOID")
    crosswalk = atomic.rename(
        columns={
            "source_atomic_geoid": "source_geography_id",
            "target_atomic_weight": "weight",
            "target_atomic_area_square_meters": "raw_support_value",
        }
    )
    crosswalk["fallback_basis"] = "none"
    crosswalk["assignment_status"] = "assigned"
    uncovered = set(diagnostics["uncovered_atomic_ids"])
    material = uncovered - zero_estimate_ids
    if material:
        raise ValueError(
            f"Direct ACS area crosswalk omits nonzero source geographies: {sorted(material)}"
        )
    if uncovered:
        projected = block_groups.to_crs("EPSG:5070").set_index("GEOID")
        exceptions = pd.DataFrame(
            {
                "source_geography_id": sorted(uncovered),
                "target_district_id": pd.Series(
                    [pd.NA] * len(uncovered), dtype="Int64"
                ),
                "raw_support_value": [
                    float(projected.loc[source_id].geometry.area)
                    for source_id in sorted(uncovered)
                ],
                "weight": 0.0,
                "fallback_basis": "zero_estimate_water_only_unassigned",
                "assignment_status": "typed_zero_estimate_water_exception",
            }
        )
        crosswalk = pd.concat([crosswalk, exceptions], ignore_index=True)
    diagnostics["typed_zero_estimate_water_exceptions"] = len(uncovered)
    diagnostics["typed_zero_estimate_water_exception_ids"] = sorted(uncovered)
    regime = f"simple_{vintage}"
    return normalize_crosswalk(crosswalk, plan, regime, vintage), diagnostics


def zero_estimate_ids(populations: dict[str, pd.DataFrame], vintage: str) -> set[str]:
    """Return sources with zero estimates in every product using the geography."""
    source_vintage = BLOCK_GROUP_SOURCES[vintage]["source_geography_vintage"]
    matching = [
        frame
        for product_id, frame in populations.items()
        if source_vintage_for_year(int(product_id.rsplit("_", 1)[1])) == source_vintage
    ]
    if not matching:
        return set()
    zero_sets = [
        set(frame.loc[frame["B01003_001E"].eq(0), "source_block_group_geoid"])
        for frame in matching
    ]
    return set.intersection(*zero_sets)


def build_population_2010_bg_crosswalk(
    root: Path, plan_id: str, simple: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, object]]:
    population = load_2010_pl94_block_population(
        root / SOURCES_2010["census_population"]["relative_path"]
    )
    direct = pd.read_parquet(
        root
        / "data/processed/direct_legislative/poc029/decennial_crosswalks"
        / f"dec_2010__{plan_id}__v1.parquet"
    )
    assigned = direct[direct["assignment_status"].eq("assigned")].merge(
        population,
        left_on="source_geography_id",
        right_on="source_block_geoid",
        validate="many_to_one",
    )
    assigned["source_geography_id"] = assigned["source_geography_id"].str.slice(0, 12)
    assigned["raw_support_value"] = assigned["P0010001"] * assigned["weight"]
    grouped = assigned.groupby(
        ["source_geography_id", "target_district_id"], as_index=False
    )["raw_support_value"].sum()
    crosswalk, fallback = normalize_support_with_fallback(grouped, simple)
    plan = direct[["target_chamber", "target_plan_id", "target_plan_reference_vintage"]]
    plan = plan.drop_duplicates()
    normalized = normalize_crosswalk(
        crosswalk,
        plan,
        "population_2010_bg",
        "2010",
    )
    return normalized, {
        "direct_decennial_support_path": (
            "data/processed/direct_legislative/poc029/decennial_crosswalks/"
            f"dec_2010__{plan_id}__v1.parquet"
        ),
        "zero_support_fallback_block_groups": fallback,
        "nearest_assignment_count": 0,
    }


def build_population_2020_bg_crosswalk(
    root: Path, plan_id: str, simple: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, object]]:
    population = load_2010_pl94_block_population(
        root / SOURCES_2010["census_population"]["relative_path"]
    )
    relationship = load_2010_2020_block_relationship(
        root / SOURCES_2010["block_relationship"]["relative_path"]
    )
    atomic = pd.read_parquet(
        root
        / "data/processed/direct_legislative/"
        / "lrc_fragment_to_2021_legislative_plan_v1.parquet"
    )
    atomic = atomic[
        atomic["target_plan_id"].eq(plan_id)
        & atomic["assignment_status"].eq("assigned")
    ].copy()
    parent_district = atomic.groupby(
        ["source_geography_id", "target_district_id"], as_index=False
    )["atomic_area_square_meters"].sum()
    parent_district["parent_area"] = parent_district.groupby("source_geography_id")[
        "atomic_area_square_meters"
    ].transform("sum")
    parent_district["target_plan_weight"] = (
        parent_district["atomic_area_square_meters"] / parent_district["parent_area"]
    )

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
        parent_district,
        left_on="target_2020_block_geoid",
        right_on="source_geography_id",
        validate="many_to_many",
    )
    support["source_geography_id"] = support["target_2020_block_geoid"].str.slice(0, 12)
    support["raw_support_value"] = (
        support["P0010001"]
        * support["relationship_weight"]
        * support["target_plan_weight"]
    )
    grouped = support.groupby(
        ["source_geography_id", "target_district_id"], as_index=False
    )["raw_support_value"].sum()
    crosswalk, fallback = normalize_support_with_fallback(grouped, simple)
    plan = atomic[["target_chamber", "target_plan_id", "target_plan_reference_vintage"]]
    plan = plan.drop_duplicates()
    normalized = normalize_crosswalk(
        crosswalk,
        plan,
        "population_2020_bg",
        "2020",
    )
    return normalized, {
        "current_plan_atomic_assignment_path": (
            "data/processed/direct_legislative/"
            "lrc_fragment_to_2021_legislative_plan_v1.parquet"
        ),
        "zero_support_fallback_block_groups": fallback,
        "nearest_assignment_count": 0,
    }


def normalize_support_with_fallback(
    grouped: pd.DataFrame, simple: pd.DataFrame
) -> tuple[pd.DataFrame, int]:
    totals = grouped.groupby("source_geography_id")["raw_support_value"].transform(
        "sum"
    )
    informed = grouped[totals.gt(0)].copy()
    informed["weight"] = informed["raw_support_value"] / totals[totals.gt(0)]
    informed["fallback_basis"] = "none"
    all_ids = set(simple["source_geography_id"])
    supported_ids = set(informed["source_geography_id"])
    fallback_ids = all_ids - supported_ids
    fallback = simple[simple["source_geography_id"].isin(fallback_ids)][
        [
            "source_geography_id",
            "target_district_id",
            "raw_support_value",
            "weight",
        ]
    ].copy()
    fallback["fallback_basis"] = "zero_2010_population_simple_area"
    return pd.concat([informed, fallback], ignore_index=True), len(fallback_ids)


def normalize_crosswalk(
    frame: pd.DataFrame,
    plan: pd.DataFrame,
    regime: str,
    source_vintage: str,
) -> pd.DataFrame:
    result = frame.copy()
    result["target_chamber"] = str(plan["target_chamber"].iloc[0])
    result["target_plan_id"] = str(plan["target_plan_id"].iloc[0])
    result["target_plan_reference_vintage"] = str(
        plan["target_plan_reference_vintage"].iloc[0]
    )
    source = BLOCK_GROUP_SOURCES[source_vintage if source_vintage != "2000" else "2009"]
    result["source_dataset_id"] = source["source_dataset_id"]
    result["source_geography_vintage"] = source["source_geography_vintage"]
    result["source_estimate_metric_id"] = "B01003_001E"
    result["source_moe_metric_id"] = "B01003_001M"
    result["method_id"] = REGIME_METHODS[regime]
    result["method_version"] = "2.0.0"
    result["weighting_universe"] = REGIME_WEIGHTING_UNIVERSES[regime]
    if "assignment_status" not in result:
        result["assignment_status"] = (
            result["target_district_id"]
            .notna()
            .map({True: "assigned", False: "typed_zero_estimate_water_exception"})
        )
    result["nearest_assignment_used"] = False
    columns = [
        "source_geography_id",
        "source_dataset_id",
        "source_geography_vintage",
        "source_estimate_metric_id",
        "source_moe_metric_id",
        "target_chamber",
        "target_plan_id",
        "target_plan_reference_vintage",
        "target_district_id",
        "raw_support_value",
        "weight",
        "weighting_universe",
        "fallback_basis",
        "method_id",
        "method_version",
        "assignment_status",
        "nearest_assignment_used",
    ]
    result = result[columns]
    string_columns = [
        column
        for column in columns
        if column
        not in {
            "target_district_id",
            "raw_support_value",
            "weight",
            "nearest_assignment_used",
        }
    ]
    for column in string_columns:
        result[column] = result[column].astype("string")
    result["target_district_id"] = pd.to_numeric(
        result["target_district_id"], errors="raise"
    ).astype("Int64")
    result["raw_support_value"] = pd.to_numeric(
        result["raw_support_value"], errors="coerce"
    ).astype("float64")
    result["weight"] = result["weight"].astype("float64")
    result["nearest_assignment_used"] = result["nearest_assignment_used"].astype("bool")
    return result.sort_values(["source_geography_id", "target_district_id"])


def validate_crosswalk(crosswalk: pd.DataFrame, population: pd.DataFrame) -> None:
    expected = set(population["source_block_group_geoid"])
    observed = set(crosswalk["source_geography_id"])
    if expected != observed:
        raise ValueError(
            f"Direct ACS source universe mismatch: missing={len(expected - observed)} "
            f"unexpected={len(observed - expected)}"
        )
    assigned = crosswalk[crosswalk["assignment_status"].eq("assigned")]
    exceptions = crosswalk[~crosswalk["assignment_status"].eq("assigned")]
    sums = assigned.groupby("source_geography_id")["weight"].sum()
    if sums.sub(1).abs().max() > WEIGHT_TOLERANCE:
        raise ValueError("Direct ACS crosswalk weights do not sum to one")
    if assigned["target_district_id"].isna().any():
        raise ValueError("Assigned direct ACS rows require a district")
    exception_ids = set(exceptions["source_geography_id"])
    exception_population = population[
        population["source_block_group_geoid"].isin(exception_ids)
    ]
    if exception_population["B01003_001E"].ne(0).any():
        raise ValueError("Direct ACS typed exceptions must have zero estimate")
    if not exceptions.empty and (
        exceptions["target_district_id"].notna().any()
        or exceptions["weight"].ne(0).any()
    ):
        raise ValueError("Direct ACS typed exceptions must remain unassigned")
    if any("precinct" in column for column in crosswalk.columns):
        raise ValueError(
            "Direct legislative ACS output cannot contain precinct identity"
        )


def aggregate_acs(
    population: pd.DataFrame,
    crosswalk: pd.DataFrame,
    partition: dict[str, object],
) -> pd.DataFrame:
    allocated = crosswalk[crosswalk["assignment_status"].eq("assigned")].merge(
        population,
        left_on="source_geography_id",
        right_on="source_block_group_geoid",
        validate="many_to_one",
    )
    allocated["estimate"] = allocated["B01003_001E"] * allocated["weight"]
    allocated["moe_component"] = allocated["B01003_001M"] * allocated["weight"]
    result = allocated.groupby("target_district_id", as_index=False).agg(
        estimate=("estimate", "sum"),
        margin_of_error=(
            "moe_component",
            lambda values: math.sqrt((values**2).sum()),
        ),
        contributing_source_block_groups=("source_geography_id", "nunique"),
    )
    result["population_product_id"] = partition["population_product_id"]
    result["source_estimate_metric_id"] = "B01003_001E"
    result["source_moe_metric_id"] = "B01003_001M"
    result["moe_confidence_level"] = 0.90
    result["moe_aggregation_method"] = "weighted_source_moe_then_rss_v1"
    result["population_universe"] = "total_population"
    result["target_chamber"] = partition["target_chamber"]
    result["target_plan_id"] = partition["target_plan_id"]
    result["target_plan_reference_vintage"] = partition["target_plan_reference_vintage"]
    result["method_id"] = REGIME_METHODS[partition["support_regime"]]
    result["uncertainty"] = partition["uncertainty"]
    return result[
        [
            "population_product_id",
            "source_estimate_metric_id",
            "source_moe_metric_id",
            "moe_confidence_level",
            "moe_aggregation_method",
            "population_universe",
            "target_chamber",
            "target_plan_id",
            "target_plan_reference_vintage",
            "target_district_id",
            "estimate",
            "margin_of_error",
            "contributing_source_block_groups",
            "method_id",
            "uncertainty",
        ]
    ]


def profile_crosswalk(
    regime: str,
    plan_id: str,
    crosswalk: pd.DataFrame,
    diagnostics: dict[str, object],
    path: str,
    crosswalk_hash: str,
) -> dict[str, object]:
    assigned = crosswalk[crosswalk["assignment_status"].eq("assigned")]
    sums = assigned.groupby("source_geography_id")["weight"].sum()
    return {
        "support_regime": regime,
        "target_plan_id": plan_id,
        "target_chamber": str(crosswalk["target_chamber"].iloc[0]),
        "target_plan_reference_vintage": str(
            crosswalk["target_plan_reference_vintage"].iloc[0]
        ),
        "method_id": str(crosswalk["method_id"].iloc[0]),
        "weighting_universe": str(crosswalk["weighting_universe"].iloc[0]),
        "source_geographies": int(crosswalk["source_geography_id"].nunique()),
        "allocation_rows": len(crosswalk),
        "fallback_source_geographies": int(
            crosswalk.loc[
                ~crosswalk["fallback_basis"].eq("none"), "source_geography_id"
            ].nunique()
        ),
        "typed_exception_source_geographies": int(
            crosswalk.loc[
                ~crosswalk["assignment_status"].eq("assigned"),
                "source_geography_id",
            ].nunique()
        ),
        "maximum_weight_sum_delta": float(sums.sub(1).abs().max()),
        "nearest_assignment_count": int(crosswalk["nearest_assignment_used"].sum()),
        "uses_precinct_input": False,
        "crosswalk_path": path,
        "crosswalk_logical_sha256": crosswalk_hash,
        "diagnostics": diagnostics,
    }


def profile_partition(
    partition: dict[str, object],
    population: pd.DataFrame,
    crosswalk: pd.DataFrame,
    result: pd.DataFrame,
    crosswalk_profile: dict[str, object],
) -> dict[str, object]:
    source_total = float(population["B01003_001E"].sum())
    exception_ids = set(
        crosswalk.loc[
            ~crosswalk["assignment_status"].eq("assigned"), "source_geography_id"
        ]
    )
    exception_population = population[
        population["source_block_group_geoid"].isin(exception_ids)
    ]
    return {
        **partition,
        "source_block_groups": len(population),
        "source_estimate": source_total,
        "allocated_estimate": float(result["estimate"].sum()),
        "district_count": int(result["target_district_id"].nunique()),
        "moe_complete_nonnegative": bool(
            result["margin_of_error"].notna().all()
            and result["margin_of_error"].ge(0).all()
        ),
        "typed_exception_source_geographies": len(exception_ids),
        "typed_exception_estimate": float(exception_population["B01003_001E"].sum()),
        "typed_exception_source_moe_linear_sum": float(
            exception_population["B01003_001M"].sum()
        ),
        "result_logical_sha256": logical_frame_hash(
            result, ["target_plan_id", "target_district_id"]
        ),
        "crosswalk_logical_sha256": crosswalk_profile["crosswalk_logical_sha256"],
        "crosswalk_path": crosswalk_profile["crosswalk_path"],
        "crosswalk_allocation_rows": len(crosswalk),
        "fallback_source_geographies": crosswalk_profile["fallback_source_geographies"],
        "maximum_weight_sum_delta": crosswalk_profile["maximum_weight_sum_delta"],
        "nearest_assignment_count": crosswalk_profile["nearest_assignment_count"],
        "uses_precinct_input": False,
        "method_id": REGIME_METHODS[partition["support_regime"]],
        "weighting_universe": REGIME_WEIGHTING_UNIVERSES[partition["support_regime"]],
        "fallback_policy": (
            "none"
            if partition["support_regime"].startswith("simple_")
            else "zero 2010 population support uses normalized block-group area"
        ),
    }


def partition_checks(profile: dict[str, object]) -> list[dict[str, object]]:
    prefix = f"{profile['population_product_id']}:{profile['target_plan_id']}"
    return [
        check(
            f"{prefix}:district_count",
            profile["district_count"] == profile["expected_district_count"],
            profile["district_count"],
        ),
        check(
            f"{prefix}:estimate_conserved",
            abs(profile["allocated_estimate"] - profile["source_estimate"])
            <= RESULT_TOLERANCE,
            profile["allocated_estimate"] - profile["source_estimate"],
        ),
        check(
            f"{prefix}:weights_sum_to_one",
            profile["maximum_weight_sum_delta"] <= WEIGHT_TOLERANCE,
            profile["maximum_weight_sum_delta"],
        ),
        check(
            f"{prefix}:moe_complete_nonnegative",
            profile["moe_complete_nonnegative"],
            profile["moe_complete_nonnegative"],
        ),
        check(
            f"{prefix}:typed_exceptions_zero_estimate",
            profile["typed_exception_estimate"] == 0,
            profile["typed_exception_estimate"],
        ),
        check(
            f"{prefix}:no_precinct_input",
            not profile["uses_precinct_input"],
            profile["uses_precinct_input"],
        ),
        check(
            f"{prefix}:no_nearest_assignment",
            profile["nearest_assignment_count"] == 0,
            profile["nearest_assignment_count"],
        ),
    ]


def build_acs_manifest(root: Path) -> dict[str, object]:
    """Freeze accepted upstream evidence and reverify raw ACS source hashes."""
    upstream_paths = [
        "artifacts/poc011/input_manifest.json",
        "artifacts/poc028/input_manifest.json",
        "artifacts/poc029/plan_input_manifest.json",
        "artifacts/poc029/decennial_input_manifest.json",
        "mappings/acs5_products.csv",
        PARTITION_MAPPING_PATH,
    ]
    upstream = []
    for relative_path in upstream_paths:
        path = root / relative_path
        upstream.append(
            {
                "relative_path": relative_path,
                "sha256": sha256(path),
                "last_modified_timestamp": datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ).isoformat(),
            }
        )
    accepted_manifest = json.loads(
        (root / "artifacts/poc029/acs_input_manifest.json").read_text()
    )
    sources = []
    for source in accepted_manifest["verified_source_files"]:
        path = root / source["relative_path"]
        canonical = {
            key: value for key, value in source.items() if key != "observed_sha256"
        }
        sources.append({**canonical, "observed_sha256": sha256(path)})
    return {
        "manifest_version": "1.0.0",
        "upstream_accepted_evidence": upstream,
        "verified_source_files": sources,
    }


def require_manifest_hashes(manifest: dict[str, object]) -> None:
    failures = [
        source["relative_path"]
        for source in manifest["verified_source_files"]
        if source["sha256"] != source["observed_sha256"]
    ]
    if failures:
        raise RuntimeError(f"POC029 ACS source checksum mismatch: {failures}")


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(qa: dict[str, object]) -> str:
    rows = []
    for profile in qa["profiles"]:
        rows.append(
            f"| {profile['population_product_id']} | {profile['target_chamber']} | "
            f"{profile['target_plan_reference_vintage']} | "
            f"{profile['district_count']} | {profile['allocated_estimate']:.6f} | "
            f"{profile['fallback_source_geographies']} |"
        )
    return f"""# POC029 direct ACS legislative partitions

Status: **{"PASS" if qa["passed"] else "FAIL"}**

| Product | Chamber | Plan vintage | Districts | Estimate | Fallback groups |
|---|---|---:|---:|---:|---:|
{chr(10).join(rows)}

All {qa["partition_count"]} product/plan/chamber partitions operate directly on
official legislative plans and contain no precinct identity or precinct input.
Estimates and 90% MOEs remain separate. Target MOEs use weighted source
components combined by root-sum-square and omit covariance and allocation-weight
uncertainty.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC029 direct ACS stage passed: {qa['passed']}")


if __name__ == "__main__":
    main()
