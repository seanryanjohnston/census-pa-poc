from __future__ import annotations

import json

from census_pa_poc.acs_inventory import profile_passes, profile_product_metadata


def test_product_profile_preserves_estimate_moe_and_block_group(tmp_path) -> None:
    variables = tmp_path / "variables.json"
    geography = tmp_path / "geography.json"
    variables.write_text(
        json.dumps(
            {
                "variables": {
                    "B01003_001E": {
                        "label": "Estimate!!Total",
                        "concept": "Total Population",
                        "predicateType": "int",
                        "group": "B01003",
                        "universe": "Total population",
                    },
                    "B01003_001M": {
                        "label": "Margin of Error!!Total",
                        "concept": "Total Population",
                        "predicateType": "int",
                        "group": "B01003",
                        "universe": "Total population",
                    },
                }
            }
        )
    )
    geography.write_text(
        json.dumps(
            {
                "fips": [
                    {
                        "name": "block group",
                        "geoLevelDisplay": "150",
                        "referenceDate": "2024-01-01",
                        "requires": ["state", "county", "tract"],
                    }
                ]
            }
        )
    )

    profile = profile_product_metadata(
        variables, geography, "B01003_001E", "B01003_001M"
    )

    assert profile_passes(profile)
    assert profile["block_group_supported_by_api_manifest"] is True
    assert profile["block_group_geography"][0]["geoLevelDisplay"] == "150"


def test_product_profile_types_missing_block_group_api_support(tmp_path) -> None:
    variables = tmp_path / "variables.json"
    geography = tmp_path / "geography.json"
    variables.write_text(
        json.dumps(
            {
                "variables": {
                    "B01003_001E": {
                        "label": "Estimate!!Total",
                        "concept": "B01003. Total Population",
                        "predicateType": "int",
                        "group": "B01003",
                    },
                    "B01003_001M": {
                        "label": "Margin of Error!!Total",
                        "concept": "B01003. Total Population",
                        "predicateType": "int",
                        "group": "B01003",
                    },
                }
            }
        )
    )
    geography.write_text(json.dumps({"fips": [{"name": "state"}]}))

    profile = profile_product_metadata(
        variables, geography, "B01003_001E", "B01003_001M"
    )

    assert profile_passes(profile)
    assert profile["block_group_supported_by_api_manifest"] is False
