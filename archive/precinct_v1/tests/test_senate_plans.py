from __future__ import annotations

import csv

import geopandas as gpd
from shapely.geometry import Polygon, box

from census_pa_poc.senate_plans import (
    repair_plan_geometry,
    source_profile_checks,
    validate_cycle_mapping,
)
from census_pa_poc.validation import all_pass


def test_repair_plan_geometry_records_and_repairs_self_intersection() -> None:
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    plan = gpd.GeoDataFrame(
        {"senate_district": [1]}, geometry=[bowtie], crs="EPSG:4269"
    )

    repaired, invalid_before = repair_plan_geometry(plan)

    assert invalid_before == 1
    assert repaired.geometry.is_valid.all()


def test_source_profile_checks_accept_complete_repaired_plan() -> None:
    profile = {
        "source_id": "plan",
        "row_count": 50,
        "district_count": 50,
        "district_ids": list(range(1, 51)),
        "crs": "EPSG:4269",
        "null_or_empty_geometry_count": 0,
        "invalid_geometry_count_before_repair": 1,
        "invalid_geometry_count_after_repair": 0,
    }

    assert all_pass(source_profile_checks(profile))


def test_cycle_mapping_rejects_unknown_plan(tmp_path) -> None:
    mapping_dir = tmp_path / "mappings"
    mapping_dir.mkdir()
    with (mapping_dir / "election_cycles.csv").open("w", newline="") as target:
        writer = csv.DictWriter(
            target, fieldnames=["election_id", "senate_plan_id"]
        )
        writer.writeheader()
        writer.writerow({"election_id": "e1", "senate_plan_id": "unknown"})

    checks = validate_cycle_mapping(tmp_path, {"known"})
    failures = {check["check_id"] for check in checks if not check["passed"]}

    assert "cycle_count" in failures
    assert "all_cycle_plan_ids_known" in failures


def test_fixture_geometry_is_available_for_future_overlay_tests() -> None:
    plan = gpd.GeoDataFrame(
        {"senate_district": [1, 2]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:4269",
    )

    assert plan.geometry.is_valid.all()
