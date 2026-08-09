"""Validate the county-by-county 2026 precinct source inventory."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

INVENTORY_FIELDS = (
    "county_fips",
    "county_name",
    "resolution_status",
    "authority_name",
    "authority_url",
    "boundary_source_id",
    "boundary_source_url",
    "producer",
    "product",
    "reference_vintage",
    "effective_date",
    "as_of_date",
    "retrieval_timestamp",
    "sha256",
    "license_access",
    "crs",
    "schema_status",
    "expected_precinct_count",
    "house_assignment_status",
    "senate_assignment_status",
    "contest_eligibility_status",
    "cutoff_status",
    "reviewed_at",
    "review_notes",
)

COUNTIES = {
    "001": "Adams",
    "003": "Allegheny",
    "005": "Armstrong",
    "007": "Beaver",
    "009": "Bedford",
    "011": "Berks",
    "013": "Blair",
    "015": "Bradford",
    "017": "Bucks",
    "019": "Butler",
    "021": "Cambria",
    "023": "Cameron",
    "025": "Carbon",
    "027": "Centre",
    "029": "Chester",
    "031": "Clarion",
    "033": "Clearfield",
    "035": "Clinton",
    "037": "Columbia",
    "039": "Crawford",
    "041": "Cumberland",
    "043": "Dauphin",
    "045": "Delaware",
    "047": "Elk",
    "049": "Erie",
    "051": "Fayette",
    "053": "Forest",
    "055": "Franklin",
    "057": "Fulton",
    "059": "Greene",
    "061": "Huntingdon",
    "063": "Indiana",
    "065": "Jefferson",
    "067": "Juniata",
    "069": "Lackawanna",
    "071": "Lancaster",
    "073": "Lawrence",
    "075": "Lebanon",
    "077": "Lehigh",
    "079": "Luzerne",
    "081": "Lycoming",
    "083": "McKean",
    "085": "Mercer",
    "087": "Mifflin",
    "089": "Monroe",
    "091": "Montgomery",
    "093": "Montour",
    "095": "Northampton",
    "097": "Northumberland",
    "099": "Perry",
    "101": "Philadelphia",
    "103": "Pike",
    "105": "Potter",
    "107": "Schuylkill",
    "109": "Snyder",
    "111": "Somerset",
    "113": "Sullivan",
    "115": "Susquehanna",
    "117": "Tioga",
    "119": "Union",
    "121": "Venango",
    "123": "Warren",
    "125": "Washington",
    "127": "Wayne",
    "129": "Westmoreland",
    "131": "Wyoming",
    "133": "York",
}

RESOLUTION_STATUSES = {"unreviewed", "candidate", "qualified", "reviewed_gap"}
SCHEMA_STATUSES = {"unreviewed", "profiled", "verified", "gap"}
ASSIGNMENT_STATUSES = {"unreviewed", "candidate", "verified", "reviewed_gap"}
CUTOFF_STATUSES = {"not_set", "pending", "met", "missed", "exception"}


@dataclass(frozen=True)
class InventoryValidation:
    """Machine-readable validation result for one inventory snapshot."""

    row_count: int
    status_counts: dict[str, int]
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors

    @property
    def frozen(self) -> bool:
        return self.passed and self.status_counts == {"qualified": 67}

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "frozen": self.frozen,
            "row_count": self.row_count,
            "status_counts": self.status_counts,
            "errors": list(self.errors),
        }


def load_inventory(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Load an inventory CSV and report contract-level header problems."""
    with path.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        fields = tuple(reader.fieldnames or ())
        rows = list(reader)

    errors = [] if fields == INVENTORY_FIELDS else [
        f"header must exactly equal {','.join(INVENTORY_FIELDS)}"
    ]
    return rows, errors


def validate_inventory(path: Path) -> InventoryValidation:
    """Validate coverage, enums, and status-dependent evidence requirements."""
    rows, errors = load_inventory(path)
    errors.extend(_validate_coverage(rows))
    for row in rows:
        errors.extend(_validate_row(row))

    counts = Counter(row.get("resolution_status", "") for row in rows)
    return InventoryValidation(
        row_count=len(rows),
        status_counts=dict(sorted(counts.items())),
        errors=tuple(errors),
    )


