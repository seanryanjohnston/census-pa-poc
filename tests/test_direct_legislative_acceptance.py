from census_pa_poc.direct_legislative_acceptance import (
    declaration_failures,
    valid_sha256,
)


def test_valid_sha256_requires_lowercase_hex() -> None:
    assert valid_sha256("a" * 64)
    assert not valid_sha256("A" * 64)
    assert not valid_sha256("a" * 63)


def test_declaration_failures_names_missing_contract_fields() -> None:
    failures = declaration_failures(
        [
            {
                "population_product_id": "acs5_2024",
                "target_chamber": "house",
                "target_plan_id": "pa_house_2021_final",
            }
        ]
    )

    assert failures[0]["partition"] == ("acs5_2024:house:pa_house_2021_final")
    assert "source_geography_grain" in failures[0]["missing"]
