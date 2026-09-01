from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "mappings/feature_metric_catalog_v1.csv"


def test_feature_catalog_is_census_scoped_and_versionable() -> None:
    catalog = pd.read_csv(CATALOG_PATH, dtype="string", keep_default_na=False)

    assert len(catalog) >= 40
    assert catalog["metric_id"].is_unique
    assert catalog["metric_id"].str.len().gt(0).all()
    assert set(catalog["program_scope"]) <= {
        "core_census_acs",
        "core_decennial_census",
        "census_bureau_supplement",
    }
    assert set(catalog["priority"]) <= {"P0", "P1", "P2"}
    assert catalog["source_product_or_table"].str.len().gt(0).all()
    assert catalog["known_limitations"].str.len().gt(0).all()


def test_feature_catalog_covers_the_first_candidate_bundle() -> None:
    catalog = pd.read_csv(CATALOG_PATH, dtype="string", keep_default_na=False)
    p0 = set(catalog.loc[catalog["priority"].eq("P0"), "metric_id"])

    assert {
        "population_total",
        "population_vap",
        "population_cvap",
        "age_distribution",
        "race_ethnicity",
        "education_attainment",
        "local_employment",
        "poverty",
        "income_distribution",
        "foreign_born_citizenship",
        "housing_tenure",
        "population_density",
    } <= p0
