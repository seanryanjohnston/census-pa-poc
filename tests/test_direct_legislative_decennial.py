from __future__ import annotations

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from census_pa_poc.direct_legislative_decennial import (
    apply_atomic_overrides,
    build_atomic_area_weights,
    require_supporting_hashes,
)


def test_source_local_overlap_goes_to_dominant_district() -> None:
    source = gpd.GeoDataFrame(
        {"GEOID10": ["a"]},
        geometry=[box(0, 0, 2_000, 1_000)],
        crs="EPSG:5070",
    )
    plan = gpd.GeoDataFrame(
        {"target_district_id": [1, 2]},
        geometry=[box(0, 0, 1_200, 1_000), box(800, 0, 2_000, 1_000)],
        crs="EPSG:5070",
    )

    crosswalk, diagnostics = build_atomic_area_weights(source, plan, "GEOID10")

    observed = crosswalk.set_index("target_district_id")[
        "target_atomic_weight"
    ].to_dict()
    assert observed == {1: 0.6, 2: 0.4}
    assert diagnostics["overlap_removed_square_meters"] == 400_000
    assert diagnostics["nearest_assignment_count"] == 0


def test_single_intersecting_district_absorbs_boundary_gap() -> None:
    source = gpd.GeoDataFrame(
        {"GEOID10": ["a"]}, geometry=[box(0, 0, 2, 1)], crs="EPSG:5070"
    )
    plan = gpd.GeoDataFrame(
        {"target_district_id": [1]},
        geometry=[box(0, 0, 1.5, 1)],
        crs="EPSG:5070",
    )

    crosswalk, _ = build_atomic_area_weights(source, plan, "GEOID10")

    assert crosswalk["target_atomic_weight"].tolist() == [1.0]
    assert crosswalk["normalization_status"].tolist() == [
        "single_intersecting_district"
    ]


def test_legal_override_is_explicit_and_not_nearest() -> None:
    empty = pd.DataFrame(
        columns=[
            "source_atomic_geoid",
            "target_district_id",
            "target_atomic_area_square_meters",
            "target_atomic_weight",
            "normalization_status",
            "overlap_removed_square_meters",
        ]
    )
    diagnostics = {"uncovered_atomic_geographies": 1}

    result, detail = apply_atomic_overrides(
        empty, diagnostics, "2000", "pa_house_1991_final"
    )

    assert result["source_atomic_geoid"].tolist() == ["420490117011001"]
    assert result["target_district_id"].tolist() == [4]
    assert detail["legal_assignment_override_count"] == 1
    assert detail["legal_assignment_overrides"][0]["nearest_assignment_used"] is False


def test_legal_override_sources_must_match_frozen_hashes() -> None:
    manifest = {
        "supporting_override_sources": [
            {
                "source_id": "legal_description",
                "sha256": "expected",
                "observed_sha256": "different",
            }
        ]
    }

    with pytest.raises(RuntimeError, match="legal_description"):
        require_supporting_hashes(manifest)
