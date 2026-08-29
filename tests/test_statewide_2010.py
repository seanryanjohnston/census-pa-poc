from __future__ import annotations

import csv
from zipfile import ZIP_DEFLATED, ZipFile

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from census_pa_poc.sources import (
    load_2010_2020_block_relationship,
    load_2010_pl94_block_population,
)
from census_pa_poc.statewide_2010 import (
    add_zero_population_exceptions,
    aggregate_results,
    build_2020_atomic_crosswalk,
    build_direct_atomic_crosswalk,
    build_relationship_atomic_crosswalk,
    normalize_crosswalk_dtypes,
)
from census_pa_poc.validation import logical_frame_hash


def test_load_2010_pl94_block_population_parses_fixed_width_geography(
    tmp_path,
) -> None:
    path = tmp_path / "pa2010.pl.zip"
    geography = _geography_line("0000123", "001", "000100", "1001")
    file01 = ["PLST", "PA", "000", "01", "0000123", "17"]
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("pageo2010.pl", geography + "\n")
        archive.writestr("pa000012010.pl", _csv_line(file01))

    result = load_2010_pl94_block_population(path)

    assert result.to_dict("records") == [
        {"source_block_geoid": "420010001001001", "P0010001": 17}
    ]


def test_load_relationship_filters_incoming_cross_state_rows(tmp_path) -> None:
    path = tmp_path / "relationship.zip"
    header = (
        "STATE_2010|COUNTY_2010|TRACT_2010|BLK_2010|BLKSF_2010|"
        "AREALAND_2010|AREAWATER_2010|BLOCK_PART_FLAG_O|STATE_2020|"
        "COUNTY_2020|TRACT_2020|BLK_2020|BLKSF_2020|AREALAND_2020|"
        "AREAWATER_2020|BLOCK_PART_FLAG_R|AREALAND_INT|AREAWATER_INT\n"
    )
    pa = "42|001|000100|1001||100|0||42|001|000100|1001||100|0||100|0\n"
    incoming = "34|041|031101|1041||0|100|p|42|089|300501|4006||0|100|p|0|100\n"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("tab2010_tab2020_st42_pa.txt", header + pa + incoming)

    result = load_2010_2020_block_relationship(path)

    assert result["source_block_geoid"].tolist() == ["420010001001001"]
    assert result["target_2020_block_geoid"].tolist() == ["420010001001001"]
    assert result["AREALAND_INT"].tolist() == [100]


def test_direct_and_relationship_routes_build_atomic_weights() -> None:
    source = gpd.GeoDataFrame(
        {"GEOID10": ["420010001001001"]},
        geometry=[box(0, 0, 2, 1)],
        crs="EPSG:5070",
    )
    atoms = gpd.GeoDataFrame(
        {
            "target_precinct_geoid": ["42001000001", "42001000002"],
            "senate_district": [1, 2],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:5070",
    )
    lrc = gpd.GeoDataFrame(
        {"GEOID20": ["420010001001001"]},
        geometry=[box(0, 0, 2, 1)],
        crs="EPSG:5070",
    )
    relationship = pd.DataFrame(
        {
            "source_block_geoid": ["420010001001001"],
            "target_2020_block_geoid": ["420010001001001"],
            "AREALAND_2010": [2],
            "AREAWATER_2010": [0],
            "AREALAND_INT": [2],
            "AREAWATER_INT": [0],
        }
    )

    direct, _ = build_direct_atomic_crosswalk(source, atoms)
    target_2020, _ = build_2020_atomic_crosswalk(lrc, atoms)
    related, _ = build_relationship_atomic_crosswalk(
        relationship, target_2020, {"420010001001001"}
    )

    assert direct["weight"].tolist() == [0.5, 0.5]
    assert related["weight"].tolist() == [0.5, 0.5]
    assert direct["senate_district"].tolist() == [1, 2]
    assert related["target_precinct_geoid"].tolist() == [
        "42001000001",
        "42001000002",
    ]


def test_zero_population_exception_and_aggregation() -> None:
    crosswalk = pd.DataFrame(
        {
            "source_block_geoid": ["420010001001001"],
            "target_precinct_geoid": ["42001000001"],
            "senate_district": [1],
            "weight": [1.0],
            "method_id": ["direct_atomic_area_2010_v1"],
            "weighting_universe": ["area"],
            "assignment_status": ["assigned"],
            "nearest_assignment_used": [False],
        }
    )
    population = pd.DataFrame(
        {
            "source_block_geoid": ["420010001001001", "420010001001002"],
            "P0010001": [10, 0],
        }
    )

    complete = add_zero_population_exceptions(crosswalk, population)
    precinct, senate = aggregate_results(population, complete)

    assert complete["assignment_status"].tolist() == [
        "assigned",
        "zero_population_uncovered_exception",
    ]
    assert precinct["population"].tolist() == [10.0]
    assert senate["population"].tolist() == [10.0]


def test_nullable_crosswalk_hash_survives_parquet_round_trip(tmp_path) -> None:
    frame = pd.DataFrame(
        {
            "source_block_geoid": ["420010001001001"],
            "target_precinct_geoid": [pd.NA],
            "senate_district": [pd.NA],
            "intersection_area_square_meters": [pd.NA],
            "weight": [0.0],
            "raw_composed_weight": [pd.NA],
            "source_dataset_id": ["source"],
            "source_reference_vintage": ["2010"],
            "target_precinct_dataset_id": ["precinct"],
            "target_precinct_effective_vintage": ["2021"],
            "target_senate_plan_id": ["senate"],
            "target_senate_plan_reference_vintage": ["2001"],
            "method_id": ["method"],
            "method_version": ["1.0.0"],
            "weighting_universe": ["area"],
            "assignment_status": ["zero_population_uncovered_exception"],
            "nearest_assignment_used": [False],
        }
    )
    normalized = normalize_crosswalk_dtypes(frame)
    path = tmp_path / "crosswalk.parquet"
    normalized.to_parquet(path, index=False)
    keys = [
        "method_id",
        "source_block_geoid",
        "target_precinct_geoid",
        "senate_district",
    ]

    assert logical_frame_hash(normalized, keys) == logical_frame_hash(
        pd.read_parquet(path), keys
    )


def _geography_line(
    logrecno: str, county: str, tract: str, block: str
) -> str:
    chars = [" "] * 500
    chars[0:6] = "PLST  "
    chars[6:8] = "PA"
    chars[8:11] = "750"
    chars[18:25] = logrecno
    chars[27:29] = "42"
    chars[29:32] = county
    chars[54:60] = tract
    chars[61:65] = block
    return "".join(chars)


def _csv_line(values: list[str]) -> str:
    from io import StringIO

    target = StringIO()
    csv.writer(target, lineterminator="\n").writerow(values)
    return target.getvalue()
