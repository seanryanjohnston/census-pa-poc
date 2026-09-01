from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import box

from census_pa_poc.data_explorer import (
    CURRENT_METRICS,
    CurrentPlanTables,
    ExplorerTables,
    current_district_results,
    current_metric_options,
    current_reconciliation,
    district_view,
    impacted_district_geometries,
    load_current_plan_tables,
    load_split_fragment_geometry,
    metric_options,
    normalize_acs,
    normalize_current_p001,
    normalize_decennial,
    normalize_vap,
    plan_options,
    product_options,
    provenance,
    split_allocation_view,
    split_block_options,
    split_block_summary,
    summarize_view,
    table_view,
    validate_current_plan_tables,
    validate_tables,
)


def test_normalizers_keep_estimates_and_moes_separate() -> None:
    decennial = normalize_decennial(
        pd.DataFrame(
            {
                "population_product_id": ["dec_2020"],
                "source_metric_id": ["P0010001"],
                "target_chamber": ["house"],
                "target_plan_id": ["pa_house_2021_final"],
                "target_plan_reference_vintage": ["2021"],
                "target_district_id": [1],
                "population": [10.0],
                "method_id": ["direct"],
            }
        )
    )
    acs = normalize_acs(
        pd.DataFrame(
            {
                "population_product_id": ["acs5_2024"],
                "source_estimate_metric_id": ["B01003_001E"],
                "source_moe_metric_id": ["B01003_001M"],
                "moe_confidence_level": [0.9],
                "target_chamber": ["house"],
                "target_plan_id": ["pa_house_2021_final"],
                "target_plan_reference_vintage": ["2021"],
                "target_district_id": [1],
                "estimate": [11.0],
                "margin_of_error": [2.0],
                "method_id": ["direct_acs"],
                "uncertainty": ["approximate"],
            }
        )
    )
    assert decennial.loc[0, "estimate"] == 10.0
    assert pd.isna(decennial.loc[0, "margin_of_error"])
    assert acs.loc[0, "estimate"] == 11.0
    assert acs.loc[0, "margin_of_error"] == 2.0
    assert decennial.loc[0, "metric_id"] == "total_population"
    assert acs.loc[0, "metric_id"] == "total_population"


def test_vap_normalizer_keeps_universe_and_no_moe_explicit() -> None:
    result = normalize_vap(
        pd.DataFrame(
            {
                "population_product_id": ["census_2020_pa_pl"],
                "source_metric_id": ["P0030001"],
                "metric_label": ["Voting-age population"],
                "population_universe": ["total_population_18_years_and_over"],
                "target_chamber": ["house"],
                "target_plan_id": ["pa_house_2021_final"],
                "target_district_id": ["1"],
                "estimate": [8.0],
                "moe": [pd.NA],
                "moe_treatment": ["not_applicable_exact_decennial_count"],
                "crosswalk_method_id": [
                    "lrc_fragment_p003_vap_direct_legislative_v1"
                ],
            }
        )
    )

    assert result.loc[0, "metric_id"] == "voting_age_population"
    assert result.loc[0, "source_estimate_metric_id"] == "P0030001"
    assert result.loc[0, "population_universe"] == (
        "total_population_18_years_and_over"
    )
    assert pd.isna(result.loc[0, "margin_of_error"])


def test_current_p001_normalizer_uses_current_plan_schema() -> None:
    result = normalize_current_p001(
        pd.DataFrame(
            {
                "target_chamber": ["house"],
                "target_plan_id": ["pa_house_2021_final"],
                "target_district_id": ["1"],
                "population": [10.0],
                "population_product_id": ["census_2020_pa_pl"],
                "source_metric_id": ["P0010001"],
                "population_universe": ["standard_total_population"],
                "crosswalk_method_id": ["p001_method"],
            }
        )
    )

    assert result.loc[0, "metric_id"] == "total_population"
    assert result.loc[0, "estimate"] == 10.0
    assert result.loc[0, "target_district_id"] == 1
    assert result.loc[0, "target_plan_reference_vintage"] == "2021"


def test_direct_view_options_join_and_summaries() -> None:
    tables = fixture_tables()
    assert plan_options(tables, "house") == {
        "2021 plan (2022–2026)": "pa_house_2021_final"
    }
    assert product_options(tables, "house", "pa_house_2021_final") == {
        "acs5_2024 (acs5)": "acs5_2024"
    }
    assert metric_options(tables, "house", "pa_house_2021_final") == {
        "Total population": "total_population"
    }
    view = district_view(
        tables, "house", "pa_house_2021_final", "acs5_2024"
    )
    assert len(view) == 2
    assert summarize_view(view) == {
        "district_count": 2,
        "estimate_total": 21.0,
        "moe_available": True,
    }
    assert provenance(view)["source_moe_metric_id"] == "B01003_001M"
    assert table_view(view)["target_district_id"].tolist() == [1, 2]
    one = district_view(
        tables, "house", "pa_house_2021_final", "acs5_2024", district_id=2
    )
    assert one["estimate"].tolist() == [11.0]


