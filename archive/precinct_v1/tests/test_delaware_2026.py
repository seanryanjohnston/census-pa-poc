from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from census_pa_poc.delaware_2026 import (
    build_consolidation_crosswalk,
    canonical_source_id,
    data_raw_relative_path,
    source_ids_for_record,
)


def test_canonical_source_id_repairs_observed_delaware_defects() -> None:
    assert canonical_source_id(
        SimpleNamespace(precinctid="010000W-1", name="ALDAN PRECINCT WEST")
    ) == ("0100000W-1", "pad_aldan_west_identifier")
    assert canonical_source_id(
        SimpleNamespace(precinctid="14001001-1", name="DARBY BOROUGH WARD 1 PRECINCT 2")
    ) == ("14001002-1", "repair_darby_ward_1_precinct_2_identifier")
    assert canonical_source_id(
        SimpleNamespace(precinctid="04000NE -1", name="CHADDS FORD NORTHEAST")
    ) == ("04000NE-1", "remove_identifier_whitespace")
    assert canonical_source_id(SimpleNamespace(precinctid="", name="")) == (
        None,
        "missing_source_identifier",
    )


def test_source_ids_for_record_supports_all_official_notations() -> None:
    source_ids = {
        "07000001-1",
        "07000002-1",
        "10003001-1",
        "10003002-1",
        "1700000E-1",
        "1700000W-1",
    }

    assert source_ids_for_record("07000001-1", "1 & 2", source_ids) == [
        "07000001-1",
        "07000002-1",
    ]
    assert source_ids_for_record("10003000-1", "3-1 & 3-2", source_ids) == [
        "10003001-1",
        "10003002-1",
    ]
    assert source_ids_for_record("17000000-1", "E & W", source_ids) == [
        "1700000E-1",
        "1700000W-1",
    ]


def test_crosswalk_maps_each_old_precinct_once() -> None:
    active = pd.DataFrame(
        [
            {
                "target_precinct_id": "07000001-1",
                "previous_expression": "1 & 2",
            },
            {
                "target_precinct_id": "07000003-1",
                "previous_expression": None,
            },
        ]
    )
    source_ids = {"07000001-1", "07000002-1", "07000003-1"}

    result = build_consolidation_crosswalk(active, source_ids)

    assert result[["source_precinct_id", "target_precinct_id"]].to_dict("records") == [
        {
            "source_precinct_id": "07000001-1",
            "target_precinct_id": "07000001-1",
        },
        {
            "source_precinct_id": "07000002-1",
            "target_precinct_id": "07000001-1",
        },
        {
            "source_precinct_id": "07000003-1",
            "target_precinct_id": "07000003-1",
        },
    ]
    assert result["nearest_assignment"].eq(False).all()


def test_manifest_path_is_stable_for_relative_and_absolute_roots() -> None:
    expected = "data/raw/example/source.pdf"

    assert data_raw_relative_path(Path(expected)) == expected
    assert data_raw_relative_path(Path("/workspace/project") / expected) == expected
