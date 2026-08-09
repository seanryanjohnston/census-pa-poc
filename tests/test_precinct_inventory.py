from __future__ import annotations

import csv
from pathlib import Path

from census_pa_poc.precinct_inventory import (
    COUNTIES,
    INVENTORY_FIELDS,
    validate_inventory,
)


def _row(fips: str, name: str) -> dict[str, str]:
    row = dict.fromkeys(INVENTORY_FIELDS, "")
    row.update(
        {
            "county_fips": fips,
            "county_name": name,
            "resolution_status": "unreviewed",
            "authority_name": f"{name} County Board of Elections",
            "authority_url": "https://www.pa.gov/agencies/vote/contact-us/contact-your-election-officials",
            "schema_status": "unreviewed",
            "house_assignment_status": "unreviewed",
            "senate_assignment_status": "unreviewed",
            "contest_eligibility_status": "unreviewed",
            "cutoff_status": "not_set",
        }
    )
    return row


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=INVENTORY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def test_tracked_inventory_passes_contract_but_is_not_frozen() -> None:
    path = Path(__file__).parents[1] / "mappings" / "precinct_sources_2026.csv"

    result = validate_inventory(path)

    assert result.passed
    assert not result.frozen
    assert result.row_count == 67
    assert result.status_counts == {"candidate": 2, "unreviewed": 65}


def test_qualified_requires_verified_assignments_and_cutoff(tmp_path) -> None:
    rows = [_row(fips, name) for fips, name in COUNTIES.items()]
    rows[0].update(
        {
            "resolution_status": "qualified",
            "boundary_source_id": "adams-test",
            "boundary_source_url": "https://example.test/boundaries",
            "producer": "Adams County",
            "product": "Precinct boundaries",
            "reference_vintage": "2026 general election",
            "effective_date": "2026-11-03",
            "as_of_date": "2026-10-01",
            "retrieval_timestamp": "2026-10-01T12:00:00+00:00",
            "sha256": "a" * 64,
            "license_access": "public",
            "crs": "EPSG:4326",
            "expected_precinct_count": "50",
            "reviewed_at": "2026-10-01",
            "review_notes": "fixture",
            "schema_status": "verified",
            "house_assignment_status": "verified",
            "senate_assignment_status": "verified",
            "contest_eligibility_status": "verified",
            "cutoff_status": "pending",
        }
    )
    path = tmp_path / "inventory.csv"
    _write(path, rows)

    result = validate_inventory(path)

    assert not result.passed
    assert "county 001: cutoff_status must be met for qualified" in result.errors


def test_candidate_requires_frozen_source_evidence(tmp_path) -> None:
    rows = [_row(fips, name) for fips, name in COUNTIES.items()]
    rows[0]["resolution_status"] = "candidate"
    path = tmp_path / "inventory.csv"
    _write(path, rows)

    result = validate_inventory(path)

    assert not result.passed
    assert "county 001: sha256 is required for candidate" in result.errors
    assert "county 001: effective_date is required for candidate" not in result.errors
