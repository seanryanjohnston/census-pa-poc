"""Transparent direct and representative-point crosswalk builders."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import make_valid

SOURCE_DATASET_ID = "census_2020_pa_blocks"
SOURCE_REFERENCE_VINTAGE = "2020"
TARGET_DATASET_ID = "pa_lrc_2021_release_1b_geography"
TARGET_EFFECTIVE_VINTAGE = "2021-10-05"
WEIGHTING_UNIVERSE = "whole_2020_block_population"
PHILADELPHIA_PROJECTED_CRS = "EPSG:2272"
AREA_SLIVER_TOLERANCE = 5e-6


def canonical_lrc_source_block_id(value: str) -> str:
    """Map an LRC corrected A/B/C fragment ID back to its Census block ID."""
    if len(value) == 16 and value[-1] in {"A", "B", "C"}:
        return value[:-1]
    return value


def profile_direct_fields(lrc_blocks: gpd.GeoDataFrame) -> dict[str, object]:
    """Measure whether LRC block rows encode one complete precinct assignment."""
    fields = ["STATEFP20", "COUNTYFP20", "VTD", "VTDST20", "GEOID20"]
    null_counts = {field: int(lrc_blocks[field].isna().sum()) for field in fields}
    direct_key = (
        lrc_blocks["STATEFP20"] + lrc_blocks["COUNTYFP20"] + lrc_blocks["VTDST20"]
    )
    source_ids = lrc_blocks["GEOID20"].map(canonical_lrc_source_block_id)
    source_target = pd.DataFrame({"source": source_ids, "target": direct_key}).dropna()
    target_counts = source_target.groupby("source")["target"].nunique()
    return {
        "row_count": len(lrc_blocks),
        "unique_source_blocks": int(source_ids.nunique(dropna=True)),
        "unique_target_precincts": int(direct_key.nunique(dropna=True)),
        "null_counts": null_counts,
        "duplicate_source_rows": int(source_ids.duplicated().sum()),
        "synthetic_fragment_rows": int(lrc_blocks["GEOID20"].str.len().eq(16).sum()),
        "vtd_field_disagreements": int(
            (lrc_blocks["VTD"] != lrc_blocks["VTDST20"]).sum()
        ),
        "split_source_blocks": int((target_counts > 1).sum()),
        "usable_one_target_rows": int(lrc_blocks[fields].notna().all(axis=1).sum()),
    }


def build_lrc_published_crosswalk(
    source_blocks: gpd.GeoDataFrame,
    lrc_blocks: gpd.GeoDataFrame,
    projected_crs: str = PHILADELPHIA_PROJECTED_CRS,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build the LRC published assignment, preserving corrected block splits.

    LRC represents a corrected split with two synthetic block IDs ending in
    ``A`` and ``B``. Positive-population fragments use the published fragment
    counts as weights. A zero-population parent has no population distribution
    to infer, so its rows receive fragment-area weights solely to keep the
    crosswalk total and valid.
    """
    fragments = lrc_blocks[
        ["GEOID20", "STATEFP20", "COUNTYFP20", "VTDST20", "P0010001", "geometry"]
    ].copy()
    fragments["source_block_geoid"] = fragments["GEOID20"].map(
        canonical_lrc_source_block_id
    )
    fragments["target_precinct_geoid"] = (
        fragments["STATEFP20"] + fragments["COUNTYFP20"] + fragments["VTDST20"]
    )
    fragments["fragment_area"] = fragments.to_crs(projected_crs).geometry.area
    grouped = fragments.groupby("source_block_geoid")
    fragments["source_population"] = grouped["P0010001"].transform("sum")
    fragments["source_fragment_area"] = grouped["fragment_area"].transform("sum")
    fragments["weight"] = fragments["P0010001"] / fragments["source_population"]
    zero_population = fragments["source_population"].eq(0)
    fragments.loc[zero_population, "weight"] = (
        fragments.loc[zero_population, "fragment_area"]
        / fragments.loc[zero_population, "source_fragment_area"]
    )
    fragments["weight_basis"] = np.where(
        zero_population,
        "corrected_fragment_area_zero_population",
        "published_corrected_fragment_population",
    )
    fragments["candidate_count"] = grouped["target_precinct_geoid"].transform("nunique")
    fragments["assignment_status"] = "assigned"
    fragments["tie_break_rule"] = "not_applicable"
    fragments["match_basis"] = np.where(
        fragments["candidate_count"].gt(1),
        "lrc_corrected_split_fragment",
        "lrc_published_precinct_key",
    )
    fragments = fragments.assign(
        **_crosswalk_metadata(
            "lrc_published_split_v1",
            "1.0.0",
            "published_lrc_corrected_fragment_population",
        )
    )

    source_ids = set(source_blocks["GEOID20"])
    published_ids = set(fragments["source_block_geoid"])
    if source_ids != published_ids:
        raise ValueError(
            "Published LRC source coverage differs from Census blocks: "
            f"missing={len(source_ids - published_ids)}, "
            f"unexpected={len(published_ids - source_ids)}"
        )

    split_sources = grouped.size().gt(1)
    diagnostics = {
        "allocation_rows": len(fragments),
        "source_blocks": len(source_ids),
        "synthetic_fragment_rows": int(lrc_blocks["GEOID20"].str.len().eq(16).sum()),
        "split_source_blocks": int(split_sources.sum()),
        "zero_population_split_blocks": int(
            fragments.loc[fragments["candidate_count"].gt(1)]
            .groupby("source_block_geoid")["source_population"]
            .first()
            .eq(0)
            .sum()
        ),
        "projected_crs": projected_crs,
    }
    return _sort_crosswalk(fragments), diagnostics


