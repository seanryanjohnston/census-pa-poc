"""Produce the POC013 statewide Census 1990 fixed-geography proof."""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from census_pa_poc.senate_overlay import logical_geoframe_hash
from census_pa_poc.sources import (
    load_1990_2000_block_relationship,
    load_1990_stf1b_block_population,
    load_1990_tiger_blocks_and_faces,
    load_2000_census_blocks,
    sha256,
)
from census_pa_poc.statewide_2010 import (
    AREA_CRS,
    POPULATION_TOLERANCE,
    WEIGHT_TOLERANCE,
    build_direct_atomic_crosswalk,
    check,
    comparison_summary,
    normalize_crosswalk_dtypes,
    source_counties_conserved,
    source_county_max_delta,
)
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

EXPECTED = {
    "source_blocks": 310_668,
    "population": 11_881_643,
    "housing_units": 4_938_140,
    "tiger_block_codes": 316_150,
    "tiger_faces": 480_773,
    "population_tiger_faces": 471_257,
    "relationship_rows": 394_566,
    "population_relationship_rows": 386_723,
    "relationship_sources": 316_159,
    "relationship_targets": 322_424,
    "fixed_precincts": 9_178,
    "senate_districts": 50,
    "counties": 67,
    "internal_point_ties": 2,
    "direct_zero_population_exceptions": 2,
}

DIRECT_METHOD = "direct_atomic_area_1990_v1"
RELATIONSHIP_METHOD = "relationship_tiger_face_area_1990_v1"

SOURCES = {
    "census_population": {
        "source_id": "census_1990_pa_stf1b_header",
        "producer": "U.S. Census Bureau",
        "product": "1990 Census STF 1B Pennsylvania geographic headers",
        "reference_vintage": "1990-04-01",
        "effective_vintage": "1990-04-01",
        "release_date": "1991; exact Pennsylvania release date not established",
        "url": ("https://www2.census.gov/census_1990/STF1B_ASCII/STF1B-PAh.zip"),
        "sha256": "9821d1a7d10d2065661d7174695e10d5b3624651c2b7dbcf8b8ab3d4accfd6d4",
        "license_access": "Public federal data; cite U.S. Census Bureau",
        "crs": None,
        "schema": {
            "format": "300-character fixed-width geographic-header records",
            "member": "STF1BHPA.F01",
            "block_summary_level": "100",
            "metric": "POP100 positions 291-299",
        },
        "geographic_universe": "1990 Census tabulation blocks in Pennsylvania",
        "population_universe": "Standard total population, POP100",
        "relative_path": "data/raw/census_1990_pa_stf1b/STF1B-PAh.zip",
    },
    "tiger_collection": {
        "source_id": "census_2000_tiger_pa_with_1990_codes",
        "producer": "U.S. Census Bureau",
        "product": "Census 2000 TIGER/Line Pennsylvania county files",
        "reference_vintage": "1990/2000",
        "effective_vintage": "Census 2000 topology carrying 1990 block codes",
        "release_date": "2001-06 county-member timestamps",
        "url_template": ("https://www2.census.gov/geo/tiger/tiger2k/pa/{filename}"),
        "collection_sha256": (
            "559b219b8700c4b95d84fd64531463b798ec4d43945190ca44b3128b77ce2666"
        ),
        "license_access": "Public federal data; acknowledge U.S. Census Bureau",
        "crs": "EPSG:4269 (NAD83; coordinates have six implied decimals)",
        "schema": {
            "format": "67 county ZIP archives of fixed-width TIGER/Line records",
            "geometry_records": ["RT1", "RT2", "RTI", "RTP"],
            "1990_block_record": "RTA",
            "2000_block_record": "RTS",
        },
        "geographic_universe": "Pennsylvania TIGER GT-polygons and block codes",
        "population_universe": None,
        "relative_path": "data/raw/census_2000_tiger_pa",
        "pattern": "tgr42*.zip",
    },
    "published_relationship_collection": {
        "source_id": "census_1990_2000_block_relationship_pa",
        "producer": "U.S. Census Bureau",
        "product": "1990 tabulation block to Census 2000 tabulation block files",
        "reference_vintage": "1990/2000",
        "effective_vintage": "comparability support product",
        "release_date": "2001-06-15 directory publication",
        "url_template": (
            "https://www2.census.gov/geo/relfiles/t9t2/st42_pennsylvania/{filename}"
        ),
        "collection_sha256": (
            "2844c2604b2676068e858a0b234aa74f94ce25a3b7d3fab04715a7170676328f"
        ),
        "license_access": "Public federal data; acknowledge U.S. Census Bureau",
        "crs": None,
        "schema": {
            "format": "67 county comma-delimited files without headers",
            "fields": "1990 block, part flag, 2000 block, part flag",
            "published_area_or_population_weights": False,
        },
        "geographic_universe": "Pennsylvania 1990/2000 tabulation-block pairs",
        "population_universe": None,
        "relative_path": "data/raw/census_1990_2000_block_relationship_pa",
        "pattern": "t9t242*.txt",
    },
    "census_2000_blocks": {
        "source_id": "census_2000_pa_blocks",
        "producer": "U.S. Census Bureau",
        "product": "2010 TIGER/Line Census 2000 Pennsylvania tabulation blocks",
        "reference_vintage": "2000",
        "effective_vintage": "Census 2000 tabulation geography",
        "release_date": "2011-01-13 archive timestamp",
        "url": (
            "https://www2.census.gov/geo/tiger/TIGER2010/TABBLOCK/2000/"
            "tl_2010_42_tabblock00.zip"
        ),
        "sha256": "a5771874f846018ddf7d3761939a8e9cd3ecdf8d34364caa53e84630707c85dc",
        "license_access": "Public federal data; acknowledge U.S. Census Bureau",
        "crs": "EPSG:4269",
        "schema": {"format": "ESRI Shapefile", "id": "BLKIDFP00"},
        "geographic_universe": "Census 2000 tabulation blocks in Pennsylvania",
        "population_universe": None,
        "relative_path": "data/raw/census_2000_pa_blocks/tl_2010_42_tabblock00.zip",
    },
}

