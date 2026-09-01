from __future__ import annotations

from zipfile import ZIP_DEFLATED, ZipFile

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from census_pa_poc.sources import (
    _load_1990_tiger_county_blocks,
    load_1990_2000_block_relationship,
    load_1990_stf1b_block_population,
)
from census_pa_poc.statewide_1990 import (
    build_relationship_atomic_crosswalk,
    build_tiger_face_weights,
)


def test_load_1990_stf1b_block_population_uses_header_pop100(tmp_path) -> None:
    path = tmp_path / "STF1B-PAh.zip"
    line = [" "] * 300
    line[0:8] = "STF1BHP"
    line[10:13] = "100"
    line[46:50] = "303A"
    line[51:57] = "0308  "
    line[71:74] = "001"
    line[132:134] = "42"
    line[171:181] = "0000001250"
    line[181:191] = "0000000250"
    line[259:268] = "000000008"
    line[268:277] = "+39700000"
    line[277:287] = "-077000000"
    line[290:299] = "000000017"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("STF1BHPA.F01", "".join(line) + "\r\n")

    result = load_1990_stf1b_block_population(path)

    assert result.to_dict("records") == [
        {
            "source_block_geoid": "42001030800303A",
            "P0010001": 17,
            "HU100": 8,
            "AREALAND_SQUARE_KILOMETERS": 1.25,
            "AREAWATER_SQUARE_KILOMETERS": 0.25,
            "INTPTLAT90": 39.7,
            "INTPTLON90": -77.0,
        }
    ]


def test_load_1990_2000_relationship_normalizes_legacy_ids(tmp_path) -> None:
    row = "42,001,0308,163,,42,001,030801,1000,p\n"
    for index in range(67):
        (tmp_path / f"t9t242{index:03d}.txt").write_text(row)

    result = load_1990_2000_block_relationship(tmp_path)

    assert len(result) == 67
    assert result["source_block_geoid"].unique().tolist() == ["420010308000163"]
    assert result["target_2000_block_geoid"].unique().tolist() == ["420010308011000"]


def test_load_1990_tiger_county_reconstructs_gt_polygon(tmp_path) -> None:
    path = tmp_path / "tgr42001.zip"
    coordinates = [
        ((-77.0, 39.0), (-76.0, 39.0)),
        ((-76.0, 39.0), (-76.0, 40.0)),
        ((-76.0, 40.0), (-77.0, 40.0)),
        ((-77.0, 40.0), (-77.0, 39.0)),
    ]
    rt1 = "".join(
        _rt1(index + 1, start, end) for index, (start, end) in enumerate(coordinates)
    )
    rti = "".join(_rti(index + 1) for index in range(4))
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("TGR42001.RT1", rt1)
        archive.writestr("TGR42001.RT2", "")
        archive.writestr("TGR42001.RTI", rti)
        archive.writestr("TGR42001.RTA", _rta())
        archive.writestr("TGR42001.RTP", _rtp())
        archive.writestr("TGR42001.RTS", _rts())

    result = _load_1990_tiger_county_blocks(path)

    assert result["source_block_geoid"].tolist() == ["42001030800303A"]
    assert result.geometry.iloc[0].area == pytest.approx(1.0)
    assert result.crs.to_epsg() == 4269


def test_tiger_face_weights_match_published_pairs_and_compose() -> None:
    source_id = "42001030800303A"
    blocks = gpd.GeoDataFrame(
        {"source_block_geoid": [source_id]},
        geometry=[Polygon([(0, 0), (2, 0), (2, 1), (0, 1)])],
        crs="EPSG:5070",
    )
    faces = gpd.GeoDataFrame(
        {
            "source_block_geoid": [source_id, source_id],
            "target_2000_block_geoid": [
                "420010308011000",
                "420010308011001",
            ],
        },
        geometry=[
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            Polygon([(1, 0), (2, 0), (2, 1), (1, 1)]),
        ],
        crs="EPSG:5070",
    )
    population = pd.DataFrame({"source_block_geoid": [source_id], "P0010001": [10]})
    relationship = pd.DataFrame(
        {
            "source_block_geoid": [source_id, source_id],
            "target_2000_block_geoid": [
                "420010308011000",
                "420010308011001",
            ],
        }
    )

    weights, diagnostics = build_tiger_face_weights(
        blocks, faces, population, relationship
    )
    target = pd.DataFrame(
        {
            "target_2000_block_geoid": [
                "420010308011000",
                "420010308011001",
            ],
            "target_precinct_geoid": ["42001000001", "42001000002"],
            "senate_district": [1, 2],
            "target_atomic_area_square_meters": [1.0, 1.0],
            "target_atomic_weight": [1.0, 1.0],
        }
    )
    crosswalk, composition = build_relationship_atomic_crosswalk(weights, target)

    assert weights["relationship_weight"].tolist() == pytest.approx([0.5, 0.5])
    assert diagnostics["derived_pairs_not_published"] == 0
    assert diagnostics["published_pairs_not_derived"] == 0
    assert crosswalk["weight"].tolist() == pytest.approx([0.5, 0.5])
    assert composition["missing_target_atomic_rows"] == 0


def _rt1(tlid: int, start: tuple[float, float], end: tuple[float, float]) -> str:
    line = [" "] * 228
    line[0] = "1"
    line[5:15] = f"{tlid:>10}"
    line[190:200] = _longitude(start[0])
    line[200:209] = _latitude(start[1])
    line[209:219] = _longitude(end[0])
    line[219:228] = _latitude(end[1])
    return "".join(line) + "\r\n"


def _rti(tlid: int) -> str:
    line = [" "] * 52
    line[0] = "I"
    line[5:15] = f"{tlid:>10}"
    line[21:26] = "C0001"
    line[26:36] = f"{2:>10}"
    return "".join(line) + "\r\n"


def _rta() -> str:
    line = [" "] * 98
    line[0] = "A"
    line[10:15] = "C0001"
    line[15:25] = f"{2:>10}"
    line[40:46] = "0308  "
    line[46:50] = "303A"
    line[89:91] = "42"
    line[91:94] = "001"
    return "".join(line) + "\r\n"


def _rtp() -> str:
    line = [" "] * 45
    line[0] = "P"
    line[10:15] = "C0001"
    line[15:25] = f"{2:>10}"
    line[25:35] = _longitude(-76.5)
    line[35:44] = _latitude(39.5)
    return "".join(line) + "\r\n"


def _rts() -> str:
    line = [" "] * 120
    line[0] = "S"
    line[10:15] = "C0001"
    line[15:25] = f"{2:>10}"
    line[46:48] = "42"
    line[48:51] = "001"
    line[71:77] = "030801"
    line[77:81] = "1000"
    return "".join(line) + "\r\n"


def _longitude(value: float) -> str:
    return f"{round(value * 1_000_000):+010d}"


def _latitude(value: float) -> str:
    return f"{round(value * 1_000_000):+09d}"
