from __future__ import annotations

from zipfile import ZipFile

from census_pa_poc.sources import (
    load_acs5_block_group_population,
    load_acs5_published_population_totals,
    load_pl94_block_population,
    load_pl94_block_population_statewide,
    load_pl94_block_vap_statewide,
)


def _row(size: int, values: dict[int, str]) -> str:
    fields = [""] * size
    for index, value in values.items():
        fields[index] = value
    return "|".join(fields) + "\n"


def _csv_row(size: int, values: dict[int, str]) -> str:
    return _row(size, values).replace("|", ",")


def test_load_pl94_block_population_filters_and_joins(tmp_path) -> None:
    archive = tmp_path / "fixture.zip"
    geography = "".join(
        [
            _row(
                97, {2: "750", 7: "0000001", 9: "420410001001001", 12: "42", 14: "041"}
            ),
            _row(
                97, {2: "750", 7: "0000002", 9: "420430001001001", 12: "42", 14: "043"}
            ),
            _row(97, {2: "140", 7: "0000003", 9: "42041000100", 12: "42", 14: "041"}),
        ]
    )
    file01 = "".join(
        [
            _row(6, {4: "0000001", 5: "17"}),
            _row(6, {4: "0000002", 5: "23"}),
            _row(6, {4: "0000003", 5: "40"}),
        ]
    )
    with ZipFile(archive, "w") as zf:
        zf.writestr("pageo2020.pl", geography)
        zf.writestr("pa000012020.pl", file01)

    result = load_pl94_block_population(archive, "041")

    assert result.to_dict("records") == [
        {"source_block_geoid": "420410001001001", "P0010001": 17}
    ]

    statewide = load_pl94_block_population_statewide(archive)

    assert statewide.to_dict("records") == [
        {"source_block_geoid": "420410001001001", "P0010001": 17},
        {"source_block_geoid": "420430001001001", "P0010001": 23},
    ]


def test_load_pl94_block_vap_uses_p3_in_file02(tmp_path) -> None:
    archive = tmp_path / "fixture.zip"
    geography = "".join(
        [
            _row(
                97,
                {2: "750", 7: "0000001", 9: "420410001001001", 12: "42"},
            ),
            _row(
                97,
                {2: "750", 7: "0000002", 9: "420430001001001", 12: "42"},
            ),
            _row(97, {2: "140", 7: "0000003", 9: "42041000100", 12: "42"}),
        ]
    )
    file02 = "".join(
        [
            _row(6, {4: "0000001", 5: "13"}),
            _row(6, {4: "0000002", 5: "19"}),
            _row(6, {4: "0000003", 5: "32"}),
        ]
    )
    with ZipFile(archive, "w") as zf:
        zf.writestr("pageo2020.pl", geography)
        zf.writestr("pa000022020.pl", file02)

    result = load_pl94_block_vap_statewide(archive)

    assert result.to_dict("records") == [
        {"source_block_geoid": "420410001001001", "P0030001": 13},
        {"source_block_geoid": "420430001001001", "P0030001": 19},
    ]


def test_load_acs5_sequence_population(tmp_path) -> None:
    year_dir = tmp_path / "2011"
    year_dir.mkdir()
    (year_dir / "sequence_lookup.txt").write_text(
        "Table ID,Sequence Number,Start Position\nB01003,3,7\n",
        encoding="utf-8",
    )
    (year_dir / "g20115pa.csv").write_text(
        _csv_row(
            50,
            {
                2: "150",
                4: "0000001",
                9: "42",
                10: "041",
                13: "000100",
                14: "1",
                49: "Block Group 1",
            },
        )
        + _csv_row(50, {2: "140", 4: "0000002"}),
        encoding="latin1",
    )
    archive = year_dir / "20115pa0003000.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr("e20115pa0003000.txt", _csv_row(7, {5: "0000001", 6: "123"}))
        zf.writestr("m20115pa0003000.txt", _csv_row(7, {5: "0000001", 6: "9"}))

    result = load_acs5_block_group_population(2011, year_dir)

    assert result.to_dict("records") == [
        {
            "LOGRECNO": "0000001",
            "source_block_group_geoid": "420410001001",
            "NAME": "Block Group 1",
            "B01003_001E": 123,
            "B01003_001M": 9,
        }
    ]