def test_validation_rejects_precinct_columns() -> None:
    tables = fixture_tables()
    stale = tables.results.assign(target_precinct_geoid="x")
    with pytest.raises(ValueError, match="precinct columns"):
        validate_tables(stale, tables.plans, tables.partitions)


def test_current_plan_reconciliation_and_split_views() -> None:
    tables = current_fixture_tables()

    assert current_metric_options(tables) == {
        "Total population": "total_population",
        "Voting-age population (18+)": "voting_age_population",
    }
    reconciliation = current_reconciliation(tables, "total_population")
    assert reconciliation["population"].tolist() == [21.0, 21.0, 21.0]
    assert reconciliation["difference_from_source"].tolist() == [0.0, 0.0, 0.0]
    assert reconciliation["status"].tolist() == ["Source benchmark", "Pass", "Pass"]
    assert len(current_district_results(tables, "total_population")) == 4
    assert split_block_summary(tables, "total_population").to_dict("records") == [
        {"chamber": "State House", "split_source_blocks": 1},
        {"chamber": "State Senate", "split_source_blocks": 0},
    ]
    assert split_block_options(tables, "total_population") == {
        "2020 Census block split": "split"
    }
    allocation = split_allocation_view(tables, "total_population", "split")
    assert allocation["allocation_percent"].tolist() == [75.0, 25.0]
    impacted = impacted_district_geometries(tables, "total_population", "split")
    assert impacted["district_label"].tolist() == [
        "House district 1",
        "House district 2",
    ]
    assert impacted.geometry.notna().all()


def test_current_plan_validation_rejects_nonconservation() -> None:
    tables = current_fixture_tables()
    rows = []
    for metric_id, source_metric_id in (
        ("total_population", "P0010001"),
        ("voting_age_population", "P0030001"),
    ):
        for chamber, plan_id, district_count in (
            ("house", "pa_house_2021_final", 203),
            ("senate", "pa_senate_2021_final", 50),
        ):
            for district_id in range(1, district_count + 1):
                rows.append(
                    {
                        "metric_id": metric_id,
                        "target_chamber": chamber,
                        "target_plan_id": plan_id,
                        "target_district_id": district_id,
                        "estimate": 21.0 / district_count,
                        "source_estimate_metric_id": source_metric_id,
                        "method_id": f"{metric_id}_method",
                    }
                )
    bad_results = pd.DataFrame(rows)
    bad_results.loc[
        bad_results["metric_id"].eq("total_population")
        & bad_results["target_chamber"].eq("senate"),
        "estimate",
    ] += 1
    with pytest.raises(ValueError, match="does not conserve state total"):
        validate_current_plan_tables(
            CurrentPlanTables(
                results=bad_results,
                plans=tables.plans,
                source_totals=tables.source_totals,
                split_allocations=tables.split_allocations,
            )
        )


def test_real_direct_products_load_when_available() -> None:
    from census_pa_poc.data_explorer import load_explorer_tables

    root = Path(__file__).resolve().parents[1]
    if not (root / "data/processed/direct_legislative/poc029").exists():
        pytest.skip("ignored local POC029 products are unavailable")
    tables = load_explorer_tables(root)
    view = district_view(
        tables, "house", "pa_house_2021_final", "acs5_2024"
    )
    assert len(view) == 203
    assert view["margin_of_error"].notna().all()
    assert not any("precinct" in column.lower() for column in tables.results.columns)
    assert metric_options(tables, "house", "pa_house_2021_final") == {
        "Total population": "total_population",
        "Voting-age population": "voting_age_population",
    }
    vap = district_view(
        tables,
        "senate",
        "pa_senate_2021_final",
        "census_2020_pa_pl",
        metric_id="voting_age_population",
    )
    assert len(vap) == 50
    assert vap["estimate"].sum() == 10_353_548
    assert vap["margin_of_error"].isna().all()


