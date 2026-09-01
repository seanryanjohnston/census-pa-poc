from __future__ import annotations

import csv
from zipfile import ZipFile

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from census_pa_poc.sources import load_acs5_2015_block_group_population
from census_pa_poc.statewide_acs5_2015 import (
    SIMPLE_METHOD,
    aggregate_results,
    build_population_informed_crosswalk,
    build_simple_area_crosswalk,
)


def test_summary_file_loader_joins_block_group_estimate_and_moe(tmp_path) -> None:
    geography = tmp_path / "g20155pa.csv"
    row = [""] * 53
    row[2] = "150"
    row[4] = "0000001"
    row[9] = "42"
    row[10] = "001"
    row[13] = "000100"
    row[14] = "1"
    row[49] = "Block Group 1"
    with geography.open("w", newline="", encoding="latin1") as target:
        csv.writer(target).writerow(row)

    sequence = tmp_path / "sequence.zip"
    estimate = [""] * 130
    estimate[5] = "0000001"
    estimate[129] = "123"
    margin = [""] * 130
    margin[5] = "0000001"
    margin[129] = "17"
    with ZipFile(sequence, "w") as archive:
        archive.writestr("e20155pa0003000.txt", _csv_line(estimate))
        archive.writestr("m20155pa0003000.txt", _csv_line(margin))

    result = load_acs5_2015_block_group_population(geography, sequence)

    assert result.to_dict("records") == [
        {
            "LOGRECNO": "0000001",
            "source_block_group_geoid": "420010001001",
            "NAME": "Block Group 1",
            "B01003_001E": 123,
            "B01003_001M": 17,
        }
    ]


def test_simple_area_crosswalk_normalizes_atomic_intersections() -> None:
    sources = gpd.GeoDataFrame(
        {"GEOID": ["420010001001"]},
        geometry=[box(0, 0, 2, 1)],
        crs="EPSG:5070",
    )
    atoms = gpd.GeoDataFrame(
        {
            "target_precinct_geoid": ["p1", "p2"],
            "senate_district": [1, 2],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:5070",
    )

    result, diagnostics = build_simple_area_crosswalk(sources, atoms)

    assert result["weight"].tolist() == pytest.approx([0.5, 0.5])
    assert result["method_id"].unique().tolist() == [SIMPLE_METHOD]
    assert diagnostics["assigned_source_block_groups"] == 1
    assert diagnostics["nearest_assignment_count"] == 0


def test_population_informed_crosswalk_uses_zero_support_area_fallback() -> None:
    population = pd.DataFrame(
        {
            "source_block_group_geoid": ["bg1", "bg2"],
            "B01003_001E": [100, 50],
            "B01003_001M": [10, 8],
        }
    )
    block_support = pd.DataFrame(
        {
            "source_block_group_geoid": ["bg1", "bg1", "bg2"],
            "target_precinct_geoid": ["p1", "p2", "p1"],
            "senate_district": [1, 2, 1],
            "support_population": [75.0, 25.0, 0.0],
        }
    )
    simple = pd.DataFrame(
        {
            "source_block_group_geoid": ["bg1", "bg1", "bg2", "bg2"],
            "target_precinct_geoid": ["p1", "p2", "p1", "p2"],
            "senate_district": [1, 2, 1, 2],
            "raw_support_value": [1.0, 1.0, 1.0, 4.0],
            "weight": [0.5, 0.5, 0.2, 0.8],
        }
    )

    result, diagnostics = build_population_informed_crosswalk(
        population, block_support, simple
    )

    weights = result.groupby("source_block_group_geoid")["weight"].apply(list)
    assert weights["bg1"] == pytest.approx([0.75, 0.25])
    assert weights["bg2"] == pytest.approx([0.2, 0.8])
    assert set(
        result.loc[result["source_block_group_geoid"].eq("bg2"), "fallback_basis"]
    ) == {"simple_area_zero_2010_population"}
    assert diagnostics["zero_2010_support_ids"] == ["bg2"]
    assert diagnostics["fallback_acs_estimate"] == 50


def test_aggregate_results_keeps_estimate_and_rss_moe_paths_separate() -> None:
    population = pd.DataFrame(
        {
            "source_block_group_geoid": ["bg1", "bg2"],
            "B01003_001E": [100, 50],
            "B01003_001M": [10, 8],
        }
    )
    crosswalk = pd.DataFrame(
        {
            "method_id": [SIMPLE_METHOD, SIMPLE_METHOD, SIMPLE_METHOD],
            "source_block_group_geoid": ["bg1", "bg1", "bg2"],
            "target_precinct_geoid": ["p1", "p2", "p1"],
            "senate_district": [1, 2, 1],
            "weight": [0.25, 0.75, 1.0],
        }
    )

    precinct, senate = aggregate_results(population, crosswalk)

    p1 = precinct.set_index("target_precinct_geoid").loc["p1"]
    assert p1["estimate"] == pytest.approx(75.0)
    assert p1["margin_of_error"] == pytest.approx((2.5**2 + 8.0**2) ** 0.5)
    assert precinct["estimate"].sum() == pytest.approx(150.0)
    assert senate["estimate"].sum() == pytest.approx(150.0)


def _csv_line(row: list[str]) -> str:
    from io import StringIO

    target = StringIO()
    csv.writer(target, lineterminator="\n").writerow(row)
    return target.getvalue()