def test_load_acs5_2009_fixed_width_geography(tmp_path) -> None:
    year_dir = tmp_path / "2009"
    year_dir.mkdir()
    (year_dir / "sequence_lookup.txt").write_text(
        "Table ID,Sequence Number,Start Position\nB01003,3,7\n",
        encoding="utf-8",
    )
    fields = [" "] * 250
    fields[8:11] = "150"
    fields[13:20] = "0000001"
    fields[25:27] = "42"
    fields[27:30] = "041"
    fields[40:46] = "000100"
    fields[46:47] = "1"
    fields[230:243] = "Block Group 1"
    (year_dir / "g20095pa.txt").write_text("".join(fields) + "\n", encoding="latin1")
    archive = year_dir / "20095pa0003000.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr("e20095pa0003000.txt", _csv_row(7, {5: "0000001", 6: "321"}))
        zf.writestr("m20095pa0003000.txt", _csv_row(7, {5: "0000001", 6: "12"}))

    result = load_acs5_block_group_population(2009, year_dir)

    assert result.loc[0, "source_block_group_geoid"] == "420410001001"
    assert result.loc[0, "B01003_001E"] == 321
    assert result.loc[0, "B01003_001M"] == 12


def test_load_acs5_table_population_filters_pa_block_groups(tmp_path) -> None:
    year_dir = tmp_path / "2024"
    year_dir.mkdir()
    (year_dir / "acsdt5y2024-b01003.dat").write_text(
        "GEO_ID|B01003_E001|B01003_M001\n"
        "1500000US420410001001|456|14\n"
        "1500000US360010001001|999|99\n"
        "1400000US42041000100|777|77\n",
        encoding="utf-8",
    )

    result = load_acs5_block_group_population(2024, year_dir)

    assert result.to_dict("records") == [
        {
            "source_block_group_geoid": "420410001001",
            "B01003_001E": 456,
            "B01003_001M": 14,
        }
    ]


def test_load_acs5_sequence_published_state_and_county_totals(tmp_path) -> None:
    year_dir = tmp_path / "2011"
    year_dir.mkdir()
    (year_dir / "sequence_lookup.txt").write_text(
        "Table ID,Sequence Number,Start Position\nB01003,3,7\n",
        encoding="utf-8",
    )
    (year_dir / "g20115pa.csv").write_text(
        _csv_row(
            50,
            {
                2: "040",
                4: "0000001",
                9: "42",
                48: "0400000US42",
                49: "Pennsylvania",
            },
        )
        + _csv_row(
            50,
            {
                2: "050",
                4: "0000002",
                9: "42",
                10: "041",
                48: "0500000US42041",
                49: "Cumberland County, Pennsylvania",
            },
        )
        + _csv_row(50, {2: "050", 4: "0000003", 9: "36", 10: "001"}),
        encoding="latin1",
    )
    archive = year_dir / "20115pa0003000.zip"
    with ZipFile(archive, "w") as zf:
        zf.writestr(
            "e20115pa0003000.txt",
            _csv_row(7, {5: "0000001", 6: "1000"})
            + _csv_row(7, {5: "0000002", 6: "100"}),
        )
        zf.writestr(
            "m20115pa0003000.txt",
            _csv_row(7, {5: "0000001", 6: "-555555555"})
            + _csv_row(7, {5: "0000002", 6: "-555555555"}),
        )

    result = load_acs5_published_population_totals(2011, year_dir)

    assert result[["geography_level", "geography_id", "published_estimate"]].to_dict(
        "records"
    ) == [
        {"geography_level": "county", "geography_id": "041", "published_estimate": 100},
        {"geography_level": "state", "geography_id": "42", "published_estimate": 1000},
    ]
    assert result["published_margin_of_error"].isna().all()
    assert set(result["margin_of_error_status"]) == {
        "controlled_estimate_no_meaningful_moe"
    }


def test_load_acs5_table_published_state_and_county_totals(tmp_path) -> None:
    year_dir = tmp_path / "2024"
    year_dir.mkdir()
    (year_dir / "acsdt5y2024-b01003.dat").write_text(
        "GEO_ID|NAME|B01003_E001|B01003_M001\n"
        "0400000US42|Pennsylvania|1300|-555555555\n"
        "0500000US42041|Cumberland County, Pennsylvania|260|-555555555\n"
        "0500000US36001|Albany County, New York|999|-555555555\n",
        encoding="utf-8",
    )

    result = load_acs5_published_population_totals(2024, year_dir)

    assert result[["geography_level", "geography_id", "published_estimate"]].to_dict(
        "records"
    ) == [
        {"geography_level": "county", "geography_id": "041", "published_estimate": 260},
        {"geography_level": "state", "geography_id": "42", "published_estimate": 1300},
    ]
    assert result["published_margin_of_error"].isna().all()
