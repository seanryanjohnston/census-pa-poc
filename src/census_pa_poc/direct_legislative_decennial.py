"""Build direct historical decennial-to-legislative partitions for POC029."""

from __future__ import annotations

import argparse
import gc
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

from census_pa_poc.direct_legislative import EXPECTED_POPULATION
from census_pa_poc.fixed_geography import load_lrc_blocks
from census_pa_poc.legislative_plans import NORMALIZED_PLAN_PATH
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
    load_pl94_block_population_statewide,
    sha256,
)
from census_pa_poc.statewide_1990 import SOURCES as SOURCES_1990
from census_pa_poc.statewide_1990 import (
    add_zero_population_exceptions as add_1990_exceptions,
)
from census_pa_poc.statewide_1990 import (
    apply_crosswalk_metadata as add_1990_metadata,
)
from census_pa_poc.statewide_1990 import (
    build_relationship_atomic_crosswalk as build_1990_relationship_crosswalk,
)
from census_pa_poc.statewide_1990 import build_tiger_face_weights
from census_pa_poc.statewide_2000 import SOURCES as SOURCES_2000
from census_pa_poc.statewide_2000 import (
    add_zero_population_exceptions as add_2000_exceptions,
)
from census_pa_poc.statewide_2000 import (
    apply_crosswalk_metadata as add_2000_metadata,
)
from census_pa_poc.statewide_2000 import (
    build_relationship_atomic_crosswalk as build_2000_relationship_crosswalk,
)
from census_pa_poc.statewide_2010 import SOURCES as SOURCES_2010
from census_pa_poc.statewide_2010 import (
    add_zero_population_exceptions as add_2010_exceptions,
)
from census_pa_poc.statewide_2010 import (
    build_relationship_atomic_crosswalk as build_2010_relationship_crosswalk,
)
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

