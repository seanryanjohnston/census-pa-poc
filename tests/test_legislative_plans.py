from __future__ import annotations

import geopandas as gpd
from shapely.geometry import Polygon, box

from census_pa_poc.legislative_plans import normalize_plan, profile_checks
from census_pa_poc.validation import all_pass


def test_normalize_plan_assigns_recorded_crs_repairs_and_dissolves() -> None:
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    raw = gpd.GeoDataFrame(
        {"DIST": [1, 1, 2]},
        geometry=[bowtie, box(2, 0, 3, 1), box(3, 0, 4, 1)],
    )
    source = {
        "district_field": "DIST",
        "published_crs": "EPSG:4269",
        "target_chamber": "house",
        "target_plan_id": "fixture",
        "reference_vintage": "2001",
        "first_election": "2002",
        "last_election": "2012",
        "source_url": "https://example.invalid/fixture.zip",
    }

    normalized, detail = normalize_plan(raw, source)

    assert detail == {
        "source_crs_missing": True,
        "invalid_geometry_count_before_repair": 1,
        "raw_row_count": 3,
        "duplicate_district_part_rows": 1,
    }
    assert normalized.crs.to_string() == "EPSG:4269"
    assert normalized["target_district_id"].tolist() == [1, 2]
    assert normalized.geometry.is_valid.all()


def test_profile_checks_accept_complete_normalized_plan() -> None:
    profile = {
        "target_plan_id": "fixture",
        "expected_district_count": 2,
        "normalized_row_count": 2,
        "district_count": 2,
        "district_ids": [1, 2],
        "raw_crs": None,
        "normalized_crs": "EPSG:4269",
        "source_crs_missing": True,
        "null_or_empty_geometry_count": 0,
        "invalid_geometry_count_before_repair": 1,
        "invalid_geometry_count_after_repair": 0,
    }

    assert all_pass(profile_checks(profile))
