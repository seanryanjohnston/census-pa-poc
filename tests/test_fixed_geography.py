from __future__ import annotations

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from census_pa_poc.fixed_geography import (
    audit_assignment_geometry,
    build_assignment_inventory,
    build_checks,
)
from census_pa_poc.validation import all_pass


def _fixture():
    census = pd.DataFrame(
        {"GEOID20": ["420010001001001", "420010001001002"]}
    )
    blocks = gpd.GeoDataFrame(
        {
            "FIPS": ["001", "001", "001"],
            "VTD": ["000001", "000002", "000002"],
            "P0010001": [3, 7, 11],
            "STATEFP20": ["42", "42", "42"],
            "COUNTYFP20": ["001", "001", "001"],
            "VTDST20": ["000001", "000002", "000002"],
            "GEOID20": [
                "420010001001001A",
                "420010001001001B",
                "420010001001002",
            ],
            "VTD_NAME": ["One", "Two", "Two"],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(1, 1, 2, 2)],
        crs="EPSG:4269",
    )
    precincts = gpd.GeoDataFrame(
        {
            "GEOID20": ["42001000001", "42001000002"],
            "P0010001": [3, 18],
            "STATEFP20": ["42", "42"],
            "COUNTYFP20": ["001", "001"],
            "VTDST20": ["000001", "000002"],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 2)],
        crs="EPSG:4269",
    )
    return census, blocks, precincts


def test_inventory_preserves_split_parent_fragments() -> None:
    _, blocks, _ = _fixture()

    result = build_assignment_inventory(blocks)

    split = result[result["is_split_parent"]]
    assert len(result) == 3
    assert split["source_parent_block_geoid"].nunique() == 1
    assert set(split["target_precinct_geoid"]) == {
        "42001000001",
        "42001000002",
    }
    assert result["weight"].eq(1.0).all()
    assert not result["nearest_assignment_used"].any()


def test_complete_fixture_passes_coverage_and_geometry_checks() -> None:
    census, blocks, precincts = _fixture()
    assignments = build_assignment_inventory(blocks)
    geometry, precision = audit_assignment_geometry(blocks, precincts, assignments)
    expected = {
        "census_parent_blocks": 2,
        "lrc_fragments": 3,
        "lrc_parent_blocks": 2,
        "precincts": 2,
        "split_parent_blocks": 1,
        "split_fragments": 2,
        "two_target_parents": 1,
        "three_target_parents": 0,
    }

    checks = build_checks(
        census, blocks, precincts, assignments, geometry, expected=expected
    )

    assert all_pass(checks)
    assert precision.empty
    assert geometry["representative_point_exceptions"] == 0


def test_missing_target_polygon_fails_without_nearest_assignment() -> None:
    census, blocks, precincts = _fixture()
    assignments = build_assignment_inventory(blocks)
    incomplete = precincts.iloc[[0]].copy()
    geometry, _ = audit_assignment_geometry(blocks, incomplete, assignments)
    expected = {
        "census_parent_blocks": 2,
        "lrc_fragments": 3,
        "lrc_parent_blocks": 2,
        "precincts": 1,
        "split_parent_blocks": 1,
        "split_fragments": 2,
        "two_target_parents": 1,
        "three_target_parents": 0,
    }

    checks = build_checks(
        census, blocks, incomplete, assignments, geometry, expected=expected
    )

    failures = {check["check_id"] for check in checks if not check["passed"]}
    assert "exact_target_key_match" in failures
    assert "all_assigned_targets_present" in failures
    assert not assignments["nearest_assignment_used"].any()
