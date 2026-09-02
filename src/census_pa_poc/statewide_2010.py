"""Produce the POC011 statewide 2010 fixed-precinct and Senate proof."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

from census_pa_poc.fixed_geography import load_lrc_blocks
from census_pa_poc.senate_overlay import logical_geoframe_hash
from census_pa_poc.sources import (
    load_2010_2020_block_relationship,
    load_2010_census_blocks,
    load_2010_pl94_block_population,
    sha256,
)
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

AREA_CRS = "EPSG:5070"
WEIGHT_TOLERANCE = 1e-12
POPULATION_TOLERANCE = 1e-6
EXPECTED = {
    "source_blocks": 421_545,
    "relationship_rows": 464_515,
    "relationship_sources": 421_542,
    "fixed_precincts": 9_178,
    "senate_districts": 50,
    "counties": 67,
    "population": 12_702_379,
}

SOURCES = {
    "census_population": {
        "source_id": "census_2010_pa_pl",
        "producer": "U.S. Census Bureau",
        "product": "2010 Census Redistricting Data PL 94-171 Summary File",
        "reference_vintage": "2010-04-01",
        "effective_vintage": "2010-04-01",
        "release_date": "2011-03-09",
        "url": (
            "https://www2.census.gov/census_2010/"
            "01-Redistricting_File--PL_94-171/Pennsylvania/pa2010.pl.zip"
        ),
        "sha256": "3cf2460ea17d1be087d9b12700e45962b164f6233f8c1071ddc67ab55392951a",
        "license_access": "Public federal data; cite U.S. Census Bureau",
        "crs": None,
        "schema": {
            "format": "fixed-width geography plus comma-delimited File 01",
            "geography_member": "pageo2010.pl",
            "file01_member": "pa000012010.pl",
            "join": "LOGRECNO",
            "metric": "P0010001 (File 01 field 6)",
        },
        "geographic_universe": "2010 Census tabulation blocks in Pennsylvania",
        "population_universe": "Standard total population, P0010001",
        "relative_path": "data/raw/census_2010_pa_pl/pa2010.pl.zip",
    },
    "census_blocks": {
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
            "area_fields": ["ALAND10", "AWATER10"],
        },
        "geographic_universe": "2010 Census tabulation blocks in Pennsylvania",
        "population_universe": None,
        "relative_path": (
            "data/raw/census_2010_pa_blocks/tl_2010_42_tabblock10.zip"
        ),
    },
    "block_relationship": {
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
        "license_access": "Public federal data; acknowledge U.S. Census Bureau",
        "crs": None,
        "schema": {
            "format": "pipe-delimited UTF-8 text in ZIP",
            "member": "tab2010_tab2020_st42_pa.txt",
            "weight_fields": ["AREALAND_INT", "AREAWATER_INT"],
            "population_fields": [],
        },
        "geographic_universe": (
            "2010 blocks related to 2020 Pennsylvania blocks; four incoming "
            "cross-state rows are excluded from the PA source universe"
        ),
        "population_universe": None,
        "relative_path": (
            "data/raw/census_2010_2020_block_relationship_pa/"
            "TAB2010_TAB2020_ST42.zip"
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
            "target_fields": ["STATEFP20", "COUNTYFP20", "VTDST20"],
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
    "artifact_id": "pa_senate_2001_final_fixed_precinct_overlay_v3",
    "producer": "POC022",
    "product": "Fixed 2021 LRC precinct to 2001 Final Senate geometry overlay",
    "source_precinct_dataset_id": "pa_lrc_2021_release_1b_geography",
    "source_precinct_effective_vintage": "2021-10-05",
    "target_senate_plan_id": "pa_senate_2001_final",
    "target_senate_plan_reference_vintage": "2001",
    "method_id": "fixed_precinct_senate_overlay_v3",
    "weighting_universe": "EPSG:5070 fixed precinct polygon area",
    "logical_sha256": "4e28ffbafc81599dea78f06f15944c1895e1cd459460021cd2348c3909f85aeb",
    "relative_path": (
        "data/processed/senate_overlays/"
        "pa_senate_2001_final_fixed_precinct_overlay_v3.parquet"
    ),
}


def run(root: Path) -> dict[str, object]:
    """Execute POC011 from frozen inputs through two comparable allocations."""
    root = root.resolve()
    artifact_dir = root / "artifacts/work/poc011"
    processed_dir = root / "data/processed/statewide_2010"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    require_manifest_hashes(manifest)

    population = load_2010_pl94_block_population(
        root / SOURCES["census_population"]["relative_path"]
    )
    blocks = load_2010_census_blocks(root / SOURCES["census_blocks"]["relative_path"])
    relationship = load_2010_2020_block_relationship(
        root / SOURCES["block_relationship"]["relative_path"]
    )
    lrc_blocks = load_lrc_blocks(root / SOURCES["lrc_geography"]["relative_path"])
    atoms = gpd.read_parquet(root / OVERLAY["relative_path"])[
        ["target_precinct_geoid", "senate_district", "geometry"]
    ]

    direct, direct_diagnostics = build_direct_atomic_crosswalk(blocks, atoms)
    target_2020, target_diagnostics = build_2020_atomic_crosswalk(lrc_blocks, atoms)
    relationship_crosswalk, relationship_diagnostics = (
        build_relationship_atomic_crosswalk(
            relationship,
            target_2020,
            set(population["source_block_geoid"]),
        )
    )
    relationship_diagnostics["target_2020_atomic"] = target_diagnostics

    direct = add_zero_population_exceptions(direct, population)
    relationship_crosswalk = add_zero_population_exceptions(
        relationship_crosswalk, population
    )
    direct_diagnostics.update(
        direct_exception_population_diagnostics(
            direct_diagnostics,
            population,
            relationship,
        )
    )
    crosswalks = pd.concat([direct, relationship_crosswalk], ignore_index=True)
    crosswalks = crosswalks.sort_values(
        ["method_id", "source_block_geoid", "target_precinct_geoid", "senate_district"],
        kind="stable",
        na_position="last",
    ).reset_index(drop=True)
    crosswalks = normalize_crosswalk_dtypes(crosswalks)

    precinct_result, senate_result = aggregate_results(population, crosswalks)
    precinct_comparison = compare_results(
        precinct_result, "target_precinct_geoid"
    )
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
            processed_dir / "block_to_fixed_precinct_2001_senate_v2.parquet",
            [
                "method_id",
                "source_block_geoid",
                "target_precinct_geoid",
                "senate_district",
            ],
        ),
        "precinct_population": write_immutable_parquet(
            precinct_result,
            processed_dir / "fixed_precinct_population_2010_v1.parquet",
            ["method_id", "target_precinct_geoid"],
        ),
        "senate_population": write_immutable_parquet(
            senate_result,
            processed_dir / "senate_population_2010_2001_plan_v1.parquet",
            ["method_id", "senate_district"],
        ),
        "precinct_method_comparison": write_immutable_parquet(
            precinct_comparison,
            processed_dir / "precinct_method_comparison_2010_v1.parquet",
            ["target_precinct_geoid"],
        ),
        "senate_method_comparison": write_immutable_parquet(
            senate_comparison,
            processed_dir / "senate_method_comparison_2010_v1.parquet",
            ["senate_district"],
        ),
    }
    qa = {
        "task": "POC011",
        "direct_method_id": "direct_atomic_area_2010_v1",
        "relationship_method_id": "relationship_atomic_area_2010_v1",
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
            "POC011 QA failed; inspect artifacts/work/poc011/qa_results.json"
        )
    return qa


def build_direct_atomic_crosswalk(
    source_blocks: gpd.GeoDataFrame, atoms: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Intersect 2010 blocks directly with precinct/Senate atomic targets."""
    sources = source_blocks[["GEOID10", "geometry"]].rename(
        columns={"GEOID10": "source_block_geoid"}
    ).to_crs(AREA_CRS)
    targets = atoms.to_crs(AREA_CRS)
    intersections = gpd.overlay(
        sources,
        targets,
        how="intersection",
        keep_geom_type=True,
    )
    intersections = intersections[~intersections.geometry.is_empty].copy()
    intersections["intersection_area_square_meters"] = intersections.geometry.area
    intersections = intersections[
        intersections["intersection_area_square_meters"].gt(0)
    ]
    grouped = (
        intersections.groupby(
            ["source_block_geoid", "target_precinct_geoid", "senate_district"],
            as_index=False,
        )["intersection_area_square_meters"]
        .sum()
        .sort_values(
            ["source_block_geoid", "target_precinct_geoid", "senate_district"]
        )
    )
    covered_area = grouped.groupby("source_block_geoid")[
        "intersection_area_square_meters"
    ].transform("sum")
    grouped["weight"] = grouped["intersection_area_square_meters"] / covered_area

    source_area = sources.set_index("source_block_geoid").geometry.area
    covered_by_source = grouped.groupby("source_block_geoid")[
        "intersection_area_square_meters"
    ].sum()
    coverage = covered_by_source / source_area.reindex(covered_by_source.index)
    target_union = shapely.union_all(targets.geometry.array)
    representative_points = shapely.point_on_surface(sources.geometry.array)
    point_covered = pd.Series(
        shapely.covers(target_union, representative_points),
        index=sources["source_block_geoid"],
    )
    diagnostics = {
        "raw_intersection_rows": len(intersections),
        "allocation_rows_before_exceptions": len(grouped),
        "assigned_source_blocks": int(grouped["source_block_geoid"].nunique()),
        "uncovered_source_blocks": int(
            source_blocks["GEOID10"].nunique()
            - grouped["source_block_geoid"].nunique()
        ),
        "minimum_coverage_ratio": float(coverage.min()),
        "sources_below_99_percent_coverage": int(coverage.lt(0.99).sum()),
        "sources_below_90_percent_coverage": int(coverage.lt(0.90).sum()),
        "representative_points_uncovered": int((~point_covered).sum()),
        "representative_point_uncovered_ids": sorted(point_covered[~point_covered].index),
        "normalization": "weights normalized over covered EPSG:5070 area",
        "nearest_assignment_count": 0,
    }
    return add_crosswalk_metadata(grouped, "direct_atomic_area_2010_v1"), diagnostics


