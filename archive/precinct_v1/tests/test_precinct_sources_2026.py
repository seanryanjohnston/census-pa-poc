from __future__ import annotations

import json

import pytest

from census_pa_poc.precinct_sources_2026 import (
    PasdaSource,
    profile_source,
    sha256,
    validate_registered_candidate,
)


def test_profile_source_preserves_provenance_and_schema(tmp_path) -> None:
    source = PasdaSource("001", "Adams", "adams", 7, "OBJECTID")
    geojson_path = tmp_path / source.geojson_path
    metadata_path = tmp_path / source.metadata_path
    geojson_path.parent.mkdir(parents=True)
    geojson_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "name": "fixture",
                "crs": {
                    "type": "name",
                    "properties": {"name": "urn:ogc:def:crs:EPSG::4269"},
                },
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"OBJECTID": 1, "PRECINCT": "A"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [-77.0, 40.0],
                                    [-76.9, 40.0],
                                    [-76.9, 40.1],
                                    [-77.0, 40.0],
                                ]
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(
            {
                "name": "Adams County Voting Precincts fixture",
                "copyrightText": "Adams County",
            }
        ),
        encoding="utf-8",
    )
    inventory = {
        "001": {
            "resolution_status": "candidate",
            "boundary_source_url": source.query_url,
            "sha256": sha256(geojson_path),
            "expected_precinct_count": "1",
            "license_access": "public fixture",
        }
    }

    result = profile_source(tmp_path, source, inventory)

    assert result["producer"] == "Adams County"
    assert result["exact_product"] == "Adams County Voting Precincts fixture"
    assert result["crs"] == "EPSG:4269"
    assert result["schema"]["feature_rows"] == 1
    assert result["schema"]["invalid_geometries"] == 0
    assert result["disposition"] == "registered_candidate"


def test_registered_candidate_rejects_inventory_drift() -> None:
    source = PasdaSource("001", "Adams", "adams", 7, "OBJECTID")
    row = {
        "resolution_status": "candidate",
        "boundary_source_url": source.query_url,
        "sha256": "different",
        "expected_precinct_count": "1",
    }

    with pytest.raises(ValueError, match="inventory mismatch for county 001"):
        validate_registered_candidate(source, row, "observed", 1)
