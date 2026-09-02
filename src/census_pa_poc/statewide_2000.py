"""Produce the POC012 statewide Census 2000 fixed-geography proof."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from census_pa_poc.senate_overlay import logical_geoframe_hash
from census_pa_poc.sources import (
    load_2000_2010_block_relationship,
    load_2000_census_blocks,
    load_2000_pl94_block_population,
    load_2010_census_blocks,
    sha256,
)
from census_pa_poc.statewide_2010 import (
    AREA_CRS,
    POPULATION_TOLERANCE,
    WEIGHT_TOLERANCE,
    build_direct_atomic_crosswalk,
    check,
    comparison_summary,
    direct_exception_population_diagnostics,
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
    "source_blocks": 322_424,
    "relationship_rows": 505_426,
    "relationship_sources": 322_424,
    "fixed_precincts": 9_178,
    "senate_districts": 50,
    "counties": 67,
    "population": 12_281_054,
}
ATOMIC_GAP_EQUAL_AREA_POPULATION_TOLERANCE = 0.01

DIRECT_METHOD = "direct_atomic_area_2000_v1"
RELATIONSHIP_METHOD = "relationship_atomic_area_2000_v1"

SOURCES = {
    "census_population_geography": {
        "source_id": "census_2000_pa_pl_geography",
        "producer": "U.S. Census Bureau",
        "product": "Census 2000 PL 94-171 Pennsylvania geography header",
        "reference_vintage": "2000-04-01",
        "effective_vintage": "2000-04-01",
        "release_date": "2001-03-09",
        "url": (
            "https://www2.census.gov/census_2000/datasets/"
            "redistricting_file--pl_94-171/Pennsylvania/pageo.upl.zip"
        ),
        "sha256": "34d4079451e3d3e1396b76287d54d0a96814de8d46059a327547b74c8ea3f672",
        "license_access": "Public federal data; cite U.S. Census Bureau",
        "crs": None,
        "schema": {
            "format": "fixed-width state geography header",
            "member": "pageo.upl",
            "block_summary_level": "750",
            "join": "LOGRECNO",
        },
        "geographic_universe": "Census 2000 tabulation blocks in Pennsylvania",
        "population_universe": None,
        "relative_path": "data/raw/census_2000_pa_pl/pageo.upl.zip",
    },
    "census_population_file01": {
        "source_id": "census_2000_pa_pl_file01",
        "producer": "U.S. Census Bureau",
        "product": "Census 2000 PL 94-171 Pennsylvania File 01",
        "reference_vintage": "2000-04-01",
        "effective_vintage": "2000-04-01",
        "release_date": "2001-03-09",
        "url": (
            "https://www2.census.gov/census_2000/datasets/"
            "redistricting_file--pl_94-171/Pennsylvania/pa00001.upl.zip"
        ),
        "sha256": "888e21ecac795732564c7cd1fa3122cac58f22a006ade8f907d437cbe7a6fe0f",
        "license_access": "Public federal data; cite U.S. Census Bureau",
        "crs": None,
        "schema": {
            "format": "comma-delimited state summary file",
            "member": "pa00001.upl",
            "join": "LOGRECNO (field 5)",
            "metric": "P0010001 / PL001001 total population (field 6)",
        },
        "geographic_universe": "Census 2000 tabulation geography in Pennsylvania",
        "population_universe": "Standard total population",
        "relative_path": "data/raw/census_2000_pa_pl/pa00001.upl.zip",
    },
    "census_blocks": {
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
        "schema": {
            "format": "ESRI Shapefile",
            "layer": "tl_2010_42_tabblock00.shp",
            "id": "BLKIDFP00",
            "area_fields": ["ALAND00", "AWATER00"],
        },
        "geographic_universe": "Census 2000 tabulation blocks in Pennsylvania",
        "population_universe": None,
        "relative_path": ("data/raw/census_2000_pa_blocks/tl_2010_42_tabblock00.zip"),
    },
    "block_relationship": {
        "source_id": "census_2000_2010_block_relationship_pa",
        "producer": "U.S. Census Bureau",
        "product": "Census 2000 to 2010 tabulation block relationship file",
        "reference_vintage": "2000/2010",
        "effective_vintage": "comparability support product",
        "release_date": "2011-02-25 member timestamp",
        "url": (
            "https://www2.census.gov/geo/docs/maps-data/data/rel/t00t10/"
            "TAB2000_TAB2010_ST_42_v2.zip"
        ),
        "sha256": "ab32c86a78d72e39d791167b8eec6f960934cd13c0878833641d0c36e4be5fa7",
        "license_access": "Public federal data; acknowledge U.S. Census Bureau",
        "crs": None,
        "schema": {
            "format": "comma-delimited fixed-width-padded text in ZIP",
            "member": "TAB2000_TAB2010_ST_42_v2.txt",
            "weight_fields": ["AREALAND_INT", "AREAWATER_INT"],
            "population_fields": [],
        },
        "geographic_universe": (
            "Census 2000 Pennsylvania blocks related to 2010 tabulation blocks"
        ),
        "population_universe": None,
        "relative_path": (
            "data/raw/census_2000_2010_block_relationship_pa/"
            "TAB2000_TAB2010_ST_42_v2.zip"
        ),
    },
    "census_2010_blocks": {
        "source_id": "census_2010_pa_blocks",
        "producer": "U.S. Census Bureau",
        "product": "2010 TIGER/Line Pennsylvania tabulation blocks",
        "reference_vintage": "2010",
        "effective_vintage": "2010 Census tabulation geography",
        "release_date": "2012-03-26 archive publication",
        "url": (
            "https://www2.census.gov/geo/tiger/TIGER2010/TABBLOCK/2010/"
            "tl_2010_42_tabblock10.zip"
        ),
        "sha256": "fc33d93eb53e71b0d61c3aa35d496a8a8b8d192933d68ebef206ccbaa9e19152",
        "license_access": "Public federal data; acknowledge U.S. Census Bureau",
        "crs": "EPSG:4269",
        "schema": {
            "format": "ESRI Shapefile",
            "layer": "tl_2010_42_tabblock10.shp",
            "id": "GEOID10",
        },
        "geographic_universe": "2010 Census tabulation blocks in Pennsylvania",
        "population_universe": None,
        "relative_path": ("data/raw/census_2010_pa_blocks/tl_2010_42_tabblock10.zip"),
    },
}

OVERLAY = {
    "artifact_id": "pa_senate_1991_final_fixed_precinct_overlay_v3",
    "producer": "POC022",
    "product": "Fixed 2021 LRC precinct to 1991 Final Senate geometry overlay",
    "source_precinct_dataset_id": "pa_lrc_2021_release_1b_geography",
    "source_precinct_effective_vintage": "2021-10-05",
    "target_senate_plan_id": "pa_senate_1991_final",
    "target_senate_plan_reference_vintage": "1991",
    "method_id": "fixed_precinct_senate_overlay_v3",
    "weighting_universe": "EPSG:5070 fixed precinct polygon area",
    "logical_sha256": "d60a3584ff2a457ef99736607ec656f2d376aed5a7000a2e30a84c82e5477d26",
    "relative_path": (
        "data/processed/senate_overlays/"
        "pa_senate_1991_final_fixed_precinct_overlay_v3.parquet"
    ),
}


def run(root: Path) -> dict[str, object]:
    """Execute POC012 from frozen inputs through two comparable allocations."""
    root = root.resolve()
    artifact_dir = root / "artifacts/work/poc012"
    processed_dir = root / "data/processed/statewide_2000"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    require_manifest_hashes(manifest)

    population = load_2000_pl94_block_population(
        root / SOURCES["census_population_geography"]["relative_path"],
        root / SOURCES["census_population_file01"]["relative_path"],
    )
    blocks = load_2000_census_blocks(root / SOURCES["census_blocks"]["relative_path"])
    blocks_2010 = load_2010_census_blocks(
        root / SOURCES["census_2010_blocks"]["relative_path"]
    )
    relationship = load_2000_2010_block_relationship(
        root / SOURCES["block_relationship"]["relative_path"]
    )
    atoms = gpd.read_parquet(root / OVERLAY["relative_path"])[
        ["target_precinct_geoid", "senate_district", "geometry"]
    ]

    direct_input = blocks.rename(columns={"BLKIDFP00": "GEOID10"})
    direct, direct_diagnostics = build_direct_atomic_crosswalk(direct_input, atoms)
    direct = apply_crosswalk_metadata(direct, DIRECT_METHOD)
    target_2010, target_diagnostics = build_2010_atomic_crosswalk(blocks_2010, atoms)
    related, relationship_diagnostics = build_relationship_atomic_crosswalk(
        relationship, target_2010, population
    )
    relationship_diagnostics["target_2010_atomic"] = target_diagnostics

    direct = add_zero_population_exceptions(direct, population)
    related = add_zero_population_exceptions(related, population)
    direct_diagnostics.update(
        direct_exception_population_diagnostics(
            direct_diagnostics, population, relationship
        )
    )
    direct_diagnostics.update(
        direct_coverage_population_diagnostics(blocks, direct, population)
    )
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
        blocks,
        relationship,
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
            processed_dir / "block_to_fixed_precinct_1991_senate_v1.parquet",
            [
                "method_id",
                "source_block_geoid",
                "target_precinct_geoid",
                "senate_district",
            ],
        ),
        "precinct_population": write_immutable_parquet(
            precinct_result,
            processed_dir / "fixed_precinct_population_2000_v1.parquet",
            ["method_id", "target_precinct_geoid"],
        ),
        "senate_population": write_immutable_parquet(
            senate_result,
            processed_dir / "senate_population_2000_1991_plan_v1.parquet",
            ["method_id", "senate_district"],
        ),
        "precinct_method_comparison": write_immutable_parquet(
            precinct_comparison,
            processed_dir / "precinct_method_comparison_2000_v1.parquet",
            ["target_precinct_geoid"],
        ),
        "senate_method_comparison": write_immutable_parquet(
            senate_comparison,
            processed_dir / "senate_method_comparison_2000_v1.parquet",
            ["senate_district"],
        ),
    }
    qa = {
        "task": "POC012",
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
        raise RuntimeError(
            "POC012 QA failed; inspect artifacts/work/poc012/qa_results.json"
        )
    return qa


def build_2010_atomic_crosswalk(
    blocks: gpd.GeoDataFrame, atoms: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build a geometry-only 2010-block to atomic-target bridge."""
    sources = (
        blocks[["GEOID10", "geometry"]]
        .rename(columns={"GEOID10": "target_2010_block_geoid"})
        .to_crs(AREA_CRS)
    )
    intersections = gpd.overlay(
        sources,
        atoms.to_crs(AREA_CRS),
        how="intersection",
        keep_geom_type=True,
    )
    intersections = intersections[~intersections.geometry.is_empty].copy()
    intersections["atomic_area_square_meters"] = intersections.geometry.area
    intersections = intersections[intersections["atomic_area_square_meters"].gt(0)]
    grouped = intersections.groupby(
        ["target_2010_block_geoid", "target_precinct_geoid", "senate_district"],
        as_index=False,
    )["atomic_area_square_meters"].sum()
    covered = grouped.groupby("target_2010_block_geoid")[
        "atomic_area_square_meters"
    ].transform("sum")
    grouped["target_atomic_weight"] = grouped["atomic_area_square_meters"] / covered
    source_ids = set(sources["target_2010_block_geoid"])
    observed_ids = set(grouped["target_2010_block_geoid"])
    diagnostics = {
        "raw_intersection_rows": len(intersections),
        "allocation_rows": len(grouped),
        "target_2010_blocks": len(observed_ids),
        "uncovered_target_2010_blocks": len(source_ids - observed_ids),
        "uncovered_target_2010_ids": sorted(source_ids - observed_ids),
        "fixed_precincts": int(grouped["target_precinct_geoid"].nunique()),
        "senate_districts": int(grouped["senate_district"].nunique()),
        "weighting_universe": "2010 block EPSG:5070 area only",
    }
    return grouped, diagnostics