def build_2020_atomic_crosswalk(
    lrc_blocks: gpd.GeoDataFrame, atoms: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build a geometry-only 2020 parent-block to atomic-target aid."""
    fragments = lrc_blocks[["GEOID20", "geometry"]].copy()
    fragments["target_2020_block_geoid"] = fragments["GEOID20"].str.slice(0, 15)
    fragments = fragments[["target_2020_block_geoid", "geometry"]].to_crs(AREA_CRS)
    targets = atoms.to_crs(AREA_CRS)
    intersections = gpd.overlay(
        fragments,
        targets,
        how="intersection",
        keep_geom_type=True,
    )
    intersections = intersections[~intersections.geometry.is_empty].copy()
    intersections["atomic_area_square_meters"] = intersections.geometry.area
    intersections = intersections[intersections["atomic_area_square_meters"].gt(0)]
    grouped = intersections.groupby(
        ["target_2020_block_geoid", "target_precinct_geoid", "senate_district"],
        as_index=False,
    )["atomic_area_square_meters"].sum()
    covered = grouped.groupby("target_2020_block_geoid")[
        "atomic_area_square_meters"
    ].transform("sum")
    grouped["target_atomic_weight"] = grouped["atomic_area_square_meters"] / covered
    diagnostics = {
        "raw_intersection_rows": len(intersections),
        "allocation_rows": len(grouped),
        "target_2020_parent_blocks": int(grouped["target_2020_block_geoid"].nunique()),
        "fixed_precincts": int(grouped["target_precinct_geoid"].nunique()),
        "senate_districts": int(grouped["senate_district"].nunique()),
        "weighting_universe": "2020 corrected-fragment EPSG:5070 area only",
    }
    return grouped, diagnostics


def build_relationship_atomic_crosswalk(
    relationship: pd.DataFrame,
    target_2020: pd.DataFrame,
    expected_source_ids: set[str],
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Compose official relationship areas with 2020 atomic target areas."""
    relation = relationship[
        [
            "source_block_geoid",
            "target_2020_block_geoid",
            "AREALAND_2010",
            "AREAWATER_2010",
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
        target_2020,
        on="target_2020_block_geoid",
        how="left",
        validate="many_to_many",
    )
    missing_target_rows = composed["target_precinct_geoid"].isna()
    composed["component_weight"] = (
        composed["relationship_weight"] * composed["target_atomic_weight"]
    )
    grouped = composed[~missing_target_rows].groupby(
        ["source_block_geoid", "target_precinct_geoid", "senate_district"],
        as_index=False,
    )["component_weight"].sum()
    raw_sums = grouped.groupby("source_block_geoid")["component_weight"].transform(
        "sum"
    )
    grouped["weight"] = grouped["component_weight"] / raw_sums
    grouped = grouped.rename(columns={"component_weight": "raw_composed_weight"})

    observed_source_ids = set(grouped["source_block_geoid"])
    missing_source_ids = sorted(expected_source_ids - observed_source_ids)
    source_area = relation.groupby("source_block_geoid").agg(
        source_area=("AREALAND_2010", "first"),
        source_water=("AREAWATER_2010", "first"),
        intersection_area=("AREALAND_INT", "sum"),
        intersection_water=("AREAWATER_INT", "sum"),
    )
    source_area["published_source_area"] = (
        source_area["source_area"] + source_area["source_water"]
    )
    source_area["published_intersection_area"] = (
        source_area["intersection_area"] + source_area["intersection_water"]
    )
    area_mismatch = source_area["published_source_area"].ne(
        source_area["published_intersection_area"]
    )
    diagnostics = {
        "relationship_rows": len(relationship),
        "relationship_source_blocks": int(
            relationship["source_block_geoid"].nunique()
        ),
        "relationship_target_2020_blocks": int(
            relationship["target_2020_block_geoid"].nunique()
        ),
        "relationship_split_source_blocks": int(
            relationship.groupby("source_block_geoid").size().gt(1).sum()
        ),
        "relationship_max_rows_per_source": int(
            relationship.groupby("source_block_geoid").size().max()
        ),
        "relationship_source_area_mismatches": int(area_mismatch.sum()),
        "relationship_minimum_area_coverage_ratio": float(
            (
                source_area["published_intersection_area"]
                / source_area["published_source_area"]
            ).min()
        ),
        "missing_target_atomic_rows": int(missing_target_rows.sum()),
        "assigned_source_blocks": len(observed_source_ids),
        "missing_source_blocks_before_exceptions": len(missing_source_ids),
        "missing_source_ids": missing_source_ids,
        "allocation_rows_before_exceptions": len(grouped),
        "normalization": (
            "relationship intersection land+water area, then 2020 corrected-fragment "
            "atomic area; normalized per 2010 source block"
        ),
        "nearest_assignment_count": 0,
    }
    return add_crosswalk_metadata(grouped, "relationship_atomic_area_2010_v1"), diagnostics


def add_crosswalk_metadata(frame: pd.DataFrame, method_id: str) -> pd.DataFrame:
    weighting = {
        "direct_atomic_area_2010_v1": "direct EPSG:5070 polygon intersection area",
        "relationship_atomic_area_2010_v1": (
            "official relationship land+water area composed with 2020 atomic area"
        ),
    }[method_id]
    return frame.assign(
        source_dataset_id="census_2010_pa_blocks",
        source_reference_vintage="2010",
        target_precinct_dataset_id="pa_lrc_2021_release_1b_geography",
        target_precinct_effective_vintage="2021-10-05",
        target_senate_plan_id="pa_senate_2001_final",
        target_senate_plan_reference_vintage="2001",
        method_id=method_id,
        method_version="1.0.0",
        weighting_universe=weighting,
        assignment_status="assigned",
        nearest_assignment_used=False,
    )


def add_zero_population_exceptions(
    crosswalk: pd.DataFrame, population: pd.DataFrame
) -> pd.DataFrame:
    """Add typed rows only for uncovered source blocks with zero population."""
    missing = population[
        ~population["source_block_geoid"].isin(crosswalk["source_block_geoid"])
    ]
    if missing.empty:
        return crosswalk
    if not missing["P0010001"].eq(0).all():
        ids = missing.loc[missing["P0010001"].ne(0), "source_block_geoid"].tolist()
        raise ValueError(f"Material uncovered populated 2010 source blocks: {ids}")
    template = crosswalk.iloc[:0].copy()
    rows = []
    for source_id in missing["source_block_geoid"]:
        row = {column: pd.NA for column in template.columns}
        row.update(
            {
                "source_block_geoid": source_id,
                "weight": 0.0,
                "source_dataset_id": "census_2010_pa_blocks",
                "source_reference_vintage": "2010",
                "target_precinct_dataset_id": "pa_lrc_2021_release_1b_geography",
                "target_precinct_effective_vintage": "2021-10-05",
                "target_senate_plan_id": "pa_senate_2001_final",
                "target_senate_plan_reference_vintage": "2001",
                "method_id": crosswalk["method_id"].iloc[0],
                "method_version": "1.0.0",
                "weighting_universe": crosswalk["weighting_universe"].iloc[0],
                "assignment_status": "zero_population_uncovered_exception",
                "nearest_assignment_used": False,
            }
        )
        rows.append(row)
    return pd.concat([crosswalk, pd.DataFrame(rows)], ignore_index=True)


def normalize_crosswalk_dtypes(frame: pd.DataFrame) -> pd.DataFrame:
    """Make nullable identifiers stable across a Parquet round trip."""
    result = frame.copy()
    string_columns = [
        "source_block_geoid",
        "target_precinct_geoid",
        "source_dataset_id",
        "source_reference_vintage",
        "target_precinct_dataset_id",
        "target_precinct_effective_vintage",
        "target_senate_plan_id",
        "target_senate_plan_reference_vintage",
        "method_id",
        "method_version",
        "weighting_universe",
        "assignment_status",
    ]
    for column in string_columns:
        result[column] = result[column].astype("string")
    result["senate_district"] = result["senate_district"].astype("Int64")
    for column in [
        "intersection_area_square_meters",
        "weight",
        "raw_composed_weight",
    ]:
        result[column] = pd.to_numeric(result[column], errors="coerce").astype(
            "float64"
        )
    result["nearest_assignment_used"] = result[
        "nearest_assignment_used"
    ].astype("bool")
    return result


def aggregate_results(
    population: pd.DataFrame, crosswalks: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    assigned = crosswalks[crosswalks["assignment_status"].eq("assigned")]
    allocated = assigned.merge(
        population,
        on="source_block_geoid",
        how="left",
        validate="many_to_one",
    )
    allocated["allocated_population"] = allocated["P0010001"] * allocated["weight"]
    precinct = allocated.groupby(
        ["method_id", "target_precinct_geoid"], as_index=False
    )["allocated_population"].sum()
    precinct = precinct.rename(columns={"allocated_population": "population"})
    senate = allocated.groupby(["method_id", "senate_district"], as_index=False)[
        "allocated_population"
    ].sum()
    senate = senate.rename(columns={"allocated_population": "population"})
    return add_result_metadata(precinct, "fixed_precinct"), add_result_metadata(
        senate, "state_senate_district"
    )


def add_result_metadata(frame: pd.DataFrame, geography_level: str) -> pd.DataFrame:
    return frame.assign(
        population_product_id="census_2010_pa_pl",
        population_reference_date="2010-04-01",
        population_release_date="2011-03-09",
        source_geography_id="census_2010_pa_blocks",
        source_reference_vintage="2010",
        target_snapshot_id="pa_lrc_2021_release_1b_geography",
        target_effective_vintage="2021-10-05",
        senate_plan_id="pa_senate_2001_final",
        senate_plan_reference_vintage="2001",
        general_election_date=pd.NA,
        election_pairing_status="unpaired_geography_product_poc011",
        applicable_general_elections="2002|2004|2006|2008|2010|2012",
        geography_level=geography_level,
        metric="P0010001",
        population_universe="standard_total_population",
    )


def compare_results(frame: pd.DataFrame, geography_id: str) -> pd.DataFrame:
    pivot = frame.pivot(index=geography_id, columns="method_id", values="population")
    pivot = pivot.reset_index()
    pivot["delta_direct_minus_relationship"] = (
        pivot["direct_atomic_area_2010_v1"]
        - pivot["relationship_atomic_area_2010_v1"]
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
    exception_ids = set(exceptions["source_block_geoid"])
    zero_ids = set(
        population.loc[population["P0010001"].eq(0), "source_block_geoid"]
    )
    return [
        check(
            f"{method_id}_all_source_rows_or_exceptions",
            method["source_block_geoid"].nunique() == EXPECTED["source_blocks"],
            int(method["source_block_geoid"].nunique()),
        ),
        check(
            f"{method_id}_all_positive_sources_assigned",
            positive_ids.issubset(set(assigned["source_block_geoid"])),
            len(positive_ids - set(assigned["source_block_geoid"])),
        ),
        check(
            f"{method_id}_exceptions_zero_population",
            exception_ids.issubset(zero_ids),
            {"exceptions": len(exception_ids), "nonzero": len(exception_ids - zero_ids)},
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
    geometry_ids = set(blocks["GEOID10"])
    checks = [
        check("source_block_count", len(population) == EXPECTED["source_blocks"], len(population)),
        check("source_block_ids_unique", population["source_block_geoid"].is_unique, int(population["source_block_geoid"].nunique())),
        check("source_population_total", int(population["P0010001"].sum()) == EXPECTED["population"], int(population["P0010001"].sum())),
        check("geometry_block_count", len(blocks) == EXPECTED["source_blocks"], len(blocks)),
        check("geometry_ids_match_population", geometry_ids == population_ids, {"population": len(population_ids), "geometry": len(geometry_ids)}),
        check("geometry_crs", blocks.crs.to_epsg() == 4269, str(blocks.crs)),
        check("geometry_valid", bool(blocks.geometry.notna().all() and (~blocks.geometry.is_empty).all() and blocks.geometry.is_valid.all()), {"null": int(blocks.geometry.isna().sum()), "empty": int(blocks.geometry.is_empty.sum()), "invalid": int((~blocks.geometry.is_valid).sum())}),
        check("relationship_row_count", len(relationship) == EXPECTED["relationship_rows"], len(relationship)),
        check("relationship_source_count", relationship["source_block_geoid"].nunique() == EXPECTED["relationship_sources"], int(relationship["source_block_geoid"].nunique())),
        check("relationship_missing_sources_are_zero_population", set(relationship_diagnostics["missing_source_ids"]).issubset(set(population.loc[population["P0010001"].eq(0), "source_block_geoid"])), relationship_diagnostics["missing_source_ids"]),
        check("atomic_precinct_count", atoms["target_precinct_geoid"].nunique() == EXPECTED["fixed_precincts"], int(atoms["target_precinct_geoid"].nunique())),
        check("atomic_senate_district_count", atoms["senate_district"].nunique() == EXPECTED["senate_districts"], int(atoms["senate_district"].nunique())),
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
        check("relationship_target_atomic_complete", relationship_diagnostics["missing_target_atomic_rows"] == 0, relationship_diagnostics["missing_target_atomic_rows"]),
        check("no_nearest_assignments", not bool(crosswalks["nearest_assignment_used"].any()), int(crosswalks["nearest_assignment_used"].sum())),
    ]
    for method_id in ["direct_atomic_area_2010_v1", "relationship_atomic_area_2010_v1"]:
        checks.extend(validate_method_crosswalk(crosswalks, population, method_id))
        precinct_method = precinct_result[precinct_result["method_id"].eq(method_id)]
        senate_method = senate_result[senate_result["method_id"].eq(method_id)]
        checks.extend(
            [
                check(f"{method_id}_precinct_result_count", len(precinct_method) == EXPECTED["fixed_precincts"], len(precinct_method)),
                check(f"{method_id}_senate_result_count", len(senate_method) == EXPECTED["senate_districts"], len(senate_method)),
                check(f"{method_id}_precinct_population_conserved", abs(precinct_method["population"].sum() - EXPECTED["population"]) <= POPULATION_TOLERANCE, float(precinct_method["population"].sum())),
                check(f"{method_id}_senate_population_conserved", abs(senate_method["population"].sum() - EXPECTED["population"]) <= POPULATION_TOLERANCE, float(senate_method["population"].sum())),
                check(f"{method_id}_source_counties_conserved", source_counties_conserved(crosswalks, population, method_id), source_county_max_delta(crosswalks, population, method_id)),
            ]
        )
    return checks


def direct_exception_population_diagnostics(
    diagnostics: dict[str, object],
    population: pd.DataFrame,
    relationship: pd.DataFrame,
) -> dict[str, object]:
    """Type direct-geometry linework exceptions against published support."""
    ids = diagnostics["representative_point_uncovered_ids"]
    values = population.set_index("source_block_geoid")["P0010001"].reindex(ids)
    populated = values[values.gt(0)]
    relationship_ids = set(relationship["source_block_geoid"])
    unsupported = set(populated.index) - relationship_ids
    return {
        "populated_representative_point_exceptions": len(populated),
        "populated_representative_point_exception_population": int(populated.sum()),
        "populated_representative_point_exception_ids": sorted(populated.index),
        "populated_representative_point_exceptions_without_relationship_support": len(
            unsupported
        ),
        "exception_policy": (
            "retain direct covered-area normalization only where the official "
            "relationship file supplies the populated source; never use nearest"
        ),
    }


def source_county_max_delta(
    crosswalks: pd.DataFrame, population: pd.DataFrame, method_id: str
) -> float:
    assigned = crosswalks[
        crosswalks["method_id"].eq(method_id)
        & crosswalks["assignment_status"].eq("assigned")
    ]
    allocated = assigned.merge(population, on="source_block_geoid", validate="many_to_one")
    allocated["county_fips"] = allocated["source_block_geoid"].str.slice(2, 5)
    allocated["allocated"] = allocated["P0010001"] * allocated["weight"]
    observed = allocated.groupby("county_fips")["allocated"].sum()
    expected = (
        population.assign(county_fips=population["source_block_geoid"].str.slice(2, 5))
        .groupby("county_fips")["P0010001"]
        .sum()
    )
    return float(observed.sub(expected).abs().max())


def source_counties_conserved(
    crosswalks: pd.DataFrame, population: pd.DataFrame, method_id: str
) -> bool:
    return source_county_max_delta(crosswalks, population, method_id) <= POPULATION_TOLERANCE


def comparison_summary(
    precinct_comparison: pd.DataFrame, senate_comparison: pd.DataFrame
) -> dict[str, object]:
    precinct_delta = precinct_comparison["delta_direct_minus_relationship"]
    senate_delta = senate_comparison["delta_direct_minus_relationship"]
    return {
        "precincts_with_nontrivial_delta": int(precinct_delta.abs().gt(1e-6).sum()),
        "precinct_total_absolute_delta": float(precinct_delta.abs().sum()),
        "precinct_max_absolute_delta": float(precinct_delta.abs().max()),
        "senate_districts_with_nontrivial_delta": int(senate_delta.abs().gt(1e-6).sum()),
        "senate_total_absolute_delta": float(senate_delta.abs().sum()),
        "senate_max_absolute_delta": float(senate_delta.abs().max()),
    }


def build_manifest(root: Path) -> dict[str, object]:
    entries = []
    for source in SOURCES.values():
        path = root / source["relative_path"]
        entry = dict(source)
        entry.update(
            {
                "retrieval_timestamp": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
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
            "created_timestamp": datetime.fromtimestamp(overlay_path.stat().st_mtime, UTC).isoformat(),
            "size_bytes": overlay_path.stat().st_size,
            "physical_sha256": sha256(overlay_path),
            "observed_logical_sha256": logical_geoframe_hash(overlay, ["target_precinct_geoid", "senate_district"]),
        }
    )
    return {"manifest_version": "1.0.0", "sources": entries, "derived_inputs": [overlay_entry]}


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
    direct = qa["direct_diagnostics"]
    relationship = qa["relationship_diagnostics"]
    return f"""# POC011 statewide 2010 population proof

Status: **{'PASS' if qa['passed'] else 'FAIL'}**

- 2010 Census source blocks: {EXPECTED['source_blocks']:,}
- Fixed 2021 LRC precincts: {EXPECTED['fixed_precincts']:,}
- 2001 Final Senate districts: {EXPECTED['senate_districts']:,}
- Pennsylvania 2010 population: {EXPECTED['population']:,}
- Direct atomic-area source exceptions: {direct['uncovered_source_blocks']:,}
- Relationship-file source exceptions: {relationship['missing_source_blocks_before_exceptions']:,}
- Precinct total absolute method delta: {comparison['precinct_total_absolute_delta']:,.3f}
- Senate total absolute method delta: {comparison['senate_total_absolute_delta']:,.3f}
- Nearest-boundary assignments: 0

The direct route intersects 2010 blocks with the atomic fixed-precinct/2001
Senate geometry in EPSG:5070. The independent relationship-assisted route
composes official 2010-to-2020 land-plus-water intersection fractions with a
geometry-only 2020 corrected-fragment-to-atomic-target crosswalk. Neither route
uses 2020 population as a historical weight.

Both routes normalize over covered area, conserve all 12,702,379 people at the
state and source-county levels, support all fixed precincts and Senate districts,
and retain fractional estimates. Uncovered source exceptions are permitted only
for verified zero-population blocks. The method difference is uncertainty
evidence, not a claim that either equal-area route reproduces 2010 population
locations inside blocks.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC011 {'passed' if qa['passed'] else 'failed'}")


if __name__ == "__main__":
    main()
