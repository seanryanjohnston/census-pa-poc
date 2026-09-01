from __future__ import annotations

import pandas as pd

from census_pa_poc.statewide_2020 import (
    aggregate_fragments_to_senate,
    aggregate_precincts_to_senate,
    aggregate_to_precincts,
    load_senate_equivalency,
)


def test_load_senate_equivalency_reads_headerless_csv(tmp_path) -> None:
    path = tmp_path / "equivalency.csv"
    path.write_text('"420010001001001A","2"\n"420010001001001B","1"\n')

    result = load_senate_equivalency(path)

    assert result.to_dict("records") == [
        {"source_fragment_geoid": "420010001001001A", "senate_district": 2},
        {"source_fragment_geoid": "420010001001001B", "senate_district": 1},
    ]


def test_split_allocation_and_independent_senate_routes_agree() -> None:
    population = pd.DataFrame(
        {"source_block_geoid": ["420010001001001"], "P0010001": [10]}
    )
    crosswalk = pd.DataFrame(
        {
            "source_block_geoid": ["420010001001001", "420010001001001"],
            "target_precinct_geoid": ["42001000001", "42001000002"],
            "weight": [0.4, 0.6],
        }
    )
    precinct_result = aggregate_to_precincts(population, crosswalk)
    overlay = pd.DataFrame(
        {
            "target_precinct_geoid": ["42001000001", "42001000002"],
            "senate_district": [1, 2],
            "area_weight": [1.0, 1.0],
        }
    )
    lrc_blocks = pd.DataFrame(
        {
            "GEOID20": ["420010001001001A", "420010001001001B"],
            "P0010001": [4, 6],
        }
    )
    equivalency = pd.DataFrame(
        {
            "source_fragment_geoid": [
                "420010001001001A",
                "420010001001001B",
            ],
            "senate_district": [1, 2],
        }
    )

    precinct_route = aggregate_precincts_to_senate(precinct_result, overlay)
    direct_route = aggregate_fragments_to_senate(lrc_blocks, equivalency)

    assert precinct_result.to_dict("records") == [
        {"target_precinct_geoid": "42001000001", "population": 4},
        {"target_precinct_geoid": "42001000002", "population": 6},
    ]
    assert precinct_route["population"].tolist() == [4.0, 6.0]
    assert direct_route["population"].tolist() == [4, 6]
