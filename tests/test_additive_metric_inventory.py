from pathlib import Path

from census_pa_poc.additive_metric_inventory import (
    EXPECTED_ACS_PRODUCTS,
    EXPECTED_CVAP_PRODUCTS,
    build_qa,
    expand_product_scope,
    load_cvap_products,
    load_definitions,
)

ROOT = Path(__file__).resolve().parents[1]


def test_expand_product_scope() -> None:
    assert expand_product_scope("acs5_2022..acs5_2024") == [
        "acs5_2022",
        "acs5_2023",
        "acs5_2024",
    ]
    assert expand_product_scope("dec_2020") == ["dec_2020"]


def test_inventory_has_exact_product_coverage() -> None:
    definitions = load_definitions(ROOT)
    cvap = load_cvap_products(ROOT)

    assert len(definitions) == 19
    assert set(cvap["product_id"]) == EXPECTED_CVAP_PRODUCTS
    assert EXPECTED_ACS_PRODUCTS == {f"acs5_{year}" for year in range(2009, 2025)}


def test_inventory_acceptance_checks_pass() -> None:
    qa = build_qa(ROOT)

    assert qa["passed"], [check for check in qa["checks"] if not check["passed"]]