OVERLAY = {
    "artifact_id": "pa_senate_1981_plan_fixed_precinct_overlay_v3",
    "producer": "POC022",
    "product": "Fixed 2021 LRC precinct to 1981 Senate geometry overlay",
    "source_precinct_dataset_id": "pa_lrc_2021_release_1b_geography",
    "source_precinct_effective_vintage": "2021-10-05",
    "target_senate_plan_id": "pa_senate_1981_plan",
    "target_senate_plan_reference_vintage": "1981",
    "method_id": "fixed_precinct_senate_overlay_v3",
    "weighting_universe": "EPSG:5070 fixed precinct polygon area",
    "logical_sha256": "a68f672233c092ea3b24de2d67c12c5be60c5ec13ed653f66bc4a2e27a3524c2",
    "relative_path": (
        "data/processed/senate_overlays/"
        "pa_senate_1981_plan_fixed_precinct_overlay_v3.parquet"
    ),
}


def run(root: Path) -> dict[str, object]:
    """Execute POC013 from frozen legacy inputs through two allocations."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc013"
    processed_dir = root / "data/processed/statewide_1990"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    require_manifest_hashes(manifest)

    population = load_1990_stf1b_block_population(
        root / SOURCES["census_population"]["relative_path"]
    )
    relationship = load_1990_2000_block_relationship(
        root / SOURCES["published_relationship_collection"]["relative_path"]
    )
    tiger_blocks_all, tiger_faces = load_1990_tiger_blocks_and_faces(
        root / SOURCES["tiger_collection"]["relative_path"]
    )
    tiger_blocks = tiger_blocks_all[
        tiger_blocks_all["source_block_geoid"].isin(population["source_block_geoid"])
    ].copy()
    blocks_2000 = load_2000_census_blocks(
        root / SOURCES["census_2000_blocks"]["relative_path"]
    )
    atoms = gpd.read_parquet(root / OVERLAY["relative_path"])[
        ["target_precinct_geoid", "senate_district", "geometry"]
    ]

    direct_input = tiger_blocks.rename(columns={"source_block_geoid": "GEOID10"})
    direct, direct_diagnostics = build_direct_atomic_crosswalk(direct_input, atoms)
    direct = apply_crosswalk_metadata(direct, DIRECT_METHOD)
    direct = add_zero_population_exceptions(direct, population)
    direct_diagnostics.update(
        direct_population_coverage_diagnostics(
            tiger_blocks, direct, population, direct_diagnostics
        )
    )

    source_to_2000, relationship_diagnostics = build_tiger_face_weights(
        tiger_blocks,
        tiger_faces,
        population,
        relationship,
    )
    target_2000, target_diagnostics = build_2000_atomic_bridge(blocks_2000, atoms)
    related, composition_diagnostics = build_relationship_atomic_crosswalk(
        source_to_2000, target_2000
    )
    related = apply_crosswalk_metadata(related, RELATIONSHIP_METHOD)
    related = add_zero_population_exceptions(related, population)
    relationship_diagnostics["target_2000_atomic"] = target_diagnostics
    relationship_diagnostics["composition"] = composition_diagnostics

    crosswalks = pd.concat([direct, related], ignore_index=True)
    crosswalks = crosswalks.sort_values(
        [
            "method_id",
            "source_block_geoid",
            "target_precinct_geoid",
            "senate_district",
        ],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    crosswalks = normalize_crosswalk_dtypes(crosswalks)

    precinct_result, senate_result = aggregate_results(population, crosswalks)
    precinct_comparison = compare_results(precinct_result, "target_precinct_geoid")
    senate_comparison = compare_results(senate_result, "senate_district")
    checks = build_checks(
        population,
        relationship,
        tiger_blocks_all,
        tiger_blocks,
        tiger_faces,
        atoms,
        crosswalks,
        precinct_result,
        senate_result,
        direct_diagnostics,
        relationship_diagnostics,
    )

    writes = {
        "atomic_crosswalks": write_immutable_parquet(
            crosswalks,
            processed_dir / "block_to_fixed_precinct_1981_senate_v1.parquet",
            [
                "method_id",
                "source_block_geoid",
                "target_precinct_geoid",
                "senate_district",
            ],
        ),
        "precinct_population": write_immutable_parquet(
            precinct_result,
            processed_dir / "fixed_precinct_population_1990_v1.parquet",
            ["method_id", "target_precinct_geoid"],
        ),
        "senate_population": write_immutable_parquet(
            senate_result,
            processed_dir / "senate_population_1990_1981_plan_v1.parquet",
            ["method_id", "senate_district"],
        ),
        "precinct_method_comparison": write_immutable_parquet(
            precinct_comparison,
            processed_dir / "precinct_method_comparison_1990_v1.parquet",
            ["target_precinct_geoid"],
        ),
        "senate_method_comparison": write_immutable_parquet(
            senate_comparison,
            processed_dir / "senate_method_comparison_1990_v1.parquet",
            ["senate_district"],
        ),
    }
    qa = {
        "task": "POC013",
        "direct_method_id": DIRECT_METHOD,
        "relationship_method_id": RELATIONSHIP_METHOD,
        "area_crs": AREA_CRS,
        "weight_tolerance": WEIGHT_TOLERANCE,
        "population_tolerance": POPULATION_TOLERANCE,
        "direct_diagnostics": direct_diagnostics,
        "relationship_diagnostics": relationship_diagnostics,
        "comparison": comparison_summary(precinct_comparison, senate_comparison),
        "checks": checks,
        "artifact_writes": writes,
        "hashes": {
            "atomic_crosswalks": logical_frame_hash(
                crosswalks,
                [
                    "method_id",
                    "source_block_geoid",
                    "target_precinct_geoid",
                    "senate_district",
                ],
            ),
            "precinct_population": logical_frame_hash(
                precinct_result, ["method_id", "target_precinct_geoid"]
            ),
            "senate_population": logical_frame_hash(
                senate_result, ["method_id", "senate_district"]
            ),
            "precinct_method_comparison": logical_frame_hash(
                precinct_comparison, ["target_precinct_geoid"]
            ),
            "senate_method_comparison": logical_frame_hash(
                senate_comparison, ["senate_district"]
            ),
        },
        "nearest_assignment_count": 0,
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(render_report(qa))
    if not qa["passed"]:
        raise RuntimeError("POC013 QA failed; inspect artifacts/poc013/qa_results.json")
    return qa


def build_tiger_face_weights(
    blocks: gpd.GeoDataFrame,
    faces: gpd.GeoDataFrame,
    population: pd.DataFrame,
    relationship: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Derive 1990-to-2000 area weights from identical TIGER GT faces."""
    source_ids = set(population["source_block_geoid"])
    relevant = faces[
        faces["source_block_geoid"].isin(source_ids)
        & faces["target_2000_block_geoid"].notna()
    ].copy()
    projected = relevant.to_crs(AREA_CRS)
    projected["tiger_face_area_square_meters"] = projected.geometry.area
    grouped = projected.groupby(
        ["source_block_geoid", "target_2000_block_geoid"], as_index=False
    )["tiger_face_area_square_meters"].sum()
    source_covered_area = grouped.groupby("source_block_geoid")[
        "tiger_face_area_square_meters"
    ].transform("sum")
    grouped["relationship_weight"] = (
        grouped["tiger_face_area_square_meters"] / source_covered_area
    )

    published = relationship[relationship["source_block_geoid"].isin(source_ids)][
        ["source_block_geoid", "target_2000_block_geoid"]
    ].drop_duplicates()
    derived_pairs = set(
        map(
            tuple,
            grouped[["source_block_geoid", "target_2000_block_geoid"]].itertuples(
                index=False, name=None
            ),
        )
    )
    published_pairs = set(map(tuple, published.itertuples(index=False, name=None)))
    block_area = blocks.to_crs(AREA_CRS).set_index("source_block_geoid").geometry.area
    grouped_area = grouped.groupby("source_block_geoid")[
        "tiger_face_area_square_meters"
    ].sum()
    coverage = grouped_area / block_area.reindex(grouped_area.index)
    weight_sums = grouped.groupby("source_block_geoid")["relationship_weight"].sum()
    diagnostics = {
        "raw_tiger_face_rows": len(faces),
        "population_tiger_face_rows": len(relevant),
        "derived_pair_rows": len(grouped),
        "published_population_pair_rows": len(published),
        "derived_pairs_not_published": len(derived_pairs - published_pairs),
        "published_pairs_not_derived": len(published_pairs - derived_pairs),
        "source_blocks": int(grouped["source_block_geoid"].nunique()),
        "target_2000_blocks": int(grouped["target_2000_block_geoid"].nunique()),
        "minimum_source_geometry_coverage": float(coverage.min()),
        "maximum_source_geometry_coverage": float(coverage.max()),
        "maximum_weight_sum_delta": float(weight_sums.sub(1).abs().max()),
        "published_area_or_population_weights": False,
        "weighting_universe": (
            "EPSG:5070 area of identical Census 2000 TIGER GT faces carrying "
            "both 1990 and 2000 tabulation-block codes"
        ),
        "nearest_assignment_count": 0,
    }
    return grouped, diagnostics