AREA_CRS = "EPSG:5070"
MATERIAL_AREA_SQUARE_METERS = 1.0
WEIGHT_TOLERANCE = 1e-12
RESULT_TOLERANCE = 1e-6
PARTITION_MAPPING_PATH = "mappings/legislative_population_partitions_v1.csv"
EXPECTED_TOTALS = {
    "dec_1990": 11_881_643,
    "dec_2000": 12_281_054,
    "dec_2010": 12_702_379,
    "dec_2020": EXPECTED_POPULATION,
}
BRIDGE_VINTAGE = {
    "dec_1990": "2000",
    "dec_2000": "2010",
    "dec_2010": "2020",
}
METHOD_IDS = {
    "dec_1990": "relationship_tiger_face_area_direct_legislative_1990_v1",
    "dec_2000": "relationship_atomic_area_direct_legislative_2000_v1",
    "dec_2010": "relationship_atomic_area_direct_legislative_2010_v1",
    "dec_2020": "lrc_fragment_p001_direct_legislative_v1",
}
LEGAL_ASSIGNMENT_OVERRIDES = {
    ("2000", "pa_house_1991_final", "420490117011001"): {
        "target_district_id": 4,
        "basis": (
            "Official Census 2000 county-subdivision geometry places the block "
            "in North East township; the official 1991 Final legal description "
            "places North East township in State House District 4."
        ),
        "supporting_sources": {
            "1991_house_kml_sha256": (
                "10a1a82e9fde0596832d2a489879d04b268e96f82f2e6a3a9b7fa8c4dccfd816"
            ),
            "1991_final_legal_description_sha256": (
                "69fd542b47563023daa7ae03112018bd9ad81fca3a492f9a69202d71dbe8fc27"
            ),
            "census_2000_pa_cousub_sha256": (
                "687b40a0b4053115a82a8ec2a667d52009075606fec84f7eae4c3c00d0ba7ce5"
            ),
        },
    }
}
SUPPORTING_OVERRIDE_SOURCES = {
    "pa_house_1991_final_kml": {
        "producer": "Pennsylvania Legislative Reapportionment Commission",
        "product": "1991 Final State House plan KML",
        "reference_vintage": "1991",
        "effective_vintage": "used for 1992-2000 elections",
        "url": (
            "https://redistricting.state.pa.us/Resources/GISData/Districts/"
            "Legislative/House/1991/KML/PA-House-Districts-1991.kml.zip"
        ),
        "sha256": "10a1a82e9fde0596832d2a489879d04b268e96f82f2e6a3a9b7fa8c4dccfd816",
        "relative_path": (
            "data/raw/pa_house_plans/1991/PA-House-Districts-1991.kml.zip"
        ),
        "license_access": "Public official download; redistribution terms not stated",
        "crs": "EPSG:4326",
        "schema": {"format": "KML in ZIP", "member": "PA-House-Districts-1991.kml"},
        "geographic_universe": "Pennsylvania State House districts",
        "role": "independent confirmation of the published SHAPE linework gap",
    },
    "pa_house_1991_final_legal_description": {
        "producer": "Pennsylvania Legislative Reapportionment Commission",
        "product": "1991 Final House and Senate plans filed with Department of State",
        "reference_vintage": "1991",
        "effective_vintage": "used for 1992-2000 elections",
        "url": (
            "https://redistricting.state.pa.us/Resources/GISData/Districts/"
            "Legislative/House/1991/PDF/1991-11-15%20House%20and%20Senate%20"
            "Final%20Plans%20-%20Filed%20with%20DOS%20-%201026.pdf"
        ),
        "sha256": "69fd542b47563023daa7ae03112018bd9ad81fca3a492f9a69202d71dbe8fc27",
        "relative_path": (
            "data/raw/pa_house_plans/1991/1991-final-legal-description.pdf"
        ),
        "license_access": "Public official download; redistribution terms not stated",
        "crs": None,
        "schema": {"format": "77-page scanned/OCR PDF", "district": 4},
        "geographic_universe": "1991 Pennsylvania legislative plans",
        "role": "authoritative assignment of North East township to House District 4",
    },
    "census_2000_pa_county_subdivisions": {
        "producer": "U.S. Census Bureau",
        "product": "2010 TIGER/Line Census 2000 Pennsylvania county subdivisions",
        "reference_vintage": "2000",
        "effective_vintage": "Census 2000 tabulation geography",
        "url": (
            "https://www2.census.gov/geo/tiger/TIGER2010/COUSUB/2000/"
            "tl_2010_42_cousub00.zip"
        ),
        "sha256": "687b40a0b4053115a82a8ec2a667d52009075606fec84f7eae4c3c00d0ba7ce5",
        "relative_path": ("data/raw/census_2000_pa_cousub/tl_2010_42_cousub00.zip"),
        "license_access": "Public federal data; acknowledge U.S. Census Bureau",
        "crs": "EPSG:4269",
        "schema": {
            "format": "ESRI Shapefile",
            "member": "tl_2010_42_cousub00.shp",
            "name_field": "NAME00",
        },
        "geographic_universe": "Census 2000 Pennsylvania county subdivisions",
        "role": "places target block 420490117011001 in North East township",
    },
}
WEIGHTING_UNIVERSES = {
    "dec_1990": (
        "same-topology Census 2000 TIGER 1990/2000 face area composed with "
        "source-local normalized 2000-block/legislative-plan area"
    ),
    "dec_2000": (
        "official 2000-to-2010 land-plus-water relationship area composed with "
        "source-local normalized 2010-block/legislative-plan area"
    ),
    "dec_2010": (
        "official 2010-to-2020 land-plus-water relationship area composed with "
        "source-local normalized corrected-2020-block/legislative-plan area"
    ),
    "dec_2020": "published corrected-fragment P0010001 support",
}
SOURCE_GEOGRAPHY_GRAINS = {
    "dec_1990": "1990 Census block (STF 1B)",
    "dec_2000": "Census 2000 block",
    "dec_2010": "2010 Census block",
    "dec_2020": "2020 Census parent block with LRC corrected fragments",
}
FALLBACK_POLICIES = {
    "dec_1990": (
        "typed zero-population exceptions; one checksum-backed legal-description/"
        "county-subdivision override for a populated official-plan linework gap"
    ),
    "dec_2000": "typed zero-population exceptions; never nearest assignment",
    "dec_2010": "typed zero-population exceptions; never nearest assignment",
    "dec_2020": (
        "published corrected-fragment population support with atomic-area fallback "
        "only for a zero-support split parent"
    ),
}
UNCERTAINTIES = {
    "dec_1990": (
        "Same-topology TIGER face area is a geometry model, not observed "
        "within-block population."
    ),
    "dec_2000": (
        "Relationship and atomic area are geometry models, not observed "
        "within-block population."
    ),
    "dec_2010": (
        "Relationship and atomic area are geometry models, not observed "
        "within-block population."
    ),
    "dec_2020": (
        "Standard P0010001 support is valid only for this metric and cannot be "
        "generalized to another population universe."
    ),
}


