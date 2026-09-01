from __future__ import annotations

import csv
from io import StringIO
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import pytest

from census_pa_poc.sources import (
    load_2000_2010_block_relationship,
    load_2000_pl94_block_population,
)
from census_pa_poc.statewide_2000 import build_relationship_atomic_crosswalk


def test_load_2000_pl94_block_population_joins_separate_archives(tmp_path) -> None:
    geography_path = tmp_path / "pageo.upl.zip"
    file01_path = tmp_path / "pa00001.upl.zip"
    geography = _geography_line("0000123", "001", "000100", "1001")
    file01 = ["uPL", "PA", "000", "01", "0000123", "17"]
    with ZipFile(geography_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("pageo.upl", geography + "\n")
    with ZipFile(file01_path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("pa00001.upl", _csv_line(file01))

    result = load_2000_pl94_block_population(geography_path, file01_path)

    assert result.to_dict("records") == [
        {"source_block_geoid": "420010001001001", "P0010001": 17}
    ]


def test_load_2000_2010_relationship_strips_fixed_width_padding(tmp_path) -> None:
    path = tmp_path / "relationship.zip"
    header = (
        "STATE_2000,COUNTY_2000,TRACT_2000,BLK_2000,BLKSF_2000,"
        "AREALAND_2000,AREAWATER_2000,BLOCK_PART_FLAG_O,STATE_2010,"
        "COUNTY_2010,TRACT_2010,BLK_2010,BLKSF_2010,AREALAND_2010,"
        "AREAWATER_2010,BLOCK_PART_FLAG_R,AREALAND_INT,AREAWATER_INT   \n"
    )
    row = "42,001,000100,1001,,100,0,,42,001,000100,1002,,100,0,,100,0   \n"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("TAB2000_TAB2010_ST_42_v2.txt", header + row)

    result = load_2000_2010_block_relationship(path)

    assert result["source_block_geoid"].tolist() == ["420010001001001"]
    assert result["target_2010_block_geoid"].tolist() == ["420010001001002"]
    assert result["AREALAND_INT"].tolist() == [100]


def test_relationship_route_types_immaterial_missing_atomic_component() -> None:
    relationship = pd.DataFrame(
        {
            "source_block_geoid": ["420010001001001", "420010001001001"],
            "target_2010_block_geoid": [
                "420010001001001",
                "420010001001002",
            ],
            "AREALAND_2000": [1_000_000, 1_000_000],
            "AREAWATER_2000": [0, 0],
            "AREALAND_INT": [999_680, 320],
            "AREAWATER_INT": [0, 0],
        }
    )
    target = pd.DataFrame(
        {
            "target_2010_block_geoid": ["420010001001001"],
            "target_precinct_geoid": ["42001000001"],
            "senate_district": [1],
            "target_atomic_weight": [1.0],
        }
    )
    population = pd.DataFrame(
        {"source_block_geoid": ["420010001001001"], "P0010001": [7]}
    )

    crosswalk, diagnostics = build_relationship_atomic_crosswalk(
        relationship, target, population
    )

    assert crosswalk["weight"].tolist() == [1.0]
    assert diagnostics["missing_target_atomic_rows"] == 1
    assert diagnostics["missing_target_atomic_populated_source_blocks"] == 1
    assert diagnostics[
        "missing_target_atomic_equal_area_implied_population"
    ] == pytest.approx(0.00224)


def _geography_line(logrecno: str, county: str, tract: str, block: str) -> str:
    chars = [" "] * 500
    chars[0:6] = "uPL   "
    chars[6:8] = "PA"
    chars[8:11] = "750"
    chars[18:25] = logrecno
    chars[29:31] = "42"
    chars[31:34] = county
    chars[55:61] = tract
    chars[62:66] = block
    return "".join(chars)


def _csv_line(values: list[str]) -> str:
    target = StringIO()
    csv.writer(target, lineterminator="\n").writerow(values)
    return target.getvalue()