def build_area_overlay_crosswalk(
    source_blocks: gpd.GeoDataFrame,
    targets: gpd.GeoDataFrame,
    projected_crs: str = PHILADELPHIA_PROJECTED_CRS,
    sliver_tolerance: float = AREA_SLIVER_TOLERANCE,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Allocate blocks by polygon-intersection area with a declared sliver rule."""
    clean_sources, source_diagnostics = repair_polygon_geometries(source_blocks)
    clean_targets, target_diagnostics = repair_polygon_geometries(targets)
    sources = clean_sources[["GEOID20", "geometry"]].to_crs(projected_crs)
    sources = sources.rename(columns={"GEOID20": "source_block_geoid"})
    target_frame = clean_targets[["GEOID20", "geometry"]].to_crs(projected_crs)
    target_frame = target_frame.rename(columns={"GEOID20": "target_precinct_geoid"})
    source_area = sources.set_index("source_block_geoid").geometry.area

    intersections = gpd.overlay(
        sources,
        target_frame,
        how="intersection",
        keep_geom_type=False,
    )
    intersections["intersection_area"] = intersections.geometry.area
    intersections["source_area"] = intersections["source_block_geoid"].map(source_area)
    intersections["raw_area_weight"] = (
        intersections["intersection_area"] / intersections["source_area"]
    )
    positive = intersections["raw_area_weight"].gt(0)
    retained = intersections["raw_area_weight"].gt(sliver_tolerance)
    dropped = intersections[positive & ~retained]
    allocations = intersections[retained].copy()
    allocation_area = allocations.groupby("source_block_geoid")[
        "intersection_area"
    ].transform("sum")
    allocations["weight"] = allocations["intersection_area"] / allocation_area
    allocations["coverage_ratio"] = allocations.groupby("source_block_geoid")[
        "raw_area_weight"
    ].transform("sum")
    allocations["candidate_count"] = allocations.groupby("source_block_geoid")[
        "target_precinct_geoid"
    ].transform("nunique")
    allocations["assignment_status"] = "assigned"
    allocations["tie_break_rule"] = "not_applicable"
    allocations["match_basis"] = "positive_area_intersection"
    allocations["weight_basis"] = "normalized_equal_area_intersection"
    allocations = allocations.assign(
        **_crosswalk_metadata(
            "area_overlay_v1",
            "1.0.0",
            "2020_block_equal_area_geometry",
        )
    )

    allocated_source_ids = set(allocations["source_block_geoid"])
    source_ids = set(sources["source_block_geoid"])
    if allocated_source_ids != source_ids:
        raise ValueError(
            "Area overlay did not cover every source block: "
            f"missing={len(source_ids - allocated_source_ids)}"
        )

    source_target_counts = allocations.groupby("source_block_geoid")[
        "target_precinct_geoid"
    ].nunique()
    coverage = allocations.groupby("source_block_geoid")["raw_area_weight"].sum()
    diagnostics = {
        "allocation_rows": len(allocations),
        "source_blocks": len(source_ids),
        "split_source_blocks": int(source_target_counts.gt(1).sum()),
        "sliver_tolerance_source_area_share": sliver_tolerance,
        "dropped_positive_sliver_rows": len(dropped),
        "maximum_dropped_sliver_share": (
            float(dropped["raw_area_weight"].max()) if len(dropped) else 0.0
        ),
        "minimum_retained_coverage_ratio": float(coverage.min()),
        "maximum_retained_coverage_ratio": float(coverage.max()),
        "projected_crs": projected_crs,
        "source_geometry": source_diagnostics,
        "target_geometry": target_diagnostics,
    }
    return _sort_crosswalk(allocations), diagnostics


def _crosswalk_metadata(
    method_id: str,
    method_version: str,
    weighting_universe: str = WEIGHTING_UNIVERSE,
) -> dict[str, object]:
    return {
        "source_dataset_id": SOURCE_DATASET_ID,
        "source_reference_vintage": SOURCE_REFERENCE_VINTAGE,
        "target_dataset_id": TARGET_DATASET_ID,
        "target_effective_vintage": TARGET_EFFECTIVE_VINTAGE,
        "method_id": method_id,
        "method_version": method_version,
        "weighting_universe": weighting_universe,
    }


def build_direct_crosswalk(
    source_blocks: gpd.GeoDataFrame,
    lrc_blocks: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Build the LRC-published block-to-precinct assignment."""
    assignments = lrc_blocks[["GEOID20", "STATEFP20", "COUNTYFP20", "VTDST20"]].copy()
    assignments["target_precinct_geoid"] = (
        assignments["STATEFP20"] + assignments["COUNTYFP20"] + assignments["VTDST20"]
    )
    assignments = assignments.rename(columns={"GEOID20": "source_block_geoid"})
    source_ids = source_blocks[["GEOID20"]].rename(
        columns={"GEOID20": "source_block_geoid"}
    )
    result = source_ids.merge(
        assignments[["source_block_geoid", "target_precinct_geoid"]],
        on="source_block_geoid",
        how="left",
        validate="one_to_one",
    )
    result = result.assign(
        **_crosswalk_metadata("lrc_direct_v1", "1.0.0"),
        weight=1.0,
        assignment_status=result["target_precinct_geoid"]
        .notna()
        .map({True: "assigned", False: "missing_published_assignment"}),
        candidate_count=result["target_precinct_geoid"].notna().astype("int64"),
        tie_break_rule="not_applicable",
    )
    return _sort_crosswalk(result)


def repair_polygon_geometries(
    frame: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, dict[str, int]]:
    """Repair invalid polygons deterministically and report what changed."""
    result = frame.copy()
    invalid = ~result.geometry.is_valid
    empty_before = result.geometry.is_empty
    result.loc[invalid, "geometry"] = result.loc[invalid, "geometry"].map(make_valid)
    diagnostics = {
        "invalid_before": int(invalid.sum()),
        "empty_before": int(empty_before.sum()),
        "invalid_after": int((~result.geometry.is_valid).sum()),
        "empty_after": int(result.geometry.is_empty.sum()),
    }
    return result, diagnostics


def assign_points_to_targets(
    source_ids: pd.Series,
    points: gpd.GeoSeries,
    targets: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Assign points, preferring strict containment and breaking ties by ID."""
    if points.crs != targets.crs:
        raise ValueError(f"CRS mismatch: source {points.crs}, target {targets.crs}")
    point_frame = gpd.GeoDataFrame(
        {"source_block_geoid": source_ids.astype("string").to_numpy()},
        geometry=points.to_numpy(),
        crs=points.crs,
    )
    target_frame = targets[["GEOID20", "geometry"]].rename(
        columns={"GEOID20": "target_precinct_geoid"}
    )

    within = gpd.sjoin(point_frame, target_frame, predicate="within", how="inner")
    within["match_basis"] = "strict_within"
    matched = set(within["source_block_geoid"])
    unmatched = point_frame[~point_frame["source_block_geoid"].isin(matched)]
    boundary = gpd.sjoin(unmatched, target_frame, predicate="intersects", how="inner")
    boundary["match_basis"] = "boundary_intersects"
    candidates = pd.concat([within, boundary], ignore_index=True)
    candidates = candidates.sort_values(
        ["source_block_geoid", "target_precinct_geoid"], kind="stable"
    )
    candidate_counts = candidates.groupby("source_block_geoid").size()
    chosen = candidates.drop_duplicates("source_block_geoid", keep="first").copy()
    chosen["candidate_count"] = (
        chosen["source_block_geoid"].map(candidate_counts).astype("int64")
    )
    chosen["tie_break_rule"] = (
        chosen["candidate_count"]
        .gt(1)
        .map({True: "lowest_target_precinct_geoid", False: "not_applicable"})
    )

    result = point_frame[["source_block_geoid"]].merge(
        chosen[
            [
                "source_block_geoid",
                "target_precinct_geoid",
                "candidate_count",
                "tie_break_rule",
                "match_basis",
            ]
        ],
        on="source_block_geoid",
        how="left",
        validate="one_to_one",
    )
    result["candidate_count"] = result["candidate_count"].fillna(0).astype("int64")
    result["assignment_status"] = (
        result["target_precinct_geoid"]
        .notna()
        .map({True: "assigned", False: "no_spatial_candidate"})
    )
    result["tie_break_rule"] = result["tie_break_rule"].fillna("not_applicable")
    result["match_basis"] = result["match_basis"].fillna("none")
    return result


def build_representative_point_crosswalk(
    source_blocks: gpd.GeoDataFrame,
    targets: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, dict[str, dict[str, int]]]:
    """Build an independent spatial crosswalk from polygon interior points."""
    clean_sources, source_diagnostics = repair_polygon_geometries(source_blocks)
    clean_targets, target_diagnostics = repair_polygon_geometries(targets)
    points = clean_sources.geometry.representative_point()
    assignments = assign_points_to_targets(
        clean_sources["GEOID20"], points, clean_targets
    )
    assignments = assignments.assign(
        **_crosswalk_metadata("representative_point_v1", "1.0.0"),
        weight=1.0,
    )
    return _sort_crosswalk(assignments), {
        "source_geometry": source_diagnostics,
        "target_geometry": target_diagnostics,
    }


def _sort_crosswalk(frame: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "source_dataset_id",
        "source_reference_vintage",
        "source_block_geoid",
        "target_dataset_id",
        "target_effective_vintage",
        "target_precinct_geoid",
        "weight",
        "method_id",
        "method_version",
        "weighting_universe",
        "assignment_status",
        "candidate_count",
        "tie_break_rule",
    ]
    if "match_basis" in frame:
        columns.append("match_basis")
    for optional in [
        "weight_basis",
        "raw_area_weight",
        "coverage_ratio",
        "intersection_area",
        "source_area",
        "source_population",
        "fragment_area",
    ]:
        if optional in frame:
            columns.append(optional)
    return (
        frame[columns]
        .sort_values(["source_block_geoid", "target_precinct_geoid"], kind="stable")
        .reset_index(drop=True)
    )