def run(root: Path) -> dict[str, object]:
    """Execute and validate all 22 direct decennial partitions."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc029"
    manifest = build_decennial_manifest(root)
    require_supporting_hashes(manifest)
    write_json(artifact_dir / "decennial_input_manifest.json", manifest)
    plans = gpd.read_parquet(root / NORMALIZED_PLAN_PATH)
    partitions = build_partition_registry(root, plans)
    processed_dir = root / "data/processed/direct_legislative/poc029"
    crosswalk_dir = processed_dir / "decennial_crosswalks"
    expected_paths = [
        crosswalk_dir / f"{row.population_product_id}__{row.target_plan_id}__v1.parquet"
        for row in partitions.itertuples(index=False)
    ]
    if all(path.exists() for path in expected_paths):
        populations = load_decennial_populations(root)
        bridges = {}
    else:
        populations, bridges = load_decennial_inputs(root)

    crosswalk_profiles = []
    result_frames = []
    checks = []
    atom_cache: dict[tuple[str, str], tuple[pd.DataFrame, dict[str, object]]] = {}
    for partition in partitions.to_dict("records"):
        product_id = partition["population_product_id"]
        plan_id = partition["target_plan_id"]
        path = crosswalk_dir / (
            f"{product_id}__{partition['target_plan_id']}__v1.parquet"
        )
        if path.exists():
            crosswalk = pd.read_parquet(path)
            diagnostics = {"crosswalk_artifact": "reused_existing"}
        elif product_id == "dec_2020":
            crosswalk, diagnostics = load_accepted_2020_crosswalk(root, partition)
        else:
            key = (BRIDGE_VINTAGE[product_id], plan_id)
            if key not in atom_cache:
                plan = plans[plans["target_plan_id"].eq(plan_id)]
                atoms, atom_diagnostics = build_atomic_area_weights(
                    bridges[BRIDGE_VINTAGE[product_id]],
                    plan,
                    bridge_id_column(BRIDGE_VINTAGE[product_id]),
                )
                atom_cache[key] = apply_atomic_overrides(
                    atoms,
                    atom_diagnostics,
                    BRIDGE_VINTAGE[product_id],
                    plan_id,
                )
            atoms, atom_diagnostics = atom_cache[key]
            crosswalk, diagnostics = build_legacy_crosswalk(
                product_id,
                populations[product_id],
                bridges,
                atoms,
                partition,
            )
            diagnostics["target_atomic"] = atom_diagnostics

        validate_crosswalk(crosswalk, populations[product_id])
        result = aggregate_population(populations[product_id], crosswalk, partition)
        write_status = write_immutable_parquet(
            crosswalk,
            path,
            ["source_geography_id", "target_district_id"],
        )
        crosswalk_hash = logical_frame_hash(
            crosswalk, ["source_geography_id", "target_district_id"]
        )
        profile = profile_partition(
            partition,
            crosswalk,
            result,
            diagnostics,
            path.relative_to(root).as_posix(),
            write_status,
            crosswalk_hash,
        )
        crosswalk_profiles.append(profile)
        result_frames.append(result)
        checks.extend(partition_checks(profile))
        gc.collect()

    results = pd.concat(result_frames, ignore_index=True).sort_values(
        ["population_product_id", "target_plan_id", "target_district_id"]
    )
    result_path = processed_dir / "decennial_legislative_results_v1.parquet"
    result_write = write_immutable_parquet(
        results,
        result_path,
        ["population_product_id", "target_plan_id", "target_district_id"],
    )
    result_hash = logical_frame_hash(
        results,
        ["population_product_id", "target_plan_id", "target_district_id"],
    )
    qa = {
        "task": "POC029",
        "stage": "direct_decennial_partitions",
        "partition_count": len(partitions),
        "product_count": int(partitions["population_product_id"].nunique()),
        "chambers": sorted(partitions["target_chamber"].unique().tolist()),
        "plan_vintages": sorted(
            partitions["target_plan_reference_vintage"].unique().tolist()
        ),
        "profiles": crosswalk_profiles,
        "checks": checks,
        "artifact_writes": {"combined_results": result_write},
        "hashes": {"combined_results": result_hash},
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "decennial_qa.json", qa)
    (artifact_dir / "decennial_report.md").write_text(render_report(qa))
    if not qa["passed"]:
        raise RuntimeError("POC029 decennial stage failed; inspect decennial_qa.json")
    return qa


def build_partition_registry(root: Path, plans: gpd.GeoDataFrame) -> pd.DataFrame:
    """Expand accepted product/plan applicability to both chambers."""
    accepted = pd.read_csv(root / PARTITION_MAPPING_PATH, dtype="string")
    accepted = accepted[
        ~accepted["population_product_id"].str.startswith("acs5_")
    ]
    rows = []
    for partition in accepted.to_dict("records"):
        product_id = partition["population_product_id"]
        vintage = partition["target_plan_reference_vintage"]
        for chamber in ("house", "senate"):
            matching = plans[
                plans["target_chamber"].eq(chamber)
                & plans["target_plan_reference_vintage"].eq(vintage)
            ]
            rows.append(
                {
                    "population_product_id": product_id,
                    "source_geography_grain": SOURCE_GEOGRAPHY_GRAINS[product_id],
                    "target_chamber": chamber,
                    "target_plan_id": matching["target_plan_id"].iloc[0],
                    "target_plan_reference_vintage": vintage,
                    "first_applicable_election": partition[
                        "first_applicable_election"
                    ],
                    "last_applicable_election": partition[
                        "last_applicable_election"
                    ],
                    "expected_district_count": int(
                        matching["target_district_id"].nunique()
                    ),
                    "weighting_universe": WEIGHTING_UNIVERSES[product_id],
                    "fallback_policy": FALLBACK_POLICIES[product_id],
                    "uncertainty": UNCERTAINTIES[product_id],
                }
            )
    return pd.DataFrame(rows).sort_values(["population_product_id", "target_plan_id"])


def build_decennial_manifest(root: Path) -> dict[str, object]:
    """Link accepted upstream manifests and freeze override evidence."""
    upstream_paths = [
        "artifacts/poc013/input_manifest.json",
        "artifacts/poc012/input_manifest.json",
        "artifacts/poc011/input_manifest.json",
        "artifacts/poc028/input_manifest.json",
        "artifacts/poc029/plan_input_manifest.json",
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
    supporting = []
    for source_id, source in SUPPORTING_OVERRIDE_SOURCES.items():
        path = root / source["relative_path"]
        supporting.append(
            {
                "source_id": source_id,
                **source,
                "observed_sha256": sha256(path),
                "retrieval_timestamp": datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ).isoformat(),
                "size_bytes": path.stat().st_size,
            }
        )
    return {
        "manifest_version": "1.0.0",
        "upstream_accepted_manifests": upstream,
        "supporting_override_sources": supporting,
    }


def require_supporting_hashes(manifest: dict[str, object]) -> None:
    """Fail if any legal-override source differs from its frozen bytes."""
    failures = [
        source["source_id"]
        for source in manifest["supporting_override_sources"]
        if source["sha256"] != source["observed_sha256"]
    ]
    if failures:
        raise RuntimeError(f"POC029 override-source checksum mismatch: {failures}")


def load_decennial_inputs(
    root: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    """Load population and reusable topology bridges once."""
    populations = load_decennial_populations(root)
    pop_1990 = populations["dec_1990"]
    relationship_1990 = load_1990_2000_block_relationship(
        root / SOURCES_1990["published_relationship_collection"]["relative_path"]
    )
    blocks_all, faces = load_1990_tiger_blocks_and_faces(
        root / SOURCES_1990["tiger_collection"]["relative_path"]
    )
    blocks_1990 = blocks_all[
        blocks_all["source_block_geoid"].isin(pop_1990["source_block_geoid"])
    ]
    source_to_2000, _ = build_tiger_face_weights(
        blocks_1990, faces, pop_1990, relationship_1990
    )
    lrc = load_lrc_blocks(root / SOURCES_2010["lrc_geography"]["relative_path"])[
        ["GEOID20", "geometry"]
    ].copy()
    lrc["target_2020_block_geoid"] = lrc["GEOID20"].str.slice(0, 15)
    return (
        populations,
        {
            "2000": load_2000_census_blocks(
                root / SOURCES_1990["census_2000_blocks"]["relative_path"]
            ),
            "2010": load_2010_census_blocks(
                root / SOURCES_2000["census_2010_blocks"]["relative_path"]
            ),
            "2020": lrc,
            "source_to_2000": source_to_2000,
            "relationship_2000_2010": load_2000_2010_block_relationship(
                root / SOURCES_2000["block_relationship"]["relative_path"]
            ),
            "relationship_2010_2020": load_2010_2020_block_relationship(
                root / SOURCES_2010["block_relationship"]["relative_path"]
            ),
        },
    )


def load_decennial_populations(root: Path) -> dict[str, pd.DataFrame]:
    """Load only metric tables when every immutable crosswalk already exists."""
    return {
        "dec_1990": load_1990_stf1b_block_population(
            root / SOURCES_1990["census_population"]["relative_path"]
        ),
        "dec_2000": load_2000_pl94_block_population(
            root / SOURCES_2000["census_population_geography"]["relative_path"],
            root / SOURCES_2000["census_population_file01"]["relative_path"],
        ),
        "dec_2010": load_2010_pl94_block_population(
            root / SOURCES_2010["census_population"]["relative_path"]
        ),
        "dec_2020": load_pl94_block_population_statewide(
            root / "data/raw/census_2020_pa_pl/pa2020.pl.zip"
        ).rename(columns={"block_geoid": "source_block_geoid"}),
    }


def bridge_id_column(vintage: str) -> str:
    return {
        "2000": "BLKIDFP00",
        "2010": "GEOID10",
        "2020": "target_2020_block_geoid",
    }[vintage]


def build_atomic_area_weights(
    source: gpd.GeoDataFrame,
    plan: gpd.GeoDataFrame,
    source_id_column: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Normalize source-local plan overlaps and gaps without nearest assignment."""
    sources = source[[source_id_column, "geometry"]].copy()
    sources[source_id_column] = sources[source_id_column].astype("string")
    if source_id_column == "target_2020_block_geoid":
        sources = sources.dissolve(by=source_id_column, as_index=False)
    sources = sources.to_crs(AREA_CRS)
    targets = plan[["target_district_id", "geometry"]].to_crs(AREA_CRS)
    raw = gpd.overlay(sources, targets, how="intersection", keep_geom_type=True)
    raw = raw[~raw.geometry.is_empty].copy()
    raw["raw_area_square_meters"] = raw.geometry.area
    raw = raw[raw["raw_area_square_meters"].gt(0)]
    if raw.duplicated([source_id_column, "target_district_id"]).any():
        raise ValueError("Overlay unexpectedly returned duplicate source/district rows")
    grouped = raw[
        [source_id_column, "target_district_id", "raw_area_square_meters", "geometry"]
    ]
    source_geometry = sources.set_index(source_id_column).geometry
    district_counts = grouped.groupby(source_id_column)["target_district_id"].nunique()
    single_ids = set(district_counts[district_counts.eq(1)].index)
    single = grouped[grouped[source_id_column].isin(single_ids)][
        [source_id_column, "target_district_id"]
    ].rename(columns={source_id_column: "source_atomic_geoid"})
    single["target_atomic_area_square_meters"] = source_geometry.area.reindex(
        single["source_atomic_geoid"]
    ).to_numpy()
    single["target_atomic_weight"] = 1.0
    single["normalization_status"] = "single_intersecting_district"
    single["overlap_removed_square_meters"] = 0.0
    rows = single.to_dict("records")
    overlap_removed = 0.0
    multi = grouped[~grouped[source_id_column].isin(single_ids)]
    for source_id, group in multi.groupby(source_id_column, sort=True):
        normalized, removed = normalize_multi_district_source(group)
        overlap_removed += removed
        total = sum(item[2] for item in normalized)
        for district, status, area in normalized:
            rows.append(
                {
                    "source_atomic_geoid": source_id,
                    "target_district_id": district,
                    "target_atomic_area_square_meters": area,
                    "target_atomic_weight": area / total,
                    "normalization_status": status,
                    "overlap_removed_square_meters": removed,
                }
            )
    result = pd.DataFrame(rows).sort_values(
        ["source_atomic_geoid", "target_district_id"]
    )
    source_ids = set(sources[source_id_column])
    observed_ids = set(result["source_atomic_geoid"])
    weights = result.groupby("source_atomic_geoid")["target_atomic_weight"].sum()
    diagnostics = {
        "source_atomic_geographies": len(source_ids),
        "assigned_atomic_geographies": len(observed_ids),
        "uncovered_atomic_geographies": len(source_ids - observed_ids),
        "uncovered_atomic_ids": sorted(source_ids - observed_ids),
        "multi_district_atomic_geographies": int(district_counts.gt(1).sum()),
        "overlap_removed_square_meters": overlap_removed,
        "maximum_weight_sum_delta": float(weights.sub(1).abs().max()),
        "nearest_assignment_count": 0,
        "normalization_method_id": "source_local_plan_area_normalization_v1",
    }
    return result, diagnostics