def build_2000_atomic_bridge(
    blocks: gpd.GeoDataFrame, atoms: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build a geometry-only 2000-block to fixed-precinct/Senate bridge."""
    direct_input = blocks.rename(columns={"BLKIDFP00": "GEOID10"})
    frame, diagnostics = build_direct_atomic_crosswalk(direct_input, atoms)
    frame = frame.rename(
        columns={
            "source_block_geoid": "target_2000_block_geoid",
            "weight": "target_atomic_weight",
            "intersection_area_square_meters": "target_atomic_area_square_meters",
        }
    )
    return frame[
        [
            "target_2000_block_geoid",
            "target_precinct_geoid",
            "senate_district",
            "target_atomic_area_square_meters",
            "target_atomic_weight",
        ]
    ], diagnostics


def build_relationship_atomic_crosswalk(
    source_to_2000: pd.DataFrame, target_2000: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Compose same-topology 1990/2000 area with 2000 atomic target area."""
    joined = source_to_2000.merge(
        target_2000,
        on="target_2000_block_geoid",
        how="left",
        validate="many_to_many",
        indicator=True,
    )
    missing = joined[joined["_merge"].eq("left_only")]
    supported = joined[joined["_merge"].eq("both")].copy()
    supported["composed_weight"] = (
        supported["relationship_weight"] * supported["target_atomic_weight"]
    )
    grouped = supported.groupby(
        ["source_block_geoid", "target_precinct_geoid", "senate_district"],
        as_index=False,
    )["composed_weight"].sum()
    source_weight = grouped.groupby("source_block_geoid")["composed_weight"].transform(
        "sum"
    )
    grouped["weight"] = grouped["composed_weight"] / source_weight
    grouped["intersection_area_square_meters"] = pd.NA
    grouped["raw_composed_weight"] = grouped["composed_weight"]
    weight_sums = grouped.groupby("source_block_geoid")["weight"].sum()
    diagnostics = {
        "joined_rows": len(joined),
        "missing_target_atomic_rows": len(missing),
        "missing_target_atomic_source_blocks": int(
            missing["source_block_geoid"].nunique()
        ),
        "assigned_source_blocks": int(grouped["source_block_geoid"].nunique()),
        "allocation_rows": len(grouped),
        "maximum_normalized_weight_delta": float(weight_sums.sub(1).abs().max()),
        "normalization": "normalized over supported composed geometry-only area",
        "nearest_assignment_count": 0,
    }
    return grouped[
        [
            "source_block_geoid",
            "target_precinct_geoid",
            "senate_district",
            "intersection_area_square_meters",
            "weight",
            "raw_composed_weight",
        ]
    ], diagnostics


def apply_crosswalk_metadata(frame: pd.DataFrame, method_id: str) -> pd.DataFrame:
    weighting = {
        DIRECT_METHOD: "direct EPSG:5070 reconstructed-1990-block intersection area",
        RELATIONSHIP_METHOD: (
            "same-topology Census 2000 TIGER 1990/2000 GT-face area composed "
            "with geometry-only 2000-block atomic area"
        ),
    }[method_id]
    return frame.assign(
        source_dataset_id="census_1990_pa_stf1b_blocks",
        source_reference_vintage="1990",
        target_precinct_dataset_id="pa_lrc_2021_release_1b_geography",
        target_precinct_effective_vintage="2021-10-05",
        target_senate_plan_id="pa_senate_1981_plan",
        target_senate_plan_reference_vintage="1981",
        method_id=method_id,
        method_version="1.0.0",
        weighting_universe=weighting,
        assignment_status="assigned",
        nearest_assignment_used=False,
    )


def add_zero_population_exceptions(
    crosswalk: pd.DataFrame, population: pd.DataFrame
) -> pd.DataFrame:
    missing = population[
        ~population["source_block_geoid"].isin(crosswalk["source_block_geoid"])
    ]
    if missing.empty:
        return crosswalk
    if not missing["P0010001"].eq(0).all():
        ids = missing.loc[missing["P0010001"].ne(0), "source_block_geoid"].tolist()
        raise ValueError(f"Material uncovered populated 1990 source blocks: {ids}")
    rows = []
    for source_id in missing["source_block_geoid"]:
        row = {column: pd.NA for column in crosswalk.columns}
        row.update(
            {
                "source_block_geoid": source_id,
                "weight": 0.0,
                "method_id": crosswalk["method_id"].iloc[0],
                "assignment_status": "zero_population_uncovered_exception",
                "nearest_assignment_used": False,
            }
        )
        rows.append(row)
    result = pd.concat([crosswalk, pd.DataFrame(rows)], ignore_index=True)
    result = apply_crosswalk_metadata(result, crosswalk["method_id"].iloc[0])
    result.loc[
        result["source_block_geoid"].isin(missing["source_block_geoid"]),
        "assignment_status",
    ] = "zero_population_uncovered_exception"
    return result


def direct_population_coverage_diagnostics(
    blocks: gpd.GeoDataFrame,
    crosswalk: pd.DataFrame,
    population: pd.DataFrame,
    diagnostics: dict[str, object],
) -> dict[str, object]:
    assigned = crosswalk[crosswalk["assignment_status"].eq("assigned")]
    covered = assigned.groupby("source_block_geoid")[
        "intersection_area_square_meters"
    ].sum()
    source_area = blocks.to_crs(AREA_CRS).set_index("source_block_geoid").geometry.area
    coverage = covered / source_area.reindex(covered.index)
    joined = population.set_index("source_block_geoid").join(
        coverage.rename("coverage"), how="left"
    )
    joined["coverage"] = joined["coverage"].fillna(0)
    implied = joined["P0010001"] * (1 - joined["coverage"]).clip(lower=0)
    point_ids = diagnostics["representative_point_uncovered_ids"]
    point_population = joined.loc[joined.index.isin(point_ids), "P0010001"].sum()
    return {
        "uncovered_source_population": int(
            joined.loc[joined["coverage"].eq(0), "P0010001"].sum()
        ),
        "representative_point_uncovered_population": int(point_population),
        "sources_below_99_percent_coverage_populated": int(
            (joined["coverage"].lt(0.99) & joined["P0010001"].gt(0)).sum()
        ),
        "population_in_sources_below_99_percent_coverage": int(
            joined.loc[
                joined["coverage"].lt(0.99) & joined["P0010001"].gt(0),
                "P0010001",
            ].sum()
        ),
        "equal_area_implied_uncovered_population": float(implied.sum()),
        "maximum_source_equal_area_implied_uncovered_population": float(implied.max()),
        "baseline_eligible_under_topology_gate": False,
        "baseline_ineligibility_reason": (
            "material later-linework coverage loss; retain as diagnostic only"
        ),
    }


def aggregate_results(
    population: pd.DataFrame, crosswalks: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    assigned = crosswalks[crosswalks["assignment_status"].eq("assigned")]
    allocated = assigned.merge(
        population[["source_block_geoid", "P0010001"]],
        on="source_block_geoid",
        how="left",
        validate="many_to_one",
    )
    allocated["allocated_population"] = allocated["P0010001"] * allocated["weight"]
    precinct = allocated.groupby(
        ["method_id", "target_precinct_geoid"], as_index=False
    )["allocated_population"].sum()
    senate = allocated.groupby(["method_id", "senate_district"], as_index=False)[
        "allocated_population"
    ].sum()
    return add_result_metadata(
        precinct.rename(columns={"allocated_population": "population"}),
        "fixed_precinct",
    ), add_result_metadata(
        senate.rename(columns={"allocated_population": "population"}),
        "state_senate_district",
    )


def add_result_metadata(frame: pd.DataFrame, geography_level: str) -> pd.DataFrame:
    return frame.assign(
        population_product_id="census_1990_pa_stf1b_header",
        population_reference_date="1990-04-01",
        population_release_date="1991",
        population_release_date_status="exact Pennsylvania release date not established",
        source_geography_id="census_1990_pa_tiger_blocks",
        source_reference_vintage="1990",
        target_snapshot_id="pa_lrc_2021_release_1b_geography",
        target_effective_vintage="2021-10-05",
        senate_plan_id="pa_senate_1981_plan",
        senate_plan_reference_vintage="1981",
        general_election_date=pd.NA,
        election_pairing_status="unpaired_geography_product_poc013",
        applicable_general_elections="1990",
        geography_level=geography_level,
        metric="POP100",
        population_universe="standard_total_population",
    )


def compare_results(frame: pd.DataFrame, geography_id: str) -> pd.DataFrame:
    pivot = frame.pivot(index=geography_id, columns="method_id", values="population")
    pivot = pivot.reset_index()
    pivot["delta_direct_minus_relationship"] = (
        pivot[DIRECT_METHOD] - pivot[RELATIONSHIP_METHOD]
    )
    return pivot.sort_values(geography_id).reset_index(drop=True)


def validate_method_crosswalk(
    frame: pd.DataFrame, population: pd.DataFrame, method_id: str
) -> list[dict[str, object]]:
    method = frame[frame["method_id"].eq(method_id)]
    assigned = method[method["assignment_status"].eq("assigned")]
    exceptions = method[
        method["assignment_status"].eq("zero_population_uncovered_exception")
    ]
    weight_sums = assigned.groupby("source_block_geoid")["weight"].sum()
    positive_ids = set(
        population.loc[population["P0010001"].gt(0), "source_block_geoid"]
    )
    zero_ids = set(population.loc[population["P0010001"].eq(0), "source_block_geoid"])
    assigned_ids = set(assigned["source_block_geoid"])
    exception_ids = set(exceptions["source_block_geoid"])
    return [
        check(
            f"{method_id}_all_source_rows_or_exceptions",
            method["source_block_geoid"].nunique() == EXPECTED["source_blocks"],
            int(method["source_block_geoid"].nunique()),
        ),
        check(
            f"{method_id}_all_positive_sources_assigned",
            positive_ids.issubset(assigned_ids),
            len(positive_ids - assigned_ids),
        ),
        check(
            f"{method_id}_exceptions_zero_population",
            exception_ids.issubset(zero_ids),
            {
                "exceptions": len(exception_ids),
                "nonzero": len(exception_ids - zero_ids),
            },
        ),
        check(
            f"{method_id}_weights_in_range",
            bool(assigned["weight"].between(0, 1, inclusive="both").all()),
            int((~assigned["weight"].between(0, 1, inclusive="both")).sum()),
        ),
        check(
            f"{method_id}_weights_sum_to_one",
            bool(weight_sums.sub(1).abs().le(WEIGHT_TOLERANCE).all()),
            float(weight_sums.sub(1).abs().max()),
        ),
        check(
            f"{method_id}_all_precincts_supported",
            assigned["target_precinct_geoid"].nunique() == EXPECTED["fixed_precincts"],
            int(assigned["target_precinct_geoid"].nunique()),
        ),
        check(
            f"{method_id}_all_senate_districts_supported",
            assigned["senate_district"].nunique() == EXPECTED["senate_districts"],
            int(assigned["senate_district"].nunique()),
        ),
    ]


def build_checks(
    population: pd.DataFrame,
    relationship: pd.DataFrame,
    tiger_blocks_all: gpd.GeoDataFrame,
    tiger_blocks: gpd.GeoDataFrame,
    tiger_faces: gpd.GeoDataFrame,
    atoms: gpd.GeoDataFrame,
    crosswalks: pd.DataFrame,
    precinct_result: pd.DataFrame,
    senate_result: pd.DataFrame,
    direct_diagnostics: dict[str, object],
    relationship_diagnostics: dict[str, object],
) -> list[dict[str, object]]:
    source_ids = set(population["source_block_geoid"])
    geometry_ids = set(tiger_blocks_all["source_block_geoid"])
    population_relationship = relationship[
        relationship["source_block_geoid"].isin(source_ids)
    ]
    checks = [
        check(
            "source_block_count",
            len(population) == EXPECTED["source_blocks"],
            len(population),
        ),
        check(
            "source_block_ids_unique",
            population["source_block_geoid"].is_unique,
            int(population["source_block_geoid"].duplicated().sum()),
        ),
        check(
            "source_population_present",
            population["P0010001"].notna().all(),
            int(population["P0010001"].isna().sum()),
        ),
        check(
            "state_population",
            int(population["P0010001"].sum()) == EXPECTED["population"],
            int(population["P0010001"].sum()),
        ),
        check(
            "state_housing_units",
            int(population["HU100"].sum()) == EXPECTED["housing_units"],
            int(population["HU100"].sum()),
        ),
        check(
            "source_counties",
            population["source_block_geoid"].str.slice(2, 5).nunique()
            == EXPECTED["counties"],
            int(population["source_block_geoid"].str.slice(2, 5).nunique()),
        ),
        check(
            "tiger_block_code_count",
            len(tiger_blocks_all) == EXPECTED["tiger_block_codes"],
            len(tiger_blocks_all),
        ),
        check(
            "all_population_blocks_have_geometry",
            source_ids.issubset(geometry_ids),
            len(source_ids - geometry_ids),
        ),
        check(
            "population_geometry_count",
            len(tiger_blocks) == EXPECTED["source_blocks"],
            len(tiger_blocks),
        ),
        check(
            "population_geometry_valid",
            bool(tiger_blocks.geometry.is_valid.all()),
            int((~tiger_blocks.geometry.is_valid).sum()),
        ),
        check(
            "population_geometry_nonempty",
            bool((~tiger_blocks.geometry.is_empty).all()),
            int(tiger_blocks.geometry.is_empty.sum()),
        ),
        check(
            "tiger_face_count",
            len(tiger_faces) == EXPECTED["tiger_faces"],
            len(tiger_faces),
        ),
        check(
            "population_tiger_face_count",
            relationship_diagnostics["population_tiger_face_rows"]
            == EXPECTED["population_tiger_faces"],
            relationship_diagnostics["population_tiger_face_rows"],
        ),
        check(
            "internal_point_tie_count",
            int(tiger_blocks_all["TIGER_INTERNAL_POINT_MATCH_COUNT"].gt(1).sum())
            == EXPECTED["internal_point_ties"],
            int(tiger_blocks_all["TIGER_INTERNAL_POINT_MATCH_COUNT"].gt(1).sum()),
        ),
        check(
            "relationship_row_count",
            len(relationship) == EXPECTED["relationship_rows"],
            len(relationship),
        ),
        check(
            "relationship_source_count",
            relationship["source_block_geoid"].nunique()
            == EXPECTED["relationship_sources"],
            int(relationship["source_block_geoid"].nunique()),
        ),
        check(
            "relationship_target_count",
            relationship["target_2000_block_geoid"].nunique()
            == EXPECTED["relationship_targets"],
            int(relationship["target_2000_block_geoid"].nunique()),
        ),
        check(
            "population_relationship_row_count",
            len(population_relationship) == EXPECTED["population_relationship_rows"],
            len(population_relationship),
        ),
        check(
            "tiger_faces_exactly_reproduce_published_pairs",
            relationship_diagnostics["derived_pairs_not_published"] == 0
            and relationship_diagnostics["published_pairs_not_derived"] == 0,
            {
                "derived_only": relationship_diagnostics["derived_pairs_not_published"],
                "published_only": relationship_diagnostics[
                    "published_pairs_not_derived"
                ],
            },
        ),
        check(
            "relationship_all_source_blocks",
            relationship_diagnostics["source_blocks"] == EXPECTED["source_blocks"],
            relationship_diagnostics["source_blocks"],
        ),
        check(
            "relationship_source_geometry_conserved",
            abs(relationship_diagnostics["minimum_source_geometry_coverage"] - 1)
            <= WEIGHT_TOLERANCE
            and abs(relationship_diagnostics["maximum_source_geometry_coverage"] - 1)
            <= WEIGHT_TOLERANCE,
            {
                "minimum": relationship_diagnostics["minimum_source_geometry_coverage"],
                "maximum": relationship_diagnostics["maximum_source_geometry_coverage"],
            },
        ),
        check(
            "relationship_composition_all_sources",
            relationship_diagnostics["composition"]["assigned_source_blocks"]
            == EXPECTED["source_blocks"],
            relationship_diagnostics["composition"]["assigned_source_blocks"],
        ),
        check(
            "relationship_composition_no_missing_target",
            relationship_diagnostics["composition"]["missing_target_atomic_rows"] == 0,
            relationship_diagnostics["composition"]["missing_target_atomic_rows"],
        ),
        check(
            "fixed_precinct_count",
            atoms["target_precinct_geoid"].nunique() == EXPECTED["fixed_precincts"],
            int(atoms["target_precinct_geoid"].nunique()),
        ),
        check(
            "senate_district_count",
            atoms["senate_district"].nunique() == EXPECTED["senate_districts"],
            int(atoms["senate_district"].nunique()),
        ),
        check(
            "direct_zero_population_exception_count",
            direct_diagnostics["uncovered_source_blocks"]
            == EXPECTED["direct_zero_population_exceptions"]
            and direct_diagnostics["uncovered_source_population"] == 0,
            {
                "blocks": direct_diagnostics["uncovered_source_blocks"],
                "population": direct_diagnostics["uncovered_source_population"],
            },
        ),
        check(
            "direct_material_gap_retained_as_diagnostic",
            direct_diagnostics["baseline_eligible_under_topology_gate"] is False
            and direct_diagnostics["equal_area_implied_uncovered_population"] > 0.01,
            direct_diagnostics["equal_area_implied_uncovered_population"],
        ),
    ]
    checks.extend(validate_method_crosswalk(crosswalks, population, DIRECT_METHOD))
    checks.extend(
        validate_method_crosswalk(crosswalks, population, RELATIONSHIP_METHOD)
    )
    for method_id in [DIRECT_METHOD, RELATIONSHIP_METHOD]:
        precinct_method = precinct_result[precinct_result["method_id"].eq(method_id)]
        senate_method = senate_result[senate_result["method_id"].eq(method_id)]
        checks.extend(
            [
                check(
                    f"{method_id}_state_precinct_population_conserved",
                    abs(precinct_method["population"].sum() - EXPECTED["population"])
                    <= POPULATION_TOLERANCE,
                    float(precinct_method["population"].sum()),
                ),
                check(
                    f"{method_id}_state_senate_population_conserved",
                    abs(senate_method["population"].sum() - EXPECTED["population"])
                    <= POPULATION_TOLERANCE,
                    float(senate_method["population"].sum()),
                ),
                check(
                    f"{method_id}_source_counties_conserved",
                    source_counties_conserved(crosswalks, population, method_id),
                    source_county_max_delta(crosswalks, population, method_id),
                ),
            ]
        )
    checks.append(
        check(
            "no_nearest_assignment",
            not crosswalks["nearest_assignment_used"].fillna(False).any(),
            int(crosswalks["nearest_assignment_used"].fillna(False).sum()),
        )
    )
    return checks


def build_manifest(root: Path) -> dict[str, object]:
    retrieved_at = datetime.now(UTC).isoformat()
    manifest_sources = []
    for source in SOURCES.values():
        item = {name: value for name, value in source.items() if name != "pattern"}
        path = root / source["relative_path"]
        if "pattern" in source:
            paths = sorted(path.glob(source["pattern"]))
            files = [
                {
                    "filename": member.name,
                    "bytes": member.stat().st_size,
                    "sha256": sha256(member),
                    "url": source["url_template"].format(filename=member.name),
                }
                for member in paths
            ]
            item["file_count"] = len(files)
            item["bytes"] = sum(file["bytes"] for file in files)
            item["observed_collection_sha256"] = collection_sha256(files)
            item["files"] = files
        else:
            item["bytes"] = path.stat().st_size
            item["observed_sha256"] = sha256(path)
        item["retrieved_at"] = retrieved_at
        manifest_sources.append(item)
    overlay_path = root / OVERLAY["relative_path"]
    overlay = dict(OVERLAY)
    overlay["observed_logical_sha256"] = logical_geoframe_hash(
        gpd.read_parquet(overlay_path),
        ["target_precinct_geoid", "senate_district"],
    )
    overlay["bytes"] = overlay_path.stat().st_size
    overlay["retrieved_at"] = retrieved_at
    return {"task": "POC013", "sources": manifest_sources, "overlay": overlay}


def collection_sha256(files: list[dict[str, object]]) -> str:
    content = "".join(f"{item['filename']}:{item['sha256']}\n" for item in files)
    return hashlib.sha256(content.encode()).hexdigest()


def require_manifest_hashes(manifest: dict[str, object]) -> None:
    for source in manifest["sources"]:
        if "collection_sha256" in source:
            if source["observed_collection_sha256"] != source["collection_sha256"]:
                raise ValueError(f"Checksum mismatch for {source['source_id']}")
        elif source["observed_sha256"] != source["sha256"]:
            raise ValueError(f"Checksum mismatch for {source['source_id']}")
    overlay = manifest["overlay"]
    if overlay["observed_logical_sha256"] != overlay["logical_sha256"]:
        raise ValueError(f"Logical checksum mismatch for {overlay['artifact_id']}")


def render_report(qa: dict[str, object]) -> str:
    comparison = qa["comparison"]
    direct = qa["direct_diagnostics"]
    related = qa["relationship_diagnostics"]
    return f"""# POC013 statewide Census 1990 result

Status: **{"passed" if qa["passed"] else "failed"}**

- Source blocks: {EXPECTED["source_blocks"]:,}
- Standard total population: {EXPECTED["population"]:,}
- Fixed 2021 LRC precincts: {EXPECTED["fixed_precincts"]:,}
- 1981-plan Senate districts: {EXPECTED["senate_districts"]}
- Reconstructed TIGER GT faces: {EXPECTED["tiger_faces"]:,}
- Published relationship rows: {EXPECTED["relationship_rows"]:,}
- Direct zero-population uncovered exceptions: {direct["uncovered_source_blocks"]}
- Direct equal-area-implied uncovered population diagnostic: {direct["equal_area_implied_uncovered_population"]:.6f}
- Relationship/published pair differences: {related["derived_pairs_not_published"]} derived-only; {related["published_pairs_not_derived"]} published-only
- Precincts with method delta: {comparison["precincts_with_nontrivial_delta"]:,}
- Precinct total absolute delta: {comparison["precinct_total_absolute_delta"]:.6f}
- Senate districts with method delta: {comparison["senate_districts_with_nontrivial_delta"]:,}
- Senate total absolute delta: {comparison["senate_total_absolute_delta"]:.6f}
- Nearest assignments: 0

The relationship-assisted baseline derives 1990-to-2000 area weights from
identical Census 2000 TIGER GT faces carrying both block codes, then composes
those weights with geometry-only 2000-block atomic area. The published
relationship file validates the exact pairs but supplies no area or population
weights. The direct reconstructed-1990 geometry route is retained only as a
diagnostic because later linework leaves material partial-coverage evidence.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(render_report(qa))


if __name__ == "__main__":
    main()
