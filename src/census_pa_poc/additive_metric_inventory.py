"""Validate the frozen POC033 additive-metric inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

DEFINITIONS_PATH = "mappings/additive_metric_definitions_v1.csv"
CVAP_PRODUCTS_PATH = "mappings/cvap_products_v1.csv"
ACS_PRODUCTS_PATH = "mappings/acs5_products.csv"
PARTITIONS_PATH = "mappings/legislative_population_partitions_v1.csv"

REQUIRED_FAMILIES = {
    "age_distribution",
    "citizen_voting_age_population",
    "education_attainment",
    "employment_status",
    "foreign_born_citizenship",
    "household_income",
    "housing_tenure",
    "population_density",
    "poverty_ratio",
    "race_ethnicity",
    "voting_age_population",
}
EXPECTED_ACS_PRODUCTS = {f"acs5_{year}" for year in range(2009, 2025)}
EXPECTED_CVAP_PRODUCTS = {f"cvap_{year}" for year in range(2009, 2025)}


def load_definitions(root: Path) -> pd.DataFrame:
    """Load the canonical transformation and support definitions."""
    return pd.read_csv(root / DEFINITIONS_PATH, dtype="string", keep_default_na=False)


def load_cvap_products(root: Path) -> pd.DataFrame:
    """Load the exact CVAP release inventory."""
    return pd.read_csv(root / CVAP_PRODUCTS_PATH, dtype="string", keep_default_na=False)


def expand_product_scope(scope: str) -> list[str]:
    """Expand the bounded product-range notation used by the inventory."""
    if ".." not in scope:
        return [scope]
    start, end = scope.split("..", maxsplit=1)
    start_prefix, start_year = start.rsplit("_", maxsplit=1)
    end_prefix, end_year = end.rsplit("_", maxsplit=1)
    if start_prefix != end_prefix:
        raise ValueError(f"Product range changes prefix: {scope}")
    return [
        f"{start_prefix}_{year}" for year in range(int(start_year), int(end_year) + 1)
    ]


def inventory_checks(root: Path) -> list[dict[str, object]]:
    """Return machine-readable POC033 checks."""
    definitions = load_definitions(root)
    cvap = load_cvap_products(root)
    acs = pd.read_csv(root / ACS_PRODUCTS_PATH, dtype="string", keep_default_na=False)
    partitions = pd.read_csv(
        root / PARTITIONS_PATH, dtype="string", keep_default_na=False
    )
    checks: list[dict[str, object]] = []

    def check(name: str, passed: bool, detail: object) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    families = set()
    for value in definitions["metric_family"]:
        families.update(value.split("|"))
    check("required_metric_families", families == REQUIRED_FAMILIES, sorted(families))
    check(
        "definition_ids_unique",
        definitions["definition_id"].is_unique,
        len(definitions),
    )
    check(
        "definitions_frozen_or_accepted",
        definitions["status"].isin({"inventory_frozen", "accepted_poc031"}).all(),
        definitions["status"].value_counts().to_dict(),
    )
    check(
        "all_definitions_declare_universe",
        definitions["universe"].str.len().gt(0).all(),
        definitions.loc[definitions["universe"].eq(""), "definition_id"].tolist(),
    )
    check(
        "all_definitions_declare_support",
        definitions["support_candidate"].str.len().gt(0).all(),
        definitions.loc[
            definitions["support_candidate"].eq(""), "definition_id"
        ].tolist(),
    )
    check(
        "all_definitions_declare_cutoff_and_plan_policy",
        definitions["release_cutoff"].str.len().gt(0).all()
        and definitions["plan_applicability"].str.len().gt(0).all(),
        len(definitions),
    )

    acs_products = set(acs["product_id"])
    check(
        "acs_products_complete",
        acs_products == EXPECTED_ACS_PRODUCTS,
        sorted(acs_products),
    )
    check(
        "cvap_products_complete",
        set(cvap["product_id"]) == EXPECTED_CVAP_PRODUCTS,
        sorted(cvap["product_id"]),
    )
    check("cvap_product_ids_unique", cvap["product_id"].is_unique, len(cvap))
    cvap_release = pd.to_datetime(cvap["release_date"])
    cvap_period_end = pd.to_datetime(cvap["period_end"])
    check(
        "cvap_release_after_reference_period",
        cvap_release.gt(cvap_period_end).all(),
        cvap[["product_id", "release_date"]].to_dict("records"),
    )
    expected_cvap_urls = cvap.apply(
        lambda row: (
            f"/{row['estimate_year']}/{row['estimate_year']}-cvap/" in row["csv_url"]
        ),
        axis="columns",
    )
    check(
        "cvap_urls_match_product_year",
        expected_cvap_urls.all(),
        int(expected_cvap_urls.sum()),
    )

    scoped_acs = set()
    scoped_cvap = set()
    for scope in definitions["source_products"]:
        if scope.startswith("acs5_"):
            scoped_acs.update(expand_product_scope(scope))
        if scope.startswith("cvap_"):
            scoped_cvap.update(expand_product_scope(scope))
    check(
        "definition_acs_scopes_resolve", scoped_acs <= acs_products, sorted(scoped_acs)
    )
    check(
        "definition_cvap_scopes_resolve",
        scoped_cvap == EXPECTED_CVAP_PRODUCTS,
        sorted(scoped_cvap),
    )

    grouped_acs = definitions[
        definitions["source_products"].str.startswith("acs5_")
        & definitions["estimate_expression"].str.contains("+", regex=False)
    ]
    check(
        "grouped_acs_cells_declare_rss_moe",
        grouped_acs["moe_expression"].str.contains("RSS", regex=False).all(),
        grouped_acs["definition_id"].tolist(),
    )
    check(
        "no_median_is_allocated",
        ~definitions["estimate_expression"].str.lower().str.contains("median").any(),
        definitions.loc[
            definitions["estimate_expression"].str.lower().str.contains("median"),
            "definition_id",
        ].tolist(),
    )
    employment = definitions[definitions["metric_family"].eq("employment_status")]
    employment_products = set()
    for scope in employment["source_products"]:
        employment_products.update(expand_product_scope(scope))
    check(
        "employment_b23001_tract_spans_full_acs_series",
        employment_products == EXPECTED_ACS_PRODUCTS
        and employment["source_table"].tolist() == ["B23001"]
        and employment["source_grain"].tolist() == ["product-vintage Census tract"],
        employment[["source_products", "source_table", "source_grain"]].to_dict(
            "records"
        ),
    )
    education = definitions[definitions["metric_family"].eq("education_attainment")]
    check(
        "education_b15002_spans_full_acs_series",
        len(education) == 1
        and education.iloc[0]["source_products"] == "acs5_2009..acs5_2024"
        and education.iloc[0]["source_table"] == "B15002"
        and "B15003 retained only" in education.iloc[0]["category_bridge"],
        education[["source_products", "source_table"]].to_dict("records"),
    )
    density = definitions.loc[
        definitions["definition_id"].eq("density_all_population")
    ].iloc[0]
    check(
        "density_land_definition_exact",
        "EPSG:5070" in density["aggregation_note"]
        and "areawater" in density["aggregation_note"].lower(),
        density["aggregation_note"],
    )

    partition_products = set(partitions["population_product_id"])
    decennial_products = ("dec_1990", "dec_2000", "dec_2010", "dec_2020")
    missing_partition_products = (EXPECTED_ACS_PRODUCTS - partition_products) | {
        product for product in decennial_products if product not in partition_products
    }
    check(
        "plan_applicability_products_resolve",
        not missing_partition_products,
        sorted(missing_partition_products),
    )
    return checks


def build_qa(root: Path) -> dict[str, object]:
    """Build the POC033 acceptance summary without downloading source data."""
    definitions = load_definitions(root)
    cvap = load_cvap_products(root)
    checks = inventory_checks(root)
    return {
        "task": "POC033",
        "definition_count": len(definitions),
        "cvap_product_count": len(cvap),
        "metric_families": sorted(REQUIRED_FAMILIES),
        "checks": checks,
        "passed": all(item["passed"] for item in checks),
    }


def run(root: Path) -> dict[str, object]:
    """Validate and save ignored machine-readable POC033 evidence."""
    root = root.resolve()
    qa = build_qa(root)
    artifact = root / "artifacts/poc033/inventory_qa.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(qa, indent=2, sort_keys=True) + "\n")
    if not qa["passed"]:
        raise RuntimeError(f"POC033 inventory failed; inspect {artifact}")
    return qa


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    qa = run(args.root)
    print(json.dumps({"passed": qa["passed"], "checks": len(qa["checks"])}))


if __name__ == "__main__":
    main()