def build_relationship_atomic_crosswalk(
    relationship: pd.DataFrame,
    target_2010: pd.DataFrame,
    population: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Compose official 2000-to-2010 areas with 2010 atomic target areas."""
    relation = relationship[
        [
            "source_block_geoid",
            "target_2010_block_geoid",
            "AREALAND_2000",
            "AREAWATER_2000",
            "AREALAND_INT",
            "AREAWATER_INT",
        ]
    ].copy()
    relation["relationship_intersection_area"] = (
        relation["AREALAND_INT"] + relation["AREAWATER_INT"]
    )
    relationship_area = relation.groupby("source_block_geoid")[
        "relationship_intersection_area"
    ].transform("sum")
    relation["relationship_weight"] = (
        relation["relationship_intersection_area"] / relationship_area
    )
    composed = relation.merge(
        target_2010,
        on="target_2010_block_geoid",
        how="left",
        validate="many_to_many",
    )
    missing_target = composed["target_precinct_geoid"].isna()
    composed["component_weight"] = (
        composed["relationship_weight"] * composed["target_atomic_weight"]
    )
    grouped = (
        composed[~missing_target]
        .groupby(
            ["source_block_geoid", "target_precinct_geoid", "senate_district"],
            as_index=False,
        )["component_weight"]
        .sum()
    )
    raw_sums = grouped.groupby("source_block_geoid")["component_weight"].transform(
        "sum"
    )
    grouped["weight"] = grouped["component_weight"] / raw_sums
    grouped = grouped.rename(columns={"component_weight": "raw_composed_weight"})

    expected_source_ids = set(population["source_block_geoid"])
    population_by_source = population.set_index("source_block_geoid")["P0010001"]
    observed_ids = set(grouped["source_block_geoid"])
    missing_source_ids = sorted(expected_source_ids - observed_ids)
    source_area = relation.groupby("source_block_geoid").agg(
        source_land=("AREALAND_2000", "first"),
        source_water=("AREAWATER_2000", "first"),
        intersection_land=("AREALAND_INT", "sum"),
        intersection_water=("AREAWATER_INT", "sum"),
    )
    source_area["published_source_area"] = (
        source_area["source_land"] + source_area["source_water"]
    )
    source_area["published_intersection_area"] = (
        source_area["intersection_land"] + source_area["intersection_water"]
    )
    area_mismatch = source_area["published_source_area"].ne(
        source_area["published_intersection_area"]
    )
    area_mismatch_ids = sorted(source_area.index[area_mismatch])
    missing_components = composed.loc[
        missing_target,
        [
            "source_block_geoid",
            "target_2010_block_geoid",
            "relationship_intersection_area",
            "relationship_weight",
        ],
    ].copy()
    missing_components["source_population"] = missing_components[
        "source_block_geoid"
    ].map(population_by_source)
    missing_components["equal_area_implied_population"] = (
        missing_components["source_population"]
        * missing_components["relationship_weight"]
    )
    diagnostics = {
        "relationship_rows": len(relationship),
        "relationship_source_blocks": int(relationship["source_block_geoid"].nunique()),
        "relationship_target_2010_blocks": int(
            relationship["target_2010_block_geoid"].nunique()
        ),
        "relationship_split_source_blocks": int(
            relationship.groupby("source_block_geoid").size().gt(1).sum()
        ),
        "relationship_max_rows_per_source": int(
            relationship.groupby("source_block_geoid").size().max()
        ),
        "relationship_source_area_mismatches": int(area_mismatch.sum()),
        "relationship_source_area_mismatch_ids": area_mismatch_ids,
        "relationship_source_area_mismatch_population": int(
            population_by_source.reindex(area_mismatch_ids).sum()
        ),
        "relationship_minimum_area_coverage_ratio": float(
            (
                source_area["published_intersection_area"]
                / source_area["published_source_area"]
            ).min()
        ),
        "missing_target_atomic_rows": int(missing_target.sum()),
        "missing_target_atomic_source_blocks": int(
            composed.loc[missing_target, "source_block_geoid"].nunique()
        ),
        "missing_target_atomic_populated_source_blocks": int(
            missing_components.loc[
                missing_components["source_population"].gt(0),
                "source_block_geoid",
            ].nunique()
        ),
        "missing_target_atomic_source_population": int(
            missing_components.drop_duplicates("source_block_geoid")[
                "source_population"
            ].sum()
        ),
        "missing_target_atomic_equal_area_implied_population": float(
            missing_components["equal_area_implied_population"].sum()
        ),
        "missing_target_atomic_components": missing_components.to_dict("records"),
        "assigned_source_blocks": len(observed_ids),
        "missing_source_blocks_before_exceptions": len(missing_source_ids),
        "missing_source_ids": missing_source_ids,
        "allocation_rows_before_exceptions": len(grouped),
        "normalization": (
            "official 2000-to-2010 relationship land-plus-water area, then "
            "2010-block atomic area; normalized per 2000 source block"
        ),
        "nearest_assignment_count": 0,
    }
    grouped = apply_crosswalk_metadata(grouped, RELATIONSHIP_METHOD)
    return grouped, diagnostics


def direct_coverage_population_diagnostics(
    blocks: gpd.GeoDataFrame,
    direct: pd.DataFrame,
    population: pd.DataFrame,
) -> dict[str, object]:
    """Type direct-route incomplete coverage without treating it as population."""
    source_area = (
        blocks[["BLKIDFP00", "geometry"]]
        .to_crs(AREA_CRS)
        .set_index("BLKIDFP00")
        .geometry.area
    )
    covered_area = direct.groupby("source_block_geoid")[
        "intersection_area_square_meters"
    ].sum()
    coverage = covered_area / source_area.reindex(covered_area.index)
    low = coverage[coverage.lt(0.99)]
    source_population = population.set_index("source_block_geoid")["P0010001"]
    populated = low[source_population.reindex(low.index).gt(0)]
    implied = source_population.reindex(populated.index) * (1 - populated)
    return {
        "sources_below_99_percent_coverage_population": int(
            source_population.reindex(low.index).sum()
        ),
        "populated_sources_below_99_percent_coverage": len(populated),
        "equal_area_implied_uncovered_population": float(implied.sum()),
        "maximum_source_equal_area_implied_uncovered_population": float(implied.max()),
        "coverage_population_interpretation": (
            "diagnostic only; source population multiplied by uncovered area share "
            "is not an observed population location"
        ),
    }


def apply_crosswalk_metadata(frame: pd.DataFrame, method_id: str) -> pd.DataFrame:
    weighting = {
        DIRECT_METHOD: "direct EPSG:5070 polygon intersection area",
        RELATIONSHIP_METHOD: (
            "official 2000-to-2010 land-plus-water area composed with "
            "2010-block atomic area"
        ),
    }[method_id]
    return frame.assign(
        source_dataset_id="census_2000_pa_blocks",
        source_reference_vintage="2000",
        target_precinct_dataset_id="pa_lrc_2021_release_1b_geography",
        target_precinct_effective_vintage="2021-10-05",
        target_senate_plan_id="pa_senate_1991_final",
        target_senate_plan_reference_vintage="1991",
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
        raise ValueError(f"Material uncovered populated 2000 source blocks: {ids}")
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


def aggregate_results(
    population: pd.DataFrame, crosswalks: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    assigned = crosswalks[crosswalks["assignment_status"].eq("assigned")]
    allocated = assigned.merge(
        population, on="source_block_geoid", how="left", validate="many_to_one"
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
        population_product_id="census_2000_pa_pl",
        population_reference_date="2000-04-01",
        population_release_date="2001-03-09",
        source_geography_id="census_2000_pa_blocks",
        source_reference_vintage="2000",
        target_snapshot_id="pa_lrc_2021_release_1b_geography",
        target_effective_vintage="2021-10-05",
        senate_plan_id="pa_senate_1991_final",
        senate_plan_reference_vintage="1991",
        general_election_date=pd.NA,
        election_pairing_status="unpaired_geography_product_poc012",
        applicable_general_elections="1992|1994|1996|1998|2000",
        geography_level=geography_level,
        metric="P0010001",
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
    blocks: gpd.GeoDataFrame,
    relationship: pd.DataFrame,
    atoms: gpd.GeoDataFrame,
    crosswalks: pd.DataFrame,
    precinct_result: pd.DataFrame,
    senate_result: pd.DataFrame,
    direct_diagnostics: dict[str, object],
    relationship_diagnostics: dict[str, object],
) -> list[dict[str, object]]:
    population_ids = set(population["source_block_geoid"])
    geometry_ids = set(blocks["BLKIDFP00"])
    checks = [
        check(
            "source_block_count",
            len(population) == EXPECTED["source_blocks"],
            len(population),
        ),
        check(
            "source_block_ids_unique",
            population["source_block_geoid"].is_unique,
            int(population["source_block_geoid"].nunique()),
        ),
        check(
            "source_population_complete",
            not population["P0010001"].isna().any(),
            int(population["P0010001"].isna().sum()),
        ),
        check(
            "source_population_total",
            int(population["P0010001"].sum()) == EXPECTED["population"],
            int(population["P0010001"].sum()),
        ),
        check(
            "source_county_count",
            population["source_block_geoid"].str.slice(2, 5).nunique()
            == EXPECTED["counties"],
            int(population["source_block_geoid"].str.slice(2, 5).nunique()),
        ),
        check(
            "geometry_block_count",
            len(blocks) == EXPECTED["source_blocks"],
            len(blocks),
        ),
        check(
            "geometry_ids_match_population",
            geometry_ids == population_ids,
            {"population": len(population_ids), "geometry": len(geometry_ids)},
        ),
        check("geometry_crs", blocks.crs.to_epsg() == 4269, str(blocks.crs)),
        check(
            "geometry_valid",
            bool(
                blocks.geometry.notna().all()
                and (~blocks.geometry.is_empty).all()
                and blocks.geometry.is_valid.all()
            ),
            {
                "null": int(blocks.geometry.isna().sum()),
                "empty": int(blocks.geometry.is_empty.sum()),
                "invalid": int((~blocks.geometry.is_valid).sum()),
            },
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
            "relationship_source_universe_complete",
            set(relationship["source_block_geoid"]) == population_ids,
            len(population_ids - set(relationship["source_block_geoid"])),
        ),
        check(
            "atomic_precinct_count",
            atoms["target_precinct_geoid"].nunique() == EXPECTED["fixed_precincts"],
            int(atoms["target_precinct_geoid"].nunique()),
        ),
        check(
            "atomic_senate_district_count",
            atoms["senate_district"].nunique() == EXPECTED["senate_districts"],
            int(atoms["senate_district"].nunique()),
        ),
        check(
            "direct_populated_linework_exceptions_have_relationship_support",
            direct_diagnostics[
                "populated_representative_point_exceptions_without_relationship_support"
            ]
            == 0,
            {
                "representative_point_exceptions": direct_diagnostics[
                    "representative_points_uncovered"
                ],
                "populated_exceptions": direct_diagnostics[
                    "populated_representative_point_exceptions"
                ],
                "population": direct_diagnostics[
                    "populated_representative_point_exception_population"
                ],
                "without_relationship_support": direct_diagnostics[
                    "populated_representative_point_exceptions_without_relationship_support"
                ],
            },
        ),
        check(
            "relationship_all_sources_reach_atomic_target",
            relationship_diagnostics["missing_source_blocks_before_exceptions"] == 0,
            relationship_diagnostics["missing_source_blocks_before_exceptions"],
        ),
        check(
            "relationship_missing_atomic_components_immaterial",
            relationship_diagnostics[
                "missing_target_atomic_equal_area_implied_population"
            ]
            <= ATOMIC_GAP_EQUAL_AREA_POPULATION_TOLERANCE,
            {
                "equal_area_implied_population": relationship_diagnostics[
                    "missing_target_atomic_equal_area_implied_population"
                ],
                "tolerance": ATOMIC_GAP_EQUAL_AREA_POPULATION_TOLERANCE,
                "source_blocks": relationship_diagnostics[
                    "missing_target_atomic_source_blocks"
                ],
                "populated_source_blocks": relationship_diagnostics[
                    "missing_target_atomic_populated_source_blocks"
                ],
            },
        ),
        check(
            "no_nearest_assignments",
            not bool(crosswalks["nearest_assignment_used"].any()),
            int(crosswalks["nearest_assignment_used"].sum()),
        ),
    ]
    for method_id in [DIRECT_METHOD, RELATIONSHIP_METHOD]:
        checks.extend(validate_method_crosswalk(crosswalks, population, method_id))
        precinct_method = precinct_result[precinct_result["method_id"].eq(method_id)]
        senate_method = senate_result[senate_result["method_id"].eq(method_id)]
        checks.extend(
            [
                check(
                    f"{method_id}_precinct_result_count",
                    len(precinct_method) == EXPECTED["fixed_precincts"],
                    len(precinct_method),
                ),
                check(
                    f"{method_id}_senate_result_count",
                    len(senate_method) == EXPECTED["senate_districts"],
                    len(senate_method),
                ),
                check(
                    f"{method_id}_precinct_population_conserved",
                    abs(precinct_method["population"].sum() - EXPECTED["population"])
                    <= POPULATION_TOLERANCE,
                    float(precinct_method["population"].sum()),
                ),
                check(
                    f"{method_id}_senate_population_conserved",
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
    return checks


def build_manifest(root: Path) -> dict[str, object]:
    entries = []
    for source in SOURCES.values():
        path = root / source["relative_path"]
        entry = dict(source)
        entry.update(
            {
                "retrieval_timestamp": datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ).isoformat(),
                "size_bytes": path.stat().st_size,
                "observed_sha256": sha256(path),
            }
        )
        entries.append(entry)
    overlay_path = root / OVERLAY["relative_path"]
    overlay = gpd.read_parquet(overlay_path)
    overlay_entry = dict(OVERLAY)
    overlay_entry.update(
        {
            "created_timestamp": datetime.fromtimestamp(
                overlay_path.stat().st_mtime, UTC
            ).isoformat(),
            "size_bytes": overlay_path.stat().st_size,
            "physical_sha256": sha256(overlay_path),
            "observed_logical_sha256": logical_geoframe_hash(
                overlay, ["target_precinct_geoid", "senate_district"]
            ),
        }
    )
    return {
        "manifest_version": "1.0.0",
        "sources": entries,
        "derived_inputs": [overlay_entry],
    }


def require_manifest_hashes(manifest: dict[str, object]) -> None:
    failures = [
        source["source_id"]
        for source in manifest["sources"]
        if source["sha256"] != source["observed_sha256"]
    ]
    failures.extend(
        artifact["artifact_id"]
        for artifact in manifest["derived_inputs"]
        if artifact["logical_sha256"] != artifact["observed_logical_sha256"]
    )
    if failures:
        raise RuntimeError(f"Checksum mismatch: {', '.join(failures)}")


def render_report(qa: dict[str, object]) -> str:
    comparison = qa["comparison"]
    direct = qa["direct_diagnostics"]
    relationship = qa["relationship_diagnostics"]
    return f"""# POC012 statewide Census 2000 population proof

Status: **{"PASS" if qa["passed"] else "FAIL"}**

- Census 2000 source blocks: {EXPECTED["source_blocks"]:,}
- Fixed 2021 LRC precincts: {EXPECTED["fixed_precincts"]:,}
- 1991 Final Senate districts: {EXPECTED["senate_districts"]:,}
- Pennsylvania Census 2000 population: {EXPECTED["population"]:,}
- Direct atomic-area source exceptions: {direct["uncovered_source_blocks"]:,}
- Relationship-file source exceptions: {relationship["missing_source_blocks_before_exceptions"]:,}
- Precinct total absolute method delta: {comparison["precinct_total_absolute_delta"]:,.3f}
- Senate total absolute method delta: {comparison["senate_total_absolute_delta"]:,.3f}
- Nearest-boundary assignments: 0

The direct route intersects Census 2000 blocks with the atomic fixed-precinct/
1991 Senate geometry in EPSG:5070. The independent relationship-assisted route
composes official 2000-to-2010 land-plus-water intersection fractions with a
geometry-only 2010-block-to-atomic-target crosswalk. Neither route uses later
population as a historical weight.

Both routes normalize over covered area, require state and source-county
population conservation, support every fixed precinct and Senate district, and
retain fractional estimates. Any uncovered source exception is permitted only
for a verified zero-population block. The method difference is uncertainty
evidence, not a claim that either equal-area route reproduces population
locations inside Census 2000 blocks.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC012 {'passed' if qa['passed'] else 'failed'}")


if __name__ == "__main__":
    main()