def write_qa(path: Path, output: Path) -> InventoryValidation:
    """Validate an inventory and save the result as deterministic JSON."""
    result = validate_inventory(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result.as_dict(), indent=2, sort_keys=True) + "\n")
    return result


def _validate_coverage(rows: list[dict[str, str]]) -> list[str]:
    observed = [_text(row, "county_fips") for row in rows]
    errors = []
    if len(rows) != len(COUNTIES):
        errors.append(f"expected 67 county rows; observed {len(rows)}")
    duplicates = sorted(fips for fips, count in Counter(observed).items() if count > 1)
    if duplicates:
        errors.append(f"duplicate county_fips: {','.join(duplicates)}")
    missing = sorted(set(COUNTIES) - set(observed))
    extra = sorted(set(observed) - set(COUNTIES))
    if missing:
        errors.append(f"missing county_fips: {','.join(missing)}")
    if extra:
        errors.append(f"unexpected county_fips: {','.join(extra)}")
    return errors


def _validate_row(row: dict[str, str]) -> list[str]:
    fips = _text(row, "county_fips")
    prefix = f"county {fips or '<blank>'}"
    errors = []
    expected_name = COUNTIES.get(fips)
    if expected_name and _text(row, "county_name") != expected_name:
        errors.append(f"{prefix}: county_name must be {expected_name}")
    errors.extend(_enum_errors(prefix, row))
    errors.extend(_date_errors(prefix, row))
    errors.extend(_status_evidence_errors(prefix, row))
    return errors


def _enum_errors(prefix: str, row: dict[str, str]) -> list[str]:
    enum_fields = {
        "resolution_status": RESOLUTION_STATUSES,
        "schema_status": SCHEMA_STATUSES,
        "house_assignment_status": ASSIGNMENT_STATUSES,
        "senate_assignment_status": ASSIGNMENT_STATUSES,
        "contest_eligibility_status": ASSIGNMENT_STATUSES,
        "cutoff_status": CUTOFF_STATUSES,
    }
    return [
        f"{prefix}: invalid {field} {row.get(field, '')!r}"
        for field, values in enum_fields.items()
        if _text(row, field) not in values
    ]


def _date_errors(prefix: str, row: dict[str, str]) -> list[str]:
    errors = []
    for field in ("effective_date", "as_of_date", "reviewed_at"):
        value = _text(row, field)
        if value and not _is_date(value):
            errors.append(f"{prefix}: invalid ISO date in {field}")
    timestamp = _text(row, "retrieval_timestamp")
    if timestamp and not _is_datetime(timestamp):
        errors.append(f"{prefix}: invalid ISO datetime in retrieval_timestamp")
    return errors


def _status_evidence_errors(prefix: str, row: dict[str, str]) -> list[str]:
    status = _text(row, "resolution_status")
    base = ("authority_name", "authority_url")
    candidate = base + (
        "boundary_source_id",
        "boundary_source_url",
        "producer",
        "product",
        "as_of_date",
        "retrieval_timestamp",
        "sha256",
        "license_access",
        "crs",
        "expected_precinct_count",
        "reviewed_at",
        "review_notes",
    )
    qualified = candidate + ("reference_vintage", "effective_date")
    required = {
        "unreviewed": base,
        "candidate": candidate,
        "qualified": qualified,
        "reviewed_gap": base + ("reviewed_at", "review_notes"),
    }.get(status, ())
    errors = [
        f"{prefix}: {field} is required for {status}"
        for field in required
        if not _text(row, field).strip()
    ]
    digest = _text(row, "sha256")
    if digest and (len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)):
        errors.append(f"{prefix}: sha256 must be 64 lowercase hexadecimal characters")
    if status == "qualified":
        errors.extend(_qualified_status_errors(prefix, row))
    return errors


def _qualified_status_errors(prefix: str, row: dict[str, str]) -> list[str]:
    expected = {
        "schema_status": "verified",
        "house_assignment_status": "verified",
        "senate_assignment_status": "verified",
        "contest_eligibility_status": "verified",
        "cutoff_status": "met",
    }
    return [
        f"{prefix}: {field} must be {value} for qualified"
        for field, value in expected.items()
        if _text(row, field) != value
    ]


def _is_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_datetime(value: str) -> bool:
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _text(row: dict[str, str], field: str) -> str:
    return row.get(field) or ""
