from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import MultiPolygon, Point, Polygon, box

from census_pa_poc.crosswalk import (
    assign_points_to_targets,
    build_area_overlay_crosswalk,
    build_lrc_published_crosswalk,
    build_representative_point_crosswalk,
    canonical_lrc_source_block_id,
    profile_direct_fields,
    repair_polygon_geometries,
)


def _targets(ids, geometries):
    return gpd.GeoDataFrame({"GEOID20": ids}, geometry=geometries, crs="EPSG:4269")


def test_boundary_point_uses_lowest_target_id() -> None:
    targets = _targets(["B", "A"], [box(0, 0, 1, 1), box(1, 0, 2, 1)])
    points = gpd.GeoSeries([Point(1, 0.5)], crs=targets.crs)

    result = assign_points_to_targets(pd.Series(["source"]), points, targets)

    assert result.loc[0, "target_precinct_geoid"] == "A"
    assert result.loc[0, "candidate_count"] == 2
    assert result.loc[0, "tie_break_rule"] == "lowest_target_precinct_geoid"
    assert result.loc[0, "match_basis"] == "boundary_intersects"


def test_multipart_target_and_water_only_source_are_assignable() -> None:
    multipart = MultiPolygon([box(0, 0, 1, 1), box(3, 0, 4, 1)])
    targets = _targets(["multipart"], [multipart])
    sources = gpd.GeoDataFrame(
        {"GEOID20": ["water-only"], "ALAND20": [0], "AWATER20": [1_000]},
        geometry=[box(3.25, 0.25, 3.75, 0.75)],
        crs=targets.crs,
    )

    result, diagnostics = build_representative_point_crosswalk(sources, targets)

    assert result.loc[0, "target_precinct_geoid"] == "multipart"
    assert result.loc[0, "assignment_status"] == "assigned"
    assert diagnostics["source_geometry"]["invalid_before"] == 0


def test_missing_spatial_candidate_is_typed() -> None:
    targets = _targets(["target"], [box(0, 0, 1, 1)])
    points = gpd.GeoSeries([Point(5, 5)], crs=targets.crs)

    result = assign_points_to_targets(pd.Series(["source"]), points, targets)

    assert result.loc[0, "assignment_status"] == "no_spatial_candidate"
    assert result.loc[0, "candidate_count"] == 0


def test_invalid_polygon_is_repaired_and_reported() -> None:
    bow_tie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    frame = _targets(["invalid"], [bow_tie])

    repaired, diagnostics = repair_polygon_geometries(frame)

    assert diagnostics == {
        "invalid_before": 1,
        "empty_before": 0,
        "invalid_after": 0,
        "empty_after": 0,
    }
    assert repaired.geometry.is_valid.all()


def test_direct_profile_reports_duplicate_split_source() -> None:
    frame = gpd.GeoDataFrame(
        {
            "STATEFP20": ["42", "42"],
            "COUNTYFP20": ["041", "041"],
            "VTD": ["000001", "000002"],
            "VTDST20": ["000001", "000002"],
            "GEOID20": ["source", "source"],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:4269",
    )

    profile = profile_direct_fields(frame)

    assert profile["duplicate_source_rows"] == 1
    assert profile["split_source_blocks"] == 1


def test_corrected_fragment_ids_map_to_parent_block() -> None:
    assert canonical_lrc_source_block_id("421010119002007A") == "421010119002007"
    assert canonical_lrc_source_block_id("421010119002007B") == "421010119002007"
    assert canonical_lrc_source_block_id("420912087041000C") == "420912087041000"
    assert canonical_lrc_source_block_id("421010119002008") == "421010119002008"


def test_published_crosswalk_preserves_positive_population_split() -> None:
    sources = gpd.GeoDataFrame(
        {"GEOID20": ["421010119002007"]},
        geometry=[box(0, 0, 2, 1)],
        crs="EPSG:2272",
    )
    fragments = gpd.GeoDataFrame(
        {
            "GEOID20": ["421010119002007A", "421010119002007B"],
            "STATEFP20": ["42", "42"],
            "COUNTYFP20": ["101", "101"],
            "VTDST20": ["005217", "005222"],
            "P0010001": [3, 1],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs=sources.crs,
    )

    result, diagnostics = build_lrc_published_crosswalk(sources, fragments)

    assert result["source_block_geoid"].tolist() == [
        "421010119002007",
        "421010119002007",
    ]
    assert result["weight"].tolist() == [0.75, 0.25]
    assert result["weight_basis"].eq("published_corrected_fragment_population").all()
    assert diagnostics["split_source_blocks"] == 1


def test_area_overlay_allocates_one_source_to_two_targets() -> None:
    sources = gpd.GeoDataFrame(
        {"GEOID20": ["source"]},
        geometry=[box(0, 0, 4, 1)],
        crs="EPSG:2272",
    )
    targets = gpd.GeoDataFrame(
        {"GEOID20": ["left", "right"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 4, 1)],
        crs=sources.crs,
    )

    result, diagnostics = build_area_overlay_crosswalk(sources, targets)

    assert result["target_precinct_geoid"].tolist() == ["left", "right"]
    assert result["weight"].tolist() == [0.25, 0.75]
    assert diagnostics["split_source_blocks"] == 1


def test_crs_mismatch_is_rejected_by_spatial_join() -> None:
    targets = _targets(["target"], [box(0, 0, 1, 1)])
    points = gpd.GeoSeries([Point(0.5, 0.5)], crs="EPSG:3857")

    with pytest.raises(ValueError, match="CRS mismatch"):
        assign_points_to_targets(pd.Series(["source"]), points, targets)
