from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import box

from census_pa_poc.senate_overlay import build_precinct_plan_overlay


def _precinct():
    return gpd.GeoDataFrame(
        {"GEOID20": ["p1"]}, geometry=[box(0, 0, 2, 1)], crs="EPSG:5070"
    )


def test_true_split_is_preserved_and_weights_sum_to_one() -> None:
    plan = gpd.GeoDataFrame(
        {"senate_district": [1, 2]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:5070",
    )

    result, diagnostics = build_precinct_plan_overlay(_precinct(), plan, "plan")

    assert len(result) == 2
    assert result["area_weight"].sum() == pytest.approx(1)
    assert diagnostics["split_precinct_count"] == 1
    assert diagnostics["unresolved_precinct_count"] == 0


def test_overlap_is_removed_from_smaller_precinct_intersection() -> None:
    precinct = gpd.GeoDataFrame(
        {"GEOID20": ["p1"]}, geometry=[box(0, 0, 4, 1)], crs="EPSG:5070"
    )
    plan = gpd.GeoDataFrame(
        {"senate_district": [1, 2]},
        geometry=[box(0, 0, 3, 1), box(1.5, 0, 4, 1)],
        crs="EPSG:5070",
    )

    result, diagnostics = build_precinct_plan_overlay(precinct, plan, "plan")
    district_two = result[result["senate_district"].eq(2)].iloc[0]

    assert district_two["overlap_removed_square_meters"] == pytest.approx(1.5)
    assert result["area_weight"].sum() == pytest.approx(1)
    assert diagnostics["overlap_removed_square_meters"] == pytest.approx(1.5)


def test_single_district_gap_is_filled_without_nearest_assignment() -> None:
    plan = gpd.GeoDataFrame(
        {"senate_district": [1]},
        geometry=[box(0, 0, 1.5, 1)],
        crs="EPSG:5070",
    )

    result, diagnostics = build_precinct_plan_overlay(_precinct(), plan, "plan")

    assert result.iloc[0]["gap_added_square_meters"] == pytest.approx(0.5)
    assert result.iloc[0]["area_weight"] == pytest.approx(1)
    assert diagnostics["nearest_assignment_count"] == 0