def test_real_current_plan_reconciliation_and_split_geometry() -> None:
    root = Path(__file__).resolve().parents[1]
    if not (root / "data/processed/direct_legislative/poc029").exists():
        pytest.skip("ignored local direct products are unavailable")
    tables = load_current_plan_tables(root)

    expected_totals = {
        "total_population": 13_002_700,
        "voting_age_population": 10_353_548,
    }
    for metric_id in CURRENT_METRICS:
        reconciliation = current_reconciliation(tables, metric_id)
        assert reconciliation["population"].tolist() == [
            expected_totals[metric_id],
            expected_totals[metric_id],
            expected_totals[metric_id],
        ]
        assert reconciliation["difference_from_source"].eq(0).all()
        assert split_block_summary(tables, metric_id).to_dict("records") == [
            {"chamber": "State House", "split_source_blocks": 1},
            {"chamber": "State Senate", "split_source_blocks": 0},
        ]

    geometry = load_split_fragment_geometry(
        root,
        tables,
        "total_population",
        "421010257002008",
    )
    assert len(geometry) == 2
    assert set(geometry["target_district_id"]) == {"194", "200"}
    assert geometry["fragment_value"].sum() == 40
    impacted = impacted_district_geometries(
        tables,
        "total_population",
        "421010257002008",
    )
    assert impacted["target_district_id"].astype(int).tolist() == [194, 200]
    assert impacted["district_label"].tolist() == [
        "House district 194",
        "House district 200",
    ]
    assert impacted.geometry.notna().all()


def fixture_tables() -> ExplorerTables:
    plans = gpd.GeoDataFrame(
        {
            "target_chamber": ["house", "house"],
            "target_plan_id": ["pa_house_2021_final", "pa_house_2021_final"],
            "target_plan_reference_vintage": ["2021", "2021"],
            "first_applicable_election": ["2022", "2022"],
            "last_applicable_election": ["2026", "2026"],
            "target_district_id": [1, 2],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:4326",
    )
    results = pd.DataFrame(
        {
            "population_product_id": ["acs5_2024", "acs5_2024"],
            "result_family": ["acs5", "acs5"],
            "metric_id": ["total_population", "total_population"],
            "metric_label": ["Total population", "Total population"],
            "population_universe": ["total_population", "total_population"],
            "source_estimate_metric_id": ["B01003_001E", "B01003_001E"],
            "source_moe_metric_id": ["B01003_001M", "B01003_001M"],
            "moe_confidence_level": [0.9, 0.9],
            "target_chamber": ["house", "house"],
            "target_plan_id": ["pa_house_2021_final", "pa_house_2021_final"],
            "target_plan_reference_vintage": ["2021", "2021"],
            "target_district_id": [1, 2],
            "estimate": [10.0, 11.0],
            "margin_of_error": [1.0, 2.0],
            "moe_treatment": [
                "weighted_source_moe_then_rss_v1",
                "weighted_source_moe_then_rss_v1",
            ],
            "method_id": ["direct_acs", "direct_acs"],
            "uncertainty": ["approximate", "approximate"],
        }
    )
    partitions = pd.DataFrame(index=range(39))
    return ExplorerTables(results=results, plans=plans, partitions=partitions)


def current_fixture_tables() -> CurrentPlanTables:
    plans = gpd.GeoDataFrame(
        {
            "target_chamber": ["house", "house", "senate", "senate"],
            "target_plan_id": [
                "pa_house_2021_final",
                "pa_house_2021_final",
                "pa_senate_2021_final",
                "pa_senate_2021_final",
            ],
            "target_district_id": [1, 2, 1, 2],
        },
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1), box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:4326",
    )
    result_rows = []
    for metric_id, source_metric_id in (
        ("total_population", "P0010001"),
        ("voting_age_population", "P0030001"),
    ):
        for chamber, plan_id in (
            ("house", "pa_house_2021_final"),
            ("senate", "pa_senate_2021_final"),
        ):
            for district_id, estimate in ((1, 10.0), (2, 11.0)):
                result_rows.append(
                    {
                        "metric_id": metric_id,
                        "target_chamber": chamber,
                        "target_plan_id": plan_id,
                        "target_district_id": district_id,
                        "estimate": estimate,
                        "source_estimate_metric_id": source_metric_id,
                        "method_id": f"{metric_id}_method",
                    }
                )
    split_allocations = pd.DataFrame(
        {
            "metric_id": [
                "total_population",
                "total_population",
                "voting_age_population",
                "voting_age_population",
            ],
            "target_chamber": ["house"] * 4,
            "target_plan_id": ["pa_house_2021_final"] * 4,
            "source_geography_id": ["split"] * 4,
            "target_district_id": [1, 2, 1, 2],
            "source_value": [20, 20, 20, 20],
            "allocated_value": [15, 5, 15, 5],
            "weight": [0.75, 0.25, 0.75, 0.25],
            "weight_method": ["published"] * 4,
            "atomic_fragment_count": [1] * 4,
        }
    )
    return CurrentPlanTables(
        results=pd.DataFrame(result_rows),
        plans=plans,
        source_totals=pd.DataFrame(
            {
                "metric_id": ["total_population", "voting_age_population"],
                "state_source_total": [21.0, 21.0],
            }
        ),
        split_allocations=split_allocations,
    )
