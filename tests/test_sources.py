from __future__ import annotations

from zipfile import ZipFile

from census_pa_poc.sources import load_pl94_block_population


def _row(size: int, values: dict[int, str]) -> str:
    fields = [""] * size
    for index, value in values.items():
        fields[index] = value
    return "|".join(fields) + "\n"


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
