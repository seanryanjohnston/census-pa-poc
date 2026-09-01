from __future__ import annotations

import pandas as pd

from census_pa_poc.decennial_socioeconomic import (
    PRODUCTS,
    _all_cells,
    _collapse_source_cells,
)


def test_1990_employment_bridge_conserves_parent() -> None:
    cells = _all_cells("dec_socio_1990_stf3", "employment_status")
    source = pd.DataFrame(
        [{"source_geography_id": "420010301001", **dict.fromkeys(cells, 1)}]
    )

    collapsed = _collapse_source_cells(
        source, "dec_socio_1990_stf3", "employment_status"
    )

    estimates = collapsed.set_index("category")["estimate"]
    assert estimates["population_16_plus"] == 8
    assert estimates.drop("population_16_plus").sum() == 8


def test_2000_education_bridge_conserves_parent() -> None:
    cells = _all_cells("dec_socio_2000_sf3", "education_attainment")
    values = dict.fromkeys(cells, 1)
    values["P037001"] = 32
    source = pd.DataFrame([{"source_geography_id": "420010301011", **values}])

    collapsed = _collapse_source_cells(
        source, "dec_socio_2000_sf3", "education_attainment"
    )
    estimates = collapsed.set_index("category")["estimate"]
    assert estimates["population_25_plus"] == 32
    assert estimates.drop("population_25_plus").sum() == 32


def test_decennial_products_precede_first_applicable_elections() -> None:
    assert pd.Timestamp(PRODUCTS["dec_socio_1990_stf3"]["period_end"]) < pd.Timestamp(
        "1992-11-03"
    )
    assert pd.Timestamp(PRODUCTS["dec_socio_1990_stf3"]["release_date"]) < pd.Timestamp(
        "1992-11-03"
    )
    assert pd.Timestamp(PRODUCTS["dec_socio_2000_sf3"]["period_end"]) < pd.Timestamp(
        "2002-11-05"
    )
    assert pd.Timestamp(PRODUCTS["dec_socio_2000_sf3"]["release_date"]) < pd.Timestamp(
        "2002-11-05"
    )