def normalize_multi_district_source(
    group: gpd.GeoDataFrame,
) -> tuple[list[tuple[int, str, float]], float]:
    """Give overlap to the locally dominant district and remove tiny slivers."""
    entries = sorted(
        (
            int(row.target_district_id),
            row.geometry,
            float(row.raw_area_square_meters),
        )
        for row in group.itertuples()
    )
    entries.sort(key=lambda item: (-item[2], item[0]))
    assigned = shapely.GeometryCollection()
    normalized = []
    removed = 0.0
    for district, geometry, raw_area in entries:
        cleaned = shapely.difference(geometry, assigned)
        area = float(shapely.area(cleaned))
        removed += raw_area - area
        if area <= MATERIAL_AREA_SQUARE_METERS:
            continue
        status = "multi_district_area"
        if raw_area - area > MATERIAL_AREA_SQUARE_METERS:
            status = "multi_district_overlap_removed"
        normalized.append((district, status, area))
        assigned = shapely.union(assigned, cleaned)
    if not normalized:
        district, geometry, _ = entries[0]
        return [
            (district, "sub_meter_sliver_retained", float(shapely.area(geometry)))
        ], removed
    return normalized, removed


def apply_atomic_overrides(
    atoms: pd.DataFrame,
    diagnostics: dict[str, object],
    bridge_vintage: str,
    target_plan_id: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Apply only checksum-supported legal assignments for fully uncovered atoms."""
    result = atoms.copy()
    detail = dict(diagnostics)
    applied = []
    observed = set(result["source_atomic_geoid"])
    for (vintage, plan_id, source_id), override in LEGAL_ASSIGNMENT_OVERRIDES.items():
        if vintage != bridge_vintage or plan_id != target_plan_id:
            continue
        if source_id in observed:
            raise ValueError(f"Legal override is not an uncovered atom: {source_id}")
        result = pd.concat(
            [
                result,
                pd.DataFrame(
                    [
                        {
                            "source_atomic_geoid": source_id,
                            "target_district_id": override["target_district_id"],
                            "target_atomic_area_square_meters": pd.NA,
                            "target_atomic_weight": 1.0,
                            "normalization_status": (
                                "official_legal_description_cousub_override"
                            ),
                            "overlap_removed_square_meters": 0.0,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        applied.append(
            {
                "source_atomic_geoid": source_id,
                "target_district_id": override["target_district_id"],
                "basis": override["basis"],
                "supporting_sources": override["supporting_sources"],
                "nearest_assignment_used": False,
            }
        )
    detail["legal_assignment_overrides"] = applied
    detail["legal_assignment_override_count"] = len(applied)
    detail["uncovered_atomic_geographies_after_legal_overrides"] = detail[
        "uncovered_atomic_geographies"
    ] - len(applied)
    return (
        result.sort_values(["source_atomic_geoid", "target_district_id"]),
        detail,
    )


def build_legacy_crosswalk(
    product_id: str,
    population: pd.DataFrame,
    bridges: dict[str, object],
    atoms: pd.DataFrame,
    partition: dict[str, object],
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Compose the accepted relationship support directly with plan atoms."""
    adapted = adapt_atoms(atoms, product_id, partition)
    if product_id == "dec_1990":
        raw, diagnostics = build_1990_relationship_crosswalk(
            bridges["source_to_2000"], adapted
        )
        raw = add_1990_metadata(raw, "relationship_tiger_face_area_1990_v1")
        raw = add_1990_exceptions(raw, population)
    elif product_id == "dec_2000":
        raw, diagnostics = build_2000_relationship_crosswalk(
            bridges["relationship_2000_2010"], adapted, population
        )
        raw = add_2000_metadata(raw, "relationship_atomic_area_2000_v1")
        raw = add_2000_exceptions(raw, population)
    elif product_id == "dec_2010":
        raw, diagnostics = build_2010_relationship_crosswalk(
            bridges["relationship_2010_2020"],
            adapted,
            set(population["source_block_geoid"]),
        )
        raw = add_2010_exceptions(raw, population)
    else:
        raise ValueError(product_id)
    return normalize_output_crosswalk(raw, product_id, partition), diagnostics


def adapt_atoms(
    atoms: pd.DataFrame,
    product_id: str,
    partition: dict[str, object],
) -> pd.DataFrame:
    """Adapt generic plan atoms to the legacy composition function boundary."""
    identifier = {
        "dec_1990": "target_2000_block_geoid",
        "dec_2000": "target_2010_block_geoid",
        "dec_2010": "target_2020_block_geoid",
    }[product_id]
    result = atoms.rename(columns={"source_atomic_geoid": identifier}).copy()
    result["target_precinct_geoid"] = (
        partition["target_plan_id"]
        + ":"
        + result["target_district_id"].astype("string")
    )
    result["senate_district"] = result["target_district_id"].astype("int64")
    return result


def normalize_output_crosswalk(
    raw: pd.DataFrame,
    product_id: str,
    partition: dict[str, object],
) -> pd.DataFrame:
    """Remove the boundary adapter and expose only chamber-neutral identity."""
    result = raw.rename(
        columns={
            "source_block_geoid": "source_geography_id",
            "senate_district": "target_district_id",
        }
    ).copy()
    result["target_chamber"] = partition["target_chamber"]
    result["target_plan_id"] = partition["target_plan_id"]
    result["target_plan_reference_vintage"] = partition["target_plan_reference_vintage"]
    result["population_product_id"] = product_id
    result["source_metric_id"] = "P0010001" if product_id != "dec_1990" else "POP100"
    result["method_id"] = METHOD_IDS[product_id]
    result["method_version"] = "1.0.0"
    result["weighting_universe"] = WEIGHTING_UNIVERSES[product_id]
    result["fallback_basis"] = result["assignment_status"].where(
        ~result["assignment_status"].eq("assigned"), "none"
    )
    result["nearest_assignment_used"] = False
    columns = [
        "population_product_id",
        "source_geography_id",
        "source_metric_id",
        "target_chamber",
        "target_plan_id",
        "target_plan_reference_vintage",
        "target_district_id",
        "weight",
        "weighting_universe",
        "fallback_basis",
        "method_id",
        "method_version",
        "assignment_status",
        "nearest_assignment_used",
    ]
    result = result[columns]
    result["source_geography_id"] = result["source_geography_id"].astype("string")
    result["target_district_id"] = result["target_district_id"].astype("Int64")
    result["weight"] = result["weight"].astype("float64")
    return result.sort_values(["source_geography_id", "target_district_id"])


def load_accepted_2020_crosswalk(
    root: Path, partition: dict[str, object]
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Reuse the POC028 metric-specific weight product for the current plans."""
    source = pd.read_parquet(
        root / "data/processed/direct_legislative/"
        "census_2020_p001_to_2021_legislative_plan_v1.parquet"
    )
    selected = source[source["target_plan_id"].eq(partition["target_plan_id"])].copy()
    result = selected.rename(columns={"source_geography_id": "source_geography_id"})
    result["population_product_id"] = "dec_2020"
    result["source_metric_id"] = "P0010001"
    result["fallback_basis"] = result["weight_method"].where(
        result["weight_method"].str.contains("fallback"), "none"
    )
    result["method_version"] = "1.0.0"
    result["nearest_assignment_used"] = False
    result = result[
        [
            "population_product_id",
            "source_geography_id",
            "source_metric_id",
            "target_chamber",
            "target_plan_id",
            "target_plan_reference_vintage",
            "target_district_id",
            "weight",
            "weighting_universe",
            "fallback_basis",
            "method_id",
            "method_version",
            "assignment_status",
            "nearest_assignment_used",
        ]
    ]
    return result, {"accepted_poc028_crosswalk": "reused"}


def validate_crosswalk(crosswalk: pd.DataFrame, population: pd.DataFrame) -> None:
    assigned = crosswalk[crosswalk["assignment_status"].eq("assigned")]
    sums = assigned.groupby("source_geography_id")["weight"].sum()
    populated = set(population.loc[population["P0010001"].gt(0), "source_block_geoid"])
    if not populated.issubset(set(assigned["source_geography_id"])):
        raise ValueError("Direct decennial crosswalk omits populated sources")
    if sums.sub(1).abs().max() > WEIGHT_TOLERANCE:
        raise ValueError("Direct decennial crosswalk weights do not sum to one")
    if assigned["target_district_id"].isna().any():
        raise ValueError("Assigned direct decennial rows require a district")
    if any("precinct" in column for column in crosswalk.columns):
        raise ValueError("Direct legislative output cannot contain precinct identity")


def aggregate_population(
    population: pd.DataFrame,
    crosswalk: pd.DataFrame,
    partition: dict[str, object],
) -> pd.DataFrame:
    assigned = crosswalk[crosswalk["assignment_status"].eq("assigned")]
    allocated = assigned.merge(
        population,
        left_on="source_geography_id",
        right_on="source_block_geoid",
        validate="many_to_one",
    )
    allocated["population"] = allocated["P0010001"] * allocated["weight"]
    result = allocated.groupby("target_district_id", as_index=False)["population"].sum()
    result["target_district_id"] = pd.to_numeric(
        result["target_district_id"], errors="raise"
    ).astype("Int64")
    result["population_product_id"] = partition["population_product_id"]
    result["target_chamber"] = partition["target_chamber"]
    result["target_plan_id"] = partition["target_plan_id"]
    result["target_plan_reference_vintage"] = partition["target_plan_reference_vintage"]
    result["source_metric_id"] = (
        "POP100" if partition["population_product_id"] == "dec_1990" else "P0010001"
    )
    result["method_id"] = METHOD_IDS[partition["population_product_id"]]
    return result[
        [
            "population_product_id",
            "source_metric_id",
            "target_chamber",
            "target_plan_id",
            "target_plan_reference_vintage",
            "target_district_id",
            "population",
            "method_id",
        ]
    ]


def profile_partition(
    partition: dict[str, object],
    crosswalk: pd.DataFrame,
    result: pd.DataFrame,
    diagnostics: dict[str, object],
    path: str,
    write_status: str,
    crosswalk_hash: str,
) -> dict[str, object]:
    assigned = crosswalk[crosswalk["assignment_status"].eq("assigned")]
    weights = assigned.groupby("source_geography_id")["weight"].sum()
    return {
        **partition,
        "crosswalk_rows": len(crosswalk),
        "source_geographies": int(crosswalk["source_geography_id"].nunique()),
        "assigned_source_geographies": int(assigned["source_geography_id"].nunique()),
        "typed_exception_rows": int(
            (~crosswalk["assignment_status"].eq("assigned")).sum()
        ),
        "district_count": int(result["target_district_id"].nunique()),
        "population": float(result["population"].sum()),
        "maximum_weight_sum_delta": float(weights.sub(1).abs().max()),
        "nearest_assignment_count": int(crosswalk["nearest_assignment_used"].sum()),
        "uses_precinct_input": False,
        "crosswalk_path": path,
        "crosswalk_write": write_status,
        "crosswalk_logical_sha256": crosswalk_hash,
        "result_logical_sha256": logical_frame_hash(
            result, ["target_plan_id", "target_district_id"]
        ),
        "diagnostics": diagnostics,
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
            f"{prefix}:population_conserved",
            abs(
                profile["population"]
                - EXPECTED_TOTALS[profile["population_product_id"]]
            )
            <= RESULT_TOLERANCE,
            profile["population"],
        ),
        check(
            f"{prefix}:weights_sum_to_one",
            profile["maximum_weight_sum_delta"] <= WEIGHT_TOLERANCE,
            profile["maximum_weight_sum_delta"],
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


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(qa: dict[str, object]) -> str:
    rows = []
    for profile in qa["profiles"]:
        rows.append(
            f"| {profile['population_product_id']} | {profile['target_chamber']} | "
            f"{profile['target_plan_reference_vintage']} | "
            f"{profile['district_count']} | {profile['population']:.6f} | "
            f"{profile['typed_exception_rows']} |"
        )
    return f"""# POC029 direct decennial legislative partitions

Status: **{"PASS" if qa["passed"] else "FAIL"}**

| Product | Chamber | Plan vintage | Districts | Population | Typed exceptions |
|---|---|---:|---:|---:|---:|
{chr(10).join(rows)}

All {qa["partition_count"]} product/plan/chamber partitions operate directly on
official legislative plans and contain no precinct identity or precinct input.
Historical relationship support remains area-modeled and records source-local
plan overlap normalization, gaps, fallbacks, and immutable crosswalk hashes.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC029 direct decennial stage passed: {qa['passed']}")


if __name__ == "__main__":
    main()
