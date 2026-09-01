"""Produce the POC015 representative ACS block-group allocation proof."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from census_pa_poc.fixed_geography import load_lrc_blocks
from census_pa_poc.senate_overlay import logical_geoframe_hash
from census_pa_poc.sources import (
    load_2010_2020_block_relationship,
    load_2010_pl94_block_population,
    load_2015_census_block_groups,
    load_acs5_2015_block_group_population,
    sha256,
)
from census_pa_poc.statewide_2010 import (
    build_2020_atomic_crosswalk,
    build_relationship_atomic_crosswalk,
)
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

AREA_CRS = "EPSG:5070"
WEIGHT_TOLERANCE = 1e-12
ESTIMATE_TOLERANCE = 1e-6
SIMPLE_METHOD = "simple_atomic_area_acs5_2015_v1"
POPULATION_METHOD = "census2010_population_atomic_acs5_2015_v1"
EXPECTED = {
    "source_block_groups": 9_740,
    "source_counties": 67,
    "estimate": 12_779_559,
    "zero_estimate_block_groups": 18,
    "zero_2010_support_block_groups": 9,
    "fixed_precincts": 9_178,
    "senate_districts": 50,
}

SOURCES = {
    "acs_geography": {
        "source_id": "acs5_2015_pa_summary_geography",
        "producer": "U.S. Census Bureau",
        "product": "2011-2015 ACS five-year Pennsylvania Summary File geography",
        "reference_vintage": "2011-01-01/2015-12-31",
        "effective_vintage": "2015 ACS block-group geography",
        "release_date": "2016-12-08",
        "url": (
            "https://www2.census.gov/programs-surveys/acs/summary_file/2015/data/"
            "5_year_seq_by_state/Pennsylvania/Tracts_Block_Groups_Only/g20155pa.csv"
        ),
        "sha256": "74bcf0e2ae5c2591aaf82470c6b71e45618877e19db005f3053a714cba8e5748",
        "license_access": "Public federal data; cite U.S. Census Bureau",
        "crs": None,
        "schema": {
            "format": "headerless comma-delimited geography records",
            "summary_level": "150",
            "id_fields": ["STATE", "COUNTY", "TRACT", "BLKGRP"],
            "join": "LOGRECNO",
        },
        "geographic_universe": "2015 ACS Pennsylvania block groups",
        "population_universe": "Total population",
        "relative_path": "data/raw/acs5_2015_pa/g20155pa.csv",
    },
    "acs_sequence": {
        "source_id": "acs5_2015_pa_b01003_sequence",
        "producer": "U.S. Census Bureau",
        "product": "2011-2015 ACS five-year Pennsylvania Summary File sequence 0003",
        "reference_vintage": "2011-01-01/2015-12-31",
        "effective_vintage": "2015 ACS block-group geography",
        "release_date": "2016-12-08",
        "url": (
            "https://www2.census.gov/programs-surveys/acs/summary_file/2015/data/"
            "5_year_seq_by_state/Pennsylvania/Tracts_Block_Groups_Only/"
            "20155pa0003000.zip"
        ),
        "sha256": "fb438d716f48b89fa2721ea60a74c2cea1d11ca9b33c99d0cde2500770e18334",
        "license_access": "Public federal data; cite U.S. Census Bureau",
        "crs": None,
        "schema": {
            "format": "ZIP of comma-delimited estimate and MOE sequences",
            "estimate_member": "e20155pa0003000.txt",
            "moe_member": "m20155pa0003000.txt",
            "B01003_start_position_1_based": 130,
            "estimate_variable": "B01003_001E",
            "moe_variable": "B01003_001M",
        },
        "geographic_universe": "2015 ACS Pennsylvania tract/block-group records",
        "population_universe": "Total population",
        "relative_path": "data/raw/acs5_2015_pa/20155pa0003000.zip",
    },
    "acs_sequence_lookup": {
        "source_id": "acs5_2015_sequence_table_lookup",
        "producer": "U.S. Census Bureau",
        "product": "2015 ACS five-year sequence/table-number lookup",
        "reference_vintage": "2015",
        "effective_vintage": "2011-2015 ACS five-year Summary File",
        "release_date": "2016-11-14 file timestamp",
        "url": (
            "https://www2.census.gov/programs-surveys/acs/summary_file/2015/"
            "documentation/user_tools/ACS_5yr_Seq_Table_Number_Lookup.txt"
        ),
        "sha256": "263983853a1bb1a35a5ba7ec7d910cdcf052233e569bc7aa9a78517cc4a5c5dc",
        "license_access": "Public federal documentation",
        "crs": None,
        "schema": {"format": "comma-delimited table/sequence lookup"},
        "geographic_universe": "2011-2015 ACS five-year tables",
        "population_universe": None,
        "relative_path": ("data/raw/acs5_2015_pa/ACS_5yr_Seq_Table_Number_Lookup.txt"),
    },
    "acs_geography_layout": {
        "source_id": "acs5_2015_five_year_geography_layout",
        "producer": "U.S. Census Bureau",
        "product": "2015 ACS five-year Summary File geography layout",
        "reference_vintage": "2015",
        "effective_vintage": "2011-2015 ACS five-year Summary File",
        "release_date": "2016 documentation release",
        "url": (
            "https://www2.census.gov/programs-surveys/acs/summary_file/2015/"
            "documentation/geography/5_year_Mini_Geo.xlsx"
        ),
        "sha256": "b2ce924dd7f81b84e0da856e88e70567616c2d252da7db088af0d37df5b52f84",
        "license_access": "Public federal documentation",
        "crs": None,
        "schema": {"format": "Microsoft Excel geography templates"},
        "geographic_universe": "2011-2015 ACS five-year geographies",
        "population_universe": None,
        "relative_path": "data/raw/acs5_2015_pa/5_year_Mini_Geo.xlsx",
    },
    "acs_block_groups": {
        "source_id": "census_2015_pa_block_groups",
        "producer": "U.S. Census Bureau",
        "product": "2015 TIGER/Line Pennsylvania block groups",
        "reference_vintage": "2015",
        "effective_vintage": "January 1, 2015 boundaries",
        "release_date": "2015 TIGER/Line release",
        "url": ("https://www2.census.gov/geo/tiger/TIGER2015/BG/tl_2015_42_bg.zip"),
        "sha256": "c0196af49134903a652ded0b050045654a3cbdb8d4f4e4811180ac964e36af3a",
        "license_access": "Public federal data; acknowledge U.S. Census Bureau",
        "crs": "EPSG:4269",
        "schema": {
            "format": "ESRI Shapefile",
            "layer": "tl_2015_42_bg.shp",
            "id": "GEOID",
            "area_fields": ["ALAND", "AWATER"],
        },
        "geographic_universe": "2015 Pennsylvania Census block groups",
        "population_universe": None,
        "relative_path": ("data/raw/census_2015_pa_block_groups/tl_2015_42_bg.zip"),
    },
    "census_2010_population": {
        "source_id": "census_2010_pa_pl",
        "producer": "U.S. Census Bureau",
        "product": "2010 Census Redistricting Data PL 94-171 Summary File",
        "reference_vintage": "2010-04-01",
        "effective_vintage": "2010-04-01",
        "release_date": "2011-03-09",
        "url": (
            "https://www2.census.gov/census_2010/01-Redistricting_File--"
            "PL_94-171/Pennsylvania/pa2010.pl.zip"
        ),
        "sha256": "3cf2460ea17d1be087d9b12700e45962b164f6233f8c1071ddc67ab55392951a",
        "license_access": "Public federal data; cite U.S. Census Bureau",
        "crs": None,
        "schema": {
            "format": "fixed-width geography plus comma-delimited File 01",
            "metric": "P0010001",
        },
        "geographic_universe": "2010 Census blocks in Pennsylvania",
        "population_universe": "Standard total population",
        "relative_path": "data/raw/census_2010_pa_pl/pa2010.pl.zip",
    },
    "census_2010_relationship": {
        "source_id": "census_2010_2020_block_relationship_pa",
        "producer": "U.S. Census Bureau",
        "product": "2010 Census block to 2020 Census block relationship file",
        "reference_vintage": "2010/2020",
        "effective_vintage": "comparability support product",
        "release_date": "2020-12-04 file timestamp",
        "url": (
            "https://www2.census.gov/geo/docs/maps-data/data/rel2020/t10t20/"
            "TAB2010_TAB2020_ST42.zip"
        ),
        "sha256": "6e8ac323b98bf7259dac59ae7000c14fa72ce38207f77648d08645bbea29a323",
        "license_access": "Public federal data",
        "crs": None,
        "schema": {
            "format": "pipe-delimited relationship file",
            "weight_fields": ["AREALAND_INT", "AREAWATER_INT"],
        },
        "geographic_universe": "2010 Pennsylvania blocks related to 2020 blocks",
        "population_universe": None,
        "relative_path": (
            "data/raw/census_2010_2020_block_relationship_pa/TAB2010_TAB2020_ST42.zip"
        ),
    },
    "lrc_geography": {
        "source_id": "pa_lrc_2021_release_1b_geography",
        "producer": "Pennsylvania Legislative Reapportionment Commission",
        "product": "2021-10-05 LRC Data Release No. 1b Data Set 1 geography",
        "reference_vintage": "2020",
        "effective_vintage": "2021-10-05",
        "url": (
            "https://www.redistricting.state.pa.us/resources/GISData/Census/"
            "2021/2021-DataSet1-WithoutPrisoner/"
            "2021%20LRC%20Data%20Release%201b%20-%20Geography.zip"
        ),
        "sha256": "14187001c627c6a16bf967415059408c4ef7007d366fd9105b5be30763250e3b",
        "license_access": "Public download; redistribution terms not stated",
        "crs": "EPSG:4269",
        "schema": {
            "format": "ESRI Shapefile",
            "block_layer": "Geography/WP_Blocks.shp",
            "fragment_id": "GEOID20",
        },
        "geographic_universe": "Pennsylvania corrected 2020 block fragments",
        "population_universe": None,
        "relative_path": (
            "data/raw/pa_lrc_2021_release_1b_geography/"
            "2021 LRC Data Release 1b - Geography.zip"
        ),
    },
}

OVERLAY = {
    "artifact_id": "pa_senate_2012_revised_final_fixed_precinct_overlay_v3",
    "producer": "POC022",
    "product": "Fixed 2021 LRC precinct to 2012 Revised Final Senate overlay",
    "source_precinct_dataset_id": "pa_lrc_2021_release_1b_geography",
    "source_precinct_effective_vintage": "2021-10-05",
    "target_senate_plan_id": "pa_senate_2012_revised_final",
    "target_senate_plan_reference_vintage": "2012",
    "method_id": "fixed_precinct_senate_overlay_v3",
    "weighting_universe": "EPSG:5070 fixed precinct polygon area",
    "logical_sha256": "97a0c5c2f382174363de8ca7506dbe73f27f73901b4c495f2a2cf1ee4a74bc2b",
    "relative_path": (
        "data/processed/senate_overlays/"
        "pa_senate_2012_revised_final_fixed_precinct_overlay_v3.parquet"
    ),
}


def run(root: Path) -> dict[str, object]:
    """Execute the representative ACS estimate/MOE method proof."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc015"
    processed_dir = root / "data/processed/statewide_acs5_2015"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    require_manifest_hashes(manifest)

    population = load_acs5_2015_block_group_population(
        root / SOURCES["acs_geography"]["relative_path"],
        root / SOURCES["acs_sequence"]["relative_path"],
    )
    block_groups = load_2015_census_block_groups(
        root / SOURCES["acs_block_groups"]["relative_path"]
    )
    atoms = gpd.read_parquet(root / OVERLAY["relative_path"])[
        ["target_precinct_geoid", "senate_district", "geometry"]
    ]

    simple, simple_diagnostics = build_simple_area_crosswalk(block_groups, atoms)
    block_support, support_diagnostics = build_2010_block_atomic_support(root, atoms)
    informed, informed_diagnostics = build_population_informed_crosswalk(
        population,
        block_support,
        simple,
    )
    informed_diagnostics["block_atomic_support"] = support_diagnostics

    crosswalks = pd.concat([simple, informed], ignore_index=True)
    crosswalks = normalize_crosswalk_dtypes(crosswalks)
    crosswalks = crosswalks.sort_values(
        [
            "method_id",
            "source_block_group_geoid",
            "target_precinct_geoid",
            "senate_district",
        ],
        kind="stable",
    ).reset_index(drop=True)

    precinct_result, senate_result = aggregate_results(population, crosswalks)
    precinct_comparison = compare_results(precinct_result, "target_precinct_geoid")
    senate_comparison = compare_results(senate_result, "senate_district")
    checks = build_checks(
        population,
        block_groups,
        atoms,
        crosswalks,
        precinct_result,
        senate_result,
        simple_diagnostics,
        informed_diagnostics,
    )

    writes = {
        "atomic_crosswalks": write_immutable_parquet(
            crosswalks,
            processed_dir / "block_group_to_fixed_precinct_2012_senate_v1.parquet",
            [
                "method_id",
                "source_block_group_geoid",
                "target_precinct_geoid",
                "senate_district",
            ],
        ),
        "precinct_results": write_immutable_parquet(
            precinct_result,
            processed_dir / "fixed_precinct_acs5_2015_b01003_v1.parquet",
            ["method_id", "target_precinct_geoid"],
        ),
        "senate_results": write_immutable_parquet(
            senate_result,
            processed_dir / "senate_acs5_2015_b01003_2012_plan_v1.parquet",
            ["method_id", "senate_district"],
        ),
        "precinct_method_comparison": write_immutable_parquet(
            precinct_comparison,
            processed_dir / "precinct_method_comparison_acs5_2015_v1.parquet",
            ["target_precinct_geoid"],
        ),
        "senate_method_comparison": write_immutable_parquet(
            senate_comparison,
            processed_dir / "senate_method_comparison_acs5_2015_v1.parquet",
            ["senate_district"],
        ),
    }
    qa = {
        "task": "POC015",
        "representative_product_id": "acs5_2015",
        "simple_method_id": SIMPLE_METHOD,
        "population_informed_method_id": POPULATION_METHOD,
        "area_crs": AREA_CRS,
        "weight_tolerance": WEIGHT_TOLERANCE,
        "moe_confidence_level": 0.90,
        "moe_aggregation": (
            "allocate source MOE linearly by fixed crosswalk weight, then use "
            "root-sum-square across source block groups; covariance and support-"
            "weight uncertainty are unavailable"
        ),
        "simple_diagnostics": simple_diagnostics,
        "population_informed_diagnostics": informed_diagnostics,
        "comparison": comparison_summary(precinct_comparison, senate_comparison),
        "checks": checks,
        "artifact_writes": writes,
        "hashes": {
            "atomic_crosswalks": logical_frame_hash(
                crosswalks,
                [
                    "method_id",
                    "source_block_group_geoid",
                    "target_precinct_geoid",
                    "senate_district",
                ],
            ),
            "precinct_results": logical_frame_hash(
                precinct_result, ["method_id", "target_precinct_geoid"]
            ),
            "senate_results": logical_frame_hash(
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
        raise RuntimeError("POC015 QA failed; inspect artifacts/poc015/qa_results.json")
    return qa


def build_simple_area_crosswalk(
    block_groups: gpd.GeoDataFrame,
    atoms: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Intersect ACS block groups directly with the atomic target."""
    sources = block_groups[["GEOID", "geometry"]].rename(
        columns={"GEOID": "source_block_group_geoid"}
    )
    sources = sources.to_crs(AREA_CRS)
    targets = atoms.to_crs(AREA_CRS)
    intersections = gpd.overlay(
        sources, targets, how="intersection", keep_geom_type=True
    )
    intersections = intersections[~intersections.geometry.is_empty].copy()
    intersections["raw_support_value"] = intersections.geometry.area
    intersections = intersections[intersections["raw_support_value"].gt(0)]
    grouped = intersections.groupby(
        ["source_block_group_geoid", "target_precinct_geoid", "senate_district"],
        as_index=False,
    )["raw_support_value"].sum()
    covered = grouped.groupby("source_block_group_geoid")[
        "raw_support_value"
    ].transform("sum")
    grouped["weight"] = grouped["raw_support_value"] / covered
    source_area = sources.set_index("source_block_group_geoid").geometry.area
    covered_area = grouped.groupby("source_block_group_geoid")[
        "raw_support_value"
    ].sum()
    coverage = covered_area / source_area.reindex(covered_area.index)
    target_union = shapely.union_all(targets.geometry.array)
    representative_points = shapely.point_on_surface(sources.geometry.array)
    point_covered = shapely.covers(target_union, representative_points)
    diagnostics = {
        "raw_intersection_rows": len(intersections),
        "allocation_rows": len(grouped),
        "assigned_source_block_groups": int(
            grouped["source_block_group_geoid"].nunique()
        ),
        "minimum_coverage_ratio": float(coverage.min()),
        "sources_below_99_percent_coverage": int(coverage.lt(0.99).sum()),
        "sources_below_90_percent_coverage": int(coverage.lt(0.90).sum()),
        "representative_points_uncovered": int((~point_covered).sum()),
        "nearest_assignment_count": 0,
    }
    grouped["fallback_basis"] = "none"
    return add_crosswalk_metadata(grouped, SIMPLE_METHOD), diagnostics


def build_2010_block_atomic_support(
    root: Path,
    atoms: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build the accepted relationship-assisted 2010 block support surface."""
    population = load_2010_pl94_block_population(
        root / SOURCES["census_2010_population"]["relative_path"]
    )
    relationship = load_2010_2020_block_relationship(
        root / SOURCES["census_2010_relationship"]["relative_path"]
    )
    lrc_blocks = load_lrc_blocks(root / SOURCES["lrc_geography"]["relative_path"])
    target_2020, target_diagnostics = build_2020_atomic_crosswalk(lrc_blocks, atoms)
    block_crosswalk, relationship_diagnostics = build_relationship_atomic_crosswalk(
        relationship,
        target_2020,
        set(population["source_block_geoid"]),
    )
    assigned = block_crosswalk[
        ["source_block_geoid", "target_precinct_geoid", "senate_district", "weight"]
    ]
    support = assigned.merge(
        population,
        on="source_block_geoid",
        how="left",
        validate="many_to_one",
    )
    support["source_block_group_geoid"] = support["source_block_geoid"].str.slice(0, 12)
    support["support_population"] = support["P0010001"] * support["weight"]
    grouped = support.groupby(
        ["source_block_group_geoid", "target_precinct_geoid", "senate_district"],
        as_index=False,
    )["support_population"].sum()
    diagnostics = {
        "source_2010_blocks": len(population),
        "source_2010_population": int(population["P0010001"].sum()),
        "source_2010_block_groups": int(
            population["source_block_geoid"].str.slice(0, 12).nunique()
        ),
        "relationship": relationship_diagnostics,
        "target_2020_atomic": target_diagnostics,
    }
    return grouped, diagnostics


def build_population_informed_crosswalk(
    population: pd.DataFrame,
    block_support: pd.DataFrame,
    simple_crosswalk: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Weight atomic targets by 2010 block population with zero-support fallback."""
    totals = block_support.groupby("source_block_group_geoid")[
        "support_population"
    ].sum()
    positive_ids = set(totals[totals.gt(0)].index)
    all_ids = set(population["source_block_group_geoid"])
    fallback_ids = all_ids - positive_ids

    informed = block_support[
        block_support["source_block_group_geoid"].isin(positive_ids)
    ].copy()
    informed["raw_support_value"] = informed.pop("support_population")
    informed["weight"] = informed["raw_support_value"] / informed[
        "source_block_group_geoid"
    ].map(totals)
    informed["fallback_basis"] = "none"

    fallback = simple_crosswalk[
        simple_crosswalk["source_block_group_geoid"].isin(fallback_ids)
    ][
        [
            "source_block_group_geoid",
            "target_precinct_geoid",
            "senate_district",
            "raw_support_value",
            "weight",
        ]
    ].copy()
    fallback["fallback_basis"] = "simple_area_zero_2010_population"
    combined = pd.concat([informed, fallback], ignore_index=True)
    fallback_population = population[
        population["source_block_group_geoid"].isin(fallback_ids)
    ]
    diagnostics = {
        "positive_2010_support_block_groups": len(positive_ids),
        "zero_2010_support_block_groups": len(fallback_ids),
        "zero_2010_support_ids": sorted(fallback_ids),
        "fallback_acs_estimate": int(fallback_population["B01003_001E"].sum()),
        "fallback_acs_moe_linear_sum": int(fallback_population["B01003_001M"].sum()),
        "allocation_rows": len(combined),
        "nearest_assignment_count": 0,
    }
    return add_crosswalk_metadata(combined, POPULATION_METHOD), diagnostics


def add_crosswalk_metadata(frame: pd.DataFrame, method_id: str) -> pd.DataFrame:
    weighting = {
        SIMPLE_METHOD: "normalized EPSG:5070 block-group/atomic intersection area",
        POPULATION_METHOD: (
            "2010 P0010001 block population allocated through official 2010-to-2020 "
            "relationship area and geometry-only 2020 atomic area; simple area fallback "
            "for zero-2010-population block groups"
        ),
    }[method_id]
    return frame.assign(
        source_dataset_id="acs5_2015_pa_b01003_summary_file",
        source_reference_period="2011-01-01/2015-12-31",
        target_precinct_dataset_id="pa_lrc_2021_release_1b_geography",
        target_precinct_effective_vintage="2021-10-05",
        target_senate_plan_id="pa_senate_2012_revised_final",
        target_senate_plan_reference_vintage="2012",
        method_id=method_id,
        method_version="1.0.0",
        weighting_universe=weighting,
        assignment_status="assigned",
        nearest_assignment_used=False,
    )


def normalize_crosswalk_dtypes(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in [
        "source_block_group_geoid",
        "target_precinct_geoid",
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
        "fallback_basis",
    ]:
        result[column] = result[column].astype("string")
    result["senate_district"] = result["senate_district"].astype("Int64")
    result["raw_support_value"] = result["raw_support_value"].astype("float64")
    result["weight"] = result["weight"].astype("float64")
    result["nearest_assignment_used"] = result["nearest_assignment_used"].astype("bool")
    return result


def aggregate_results(
    population: pd.DataFrame,
    crosswalks: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    allocated = crosswalks.merge(
        population,
        on="source_block_group_geoid",
        how="left",
        validate="many_to_one",
    )
    allocated["allocated_estimate"] = allocated["B01003_001E"] * allocated["weight"]
    allocated["allocated_moe"] = allocated["B01003_001M"] * allocated["weight"]
    allocated["allocated_moe_square"] = allocated["allocated_moe"].pow(2)
    precinct = aggregate_geography(allocated, "target_precinct_geoid")
    senate = aggregate_geography(allocated, "senate_district")
    return add_result_metadata(precinct, "fixed_precinct"), add_result_metadata(
        senate, "state_senate_district"
    )


def aggregate_geography(allocated: pd.DataFrame, geography_id: str) -> pd.DataFrame:
    result = allocated.groupby(["method_id", geography_id], as_index=False).agg(
        estimate=("allocated_estimate", "sum"),
        moe_square=("allocated_moe_square", "sum"),
        contributing_source_block_groups=("source_block_group_geoid", "nunique"),
    )
    result["margin_of_error"] = np.sqrt(result.pop("moe_square"))
    return result


def add_result_metadata(frame: pd.DataFrame, geography_level: str) -> pd.DataFrame:
    return frame.assign(
        population_product_id="acs5_2015",
        population_reference_start="2011-01-01",
        population_reference_end="2015-12-31",
        population_release_date="2016-12-08",
        source_geography_id="acs5_2015_block_group",
        target_snapshot_id="pa_lrc_2021_release_1b_geography",
        target_effective_vintage="2021-10-05",
        senate_plan_id="pa_senate_2012_revised_final",
        senate_plan_reference_vintage="2012",
        general_election_date=pd.NA,
        election_pairing_status="unpaired_method_poc015",
        applicable_senate_plan_elections="2014|2016|2018|2020",
        geography_level=geography_level,
        estimate_metric="B01003_001E",
        moe_metric="B01003_001M",
        moe_confidence_level=0.90,
        moe_aggregation_method="weighted_source_moe_then_root_sum_square_v1",
        population_universe="total_population",
    )


def compare_results(frame: pd.DataFrame, geography_id: str) -> pd.DataFrame:
    estimate = frame.pivot(index=geography_id, columns="method_id", values="estimate")
    estimate = estimate.rename(
        columns={
            SIMPLE_METHOD: "estimate_simple_area",
            POPULATION_METHOD: "estimate_2010_population_informed",
        }
    )
    margin = frame.pivot(
        index=geography_id, columns="method_id", values="margin_of_error"
    )
    margin = margin.rename(
        columns={
            SIMPLE_METHOD: "moe_simple_area",
            POPULATION_METHOD: "moe_2010_population_informed",
        }
    )
    result = estimate.join(margin).reset_index()
    result["estimate_delta_population_minus_area"] = (
        result["estimate_2010_population_informed"] - result["estimate_simple_area"]
    )
    result["moe_delta_population_minus_area"] = (
        result["moe_2010_population_informed"] - result["moe_simple_area"]
    )
    return result.sort_values(geography_id).reset_index(drop=True)


def validate_crosswalk_method(
    crosswalks: pd.DataFrame,
    population: pd.DataFrame,
    method_id: str,
) -> list[dict[str, object]]:
    method = crosswalks[crosswalks["method_id"].eq(method_id)]
    weights = method.groupby("source_block_group_geoid")["weight"].sum()
    allocated = method.merge(
        population,
        on="source_block_group_geoid",
        validate="many_to_one",
    )
    allocated["allocated_estimate"] = allocated["B01003_001E"] * allocated["weight"]
    allocated["allocated_moe_linear"] = allocated["B01003_001M"] * allocated["weight"]
    reconstructed = allocated.groupby("source_block_group_geoid").agg(
        estimate=("allocated_estimate", "sum"),
        margin_of_error=("allocated_moe_linear", "sum"),
    )
    source = population.set_index("source_block_group_geoid")
    return [
        check(
            f"{method_id}_all_sources",
            method["source_block_group_geoid"].nunique()
            == EXPECTED["source_block_groups"],
            int(method["source_block_group_geoid"].nunique()),
        ),
        check(
            f"{method_id}_weights_in_range",
            bool(method["weight"].between(0, 1, inclusive="both").all()),
            int((~method["weight"].between(0, 1, inclusive="both")).sum()),
        ),
        check(
            f"{method_id}_weights_sum_to_one",
            bool(weights.sub(1).abs().le(WEIGHT_TOLERANCE).all()),
            float(weights.sub(1).abs().max()),
        ),
        check(
            f"{method_id}_all_precincts_supported",
            method["target_precinct_geoid"].nunique() == EXPECTED["fixed_precincts"],
            int(method["target_precinct_geoid"].nunique()),
        ),
        check(
            f"{method_id}_all_senate_districts_supported",
            method["senate_district"].nunique() == EXPECTED["senate_districts"],
            int(method["senate_district"].nunique()),
        ),
        check(
            f"{method_id}_source_estimates_reconstruct",
            bool(
                reconstructed["estimate"]
                .sub(source["B01003_001E"])
                .abs()
                .le(ESTIMATE_TOLERANCE)
                .all()
            ),
            float(reconstructed["estimate"].sub(source["B01003_001E"]).abs().max()),
        ),
        check(
            f"{method_id}_source_moes_reconstruct_linearly",
            bool(
                reconstructed["margin_of_error"]
                .sub(source["B01003_001M"])
                .abs()
                .le(ESTIMATE_TOLERANCE)
                .all()
            ),
            float(
                reconstructed["margin_of_error"].sub(source["B01003_001M"]).abs().max()
            ),
        ),
    ]


def build_checks(
    population: pd.DataFrame,
    block_groups: gpd.GeoDataFrame,
    atoms: gpd.GeoDataFrame,
    crosswalks: pd.DataFrame,
    precinct_result: pd.DataFrame,
    senate_result: pd.DataFrame,
    simple_diagnostics: dict[str, object],
    informed_diagnostics: dict[str, object],
) -> list[dict[str, object]]:
    source_ids = set(population["source_block_group_geoid"])
    geometry_ids = set(block_groups["GEOID"])
    checks = [
        check(
            "source_block_group_count",
            len(population) == EXPECTED["source_block_groups"],
            len(population),
        ),
        check(
            "source_ids_unique",
            population["source_block_group_geoid"].is_unique,
            int(population["source_block_group_geoid"].nunique()),
        ),
        check(
            "source_estimate_total",
            int(population["B01003_001E"].sum()) == EXPECTED["estimate"],
            int(population["B01003_001E"].sum()),
        ),
        check(
            "source_moes_present_nonnegative",
            bool(population["B01003_001M"].notna().all())
            and bool(population["B01003_001M"].ge(0).all()),
            {
                "missing": int(population["B01003_001M"].isna().sum()),
                "negative": int(population["B01003_001M"].lt(0).sum()),
            },
        ),
        check(
            "source_zero_estimate_count",
            int(population["B01003_001E"].eq(0).sum())
            == EXPECTED["zero_estimate_block_groups"],
            int(population["B01003_001E"].eq(0).sum()),
        ),
        check(
            "source_counties",
            population["source_block_group_geoid"].str.slice(2, 5).nunique()
            == EXPECTED["source_counties"],
            int(population["source_block_group_geoid"].str.slice(2, 5).nunique()),
        ),
        check(
            "geometry_count",
            len(block_groups) == EXPECTED["source_block_groups"],
            len(block_groups),
        ),
        check(
            "geometry_ids_match_population",
            geometry_ids == source_ids,
            {
                "population_only": len(source_ids - geometry_ids),
                "geometry_only": len(geometry_ids - source_ids),
            },
        ),
        check(
            "geometry_crs", block_groups.crs.to_epsg() == 4269, str(block_groups.crs)
        ),
        check(
            "geometry_valid",
            bool(
                block_groups.geometry.notna().all()
                and (~block_groups.geometry.is_empty).all()
                and block_groups.geometry.is_valid.all()
            ),
            {
                "missing": int(block_groups.geometry.isna().sum()),
                "empty": int(block_groups.geometry.is_empty.sum()),
                "invalid": int((~block_groups.geometry.is_valid).sum()),
            },
        ),
        check(
            "atomic_precinct_count",
            atoms["target_precinct_geoid"].nunique() == EXPECTED["fixed_precincts"],
            int(atoms["target_precinct_geoid"].nunique()),
        ),
        check(
            "atomic_senate_count",
            atoms["senate_district"].nunique() == EXPECTED["senate_districts"],
            int(atoms["senate_district"].nunique()),
        ),
        check(
            "simple_area_all_sources_intersect",
            simple_diagnostics["assigned_source_block_groups"]
            == EXPECTED["source_block_groups"],
            simple_diagnostics["assigned_source_block_groups"],
        ),
        check(
            "population_method_zero_support_fallback_count",
            informed_diagnostics["zero_2010_support_block_groups"]
            == EXPECTED["zero_2010_support_block_groups"],
            informed_diagnostics["zero_2010_support_block_groups"],
        ),
        check(
            "no_nearest_assignments",
            not bool(crosswalks["nearest_assignment_used"].any()),
            int(crosswalks["nearest_assignment_used"].sum()),
        ),
    ]
    for method_id in [SIMPLE_METHOD, POPULATION_METHOD]:
        checks.extend(validate_crosswalk_method(crosswalks, population, method_id))
        precinct = precinct_result[precinct_result["method_id"].eq(method_id)]
        senate = senate_result[senate_result["method_id"].eq(method_id)]
        checks.extend(
            [
                check(
                    f"{method_id}_precinct_result_count",
                    len(precinct) == EXPECTED["fixed_precincts"],
                    len(precinct),
                ),
                check(
                    f"{method_id}_senate_result_count",
                    len(senate) == EXPECTED["senate_districts"],
                    len(senate),
                ),
                check(
                    f"{method_id}_precinct_estimate_conserved",
                    abs(precinct["estimate"].sum() - EXPECTED["estimate"])
                    <= ESTIMATE_TOLERANCE,
                    float(precinct["estimate"].sum()),
                ),
                check(
                    f"{method_id}_senate_estimate_conserved",
                    abs(senate["estimate"].sum() - EXPECTED["estimate"])
                    <= ESTIMATE_TOLERANCE,
                    float(senate["estimate"].sum()),
                ),
                check(
                    f"{method_id}_source_counties_conserved",
                    source_county_max_delta(crosswalks, population, method_id)
                    <= ESTIMATE_TOLERANCE,
                    source_county_max_delta(crosswalks, population, method_id),
                ),
                check(
                    f"{method_id}_target_moes_finite_nonnegative",
                    bool(np.isfinite(precinct["margin_of_error"]).all())
                    and bool(precinct["margin_of_error"].ge(0).all())
                    and bool(np.isfinite(senate["margin_of_error"]).all())
                    and bool(senate["margin_of_error"].ge(0).all()),
                    {
                        "precinct_min": float(precinct["margin_of_error"].min()),
                        "senate_min": float(senate["margin_of_error"].min()),
                    },
                ),
            ]
        )
    return checks


def source_county_max_delta(
    crosswalks: pd.DataFrame,
    population: pd.DataFrame,
    method_id: str,
) -> float:
    method = crosswalks[crosswalks["method_id"].eq(method_id)]
    allocated = method.merge(
        population,
        on="source_block_group_geoid",
        validate="many_to_one",
    )
    allocated["county_fips"] = allocated["source_block_group_geoid"].str.slice(2, 5)
    allocated["allocated"] = allocated["B01003_001E"] * allocated["weight"]
    observed = allocated.groupby("county_fips")["allocated"].sum()
    expected = (
        population.assign(
            county_fips=population["source_block_group_geoid"].str.slice(2, 5)
        )
        .groupby("county_fips")["B01003_001E"]
        .sum()
    )
    return float(observed.sub(expected).abs().max())


def comparison_summary(
    precinct: pd.DataFrame,
    senate: pd.DataFrame,
) -> dict[str, object]:
    precinct_estimate = precinct["estimate_delta_population_minus_area"]
    precinct_moe = precinct["moe_delta_population_minus_area"]
    senate_estimate = senate["estimate_delta_population_minus_area"]
    senate_moe = senate["moe_delta_population_minus_area"]
    return {
        "precincts_with_estimate_delta": int(precinct_estimate.abs().gt(1e-6).sum()),
        "precinct_estimate_total_absolute_delta": float(precinct_estimate.abs().sum()),
        "precinct_estimate_max_absolute_delta": float(precinct_estimate.abs().max()),
        "precinct_moe_total_absolute_delta": float(precinct_moe.abs().sum()),
        "precinct_moe_max_absolute_delta": float(precinct_moe.abs().max()),
        "senate_districts_with_estimate_delta": int(
            senate_estimate.abs().gt(1e-6).sum()
        ),
        "senate_estimate_total_absolute_delta": float(senate_estimate.abs().sum()),
        "senate_estimate_max_absolute_delta": float(senate_estimate.abs().max()),
        "senate_moe_total_absolute_delta": float(senate_moe.abs().sum()),
        "senate_moe_max_absolute_delta": float(senate_moe.abs().max()),
    }


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


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(qa: dict[str, object]) -> str:
    comparison = qa["comparison"]
    informed = qa["population_informed_diagnostics"]
    return f"""# POC015 representative ACS block-group method proof

Status: **{"PASS" if qa["passed"] else "FAIL"}**

- Product: 2011–2015 ACS five-year B01003, released 2016-12-08
- Source block groups: {EXPECTED["source_block_groups"]:,}
- Source estimate: {EXPECTED["estimate"]:,}
- Fixed 2021 LRC precincts: {EXPECTED["fixed_precincts"]:,}
- 2012 Revised Final Senate districts: {EXPECTED["senate_districts"]:,}
- Zero-2010-population area fallbacks: {informed["zero_2010_support_block_groups"]:,}
- Precinct estimate total absolute method delta: {comparison["precinct_estimate_total_absolute_delta"]:,.3f}
- Precinct MOE total absolute method delta: {comparison["precinct_moe_total_absolute_delta"]:,.3f}
- Senate estimate total absolute method delta: {comparison["senate_estimate_total_absolute_delta"]:,.3f}
- Senate MOE total absolute method delta: {comparison["senate_moe_total_absolute_delta"]:,.3f}
- Nearest-boundary assignments: 0

The simple route normalizes direct EPSG:5070 block-group intersection area.
The population-informed route distributes each ACS block-group estimate and MOE
using 2010 Census block population carried through the accepted official
2010-to-2020 relationship/geometry-only atomic bridge. Block groups with zero
2010 population use an explicit simple-area fallback.

For each target, the estimate is the sum of weighted source estimates. The
source 90% MOE is first scaled by the same fixed allocation weight, then target
MOEs are approximated by root-sum-square across contributing source block
groups. The approximation excludes unavailable covariance and allocation-weight
uncertainty; MOEs are never summed as counts. Product-to-election availability
pairing remains POC019.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC015 {'passed' if qa['passed'] else 'failed'}")


if __name__ == "__main__":
    main()
