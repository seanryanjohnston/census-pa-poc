"""Profile the frozen PASDA county candidates used by POC008."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd

from census_pa_poc.precinct_inventory import write_qa


@dataclass(frozen=True)
class PasdaSource:
    """One exact PASDA layer retrieval and its POC008 disposition."""

    county_fips: str
    county_name: str
    slug: str
    layer_id: int
    oid_field: str
    disposition: str = "registered_candidate"

    @property
    def service_name(self) -> str:
        return f"{self.county_name.replace(' ', '')}County"

    @property
    def query_url(self) -> str:
        base = (
            "https://maps.pasda.psu.edu/ArcGIS/rest/services/pasda/"
            f"{self.service_name}/MapServer/{self.layer_id}/query"
        )
        return (
            f"{base}?where=1%3D1&outFields=*&returnGeometry=true&outSR=4269"
            f"&orderByFields={self.oid_field}&f=geojson"
        )

    @property
    def geojson_path(self) -> str:
        return (
            "data/raw/poc008_pasda_2026_candidates/"
            f"{self.county_fips}_{self.slug}_precincts.geojson"
        )

    @property
    def metadata_path(self) -> str:
        return (
            "data/raw/poc008_pasda_2026_candidates/"
            f"{self.county_fips}_{self.slug}_layer.json"
        )


PASDA_SOURCES = (
    PasdaSource("003", "Allegheny", "allegheny", 28, "OBJECTID"),
    PasdaSource("011", "Berks", "berks", 3, "OBJECTID"),
    PasdaSource("017", "Bucks", "bucks", 1, "OBJECTID"),
    PasdaSource("027", "Centre", "centre", 15, "OBJECTID_1"),
    PasdaSource("039", "Crawford", "crawford", 16, "OBJECTID"),
    PasdaSource("041", "Cumberland", "cumberland", 5, "OBJECTID"),
    PasdaSource(
        "045",
        "Delaware",
        "delaware",
        9,
        "OBJECTID_1",
        "rejected_conflicts_with_official_383_precinct_consolidation",
    ),
    PasdaSource("053", "Forest", "forest", 5, "OBJECTID_1"),
    PasdaSource("109", "Snyder", "snyder", 11, "OBJECTID"),
    PasdaSource("119", "Union", "union", 11, "OBJECTID"),
    PasdaSource("125", "Washington", "washington", 5, "OBJECTID_1"),
    PasdaSource("133", "York", "york", 26, "OBJECTID"),
)


def run(root: Path) -> dict[str, object]:
    """Profile every frozen PASDA source and refresh POC008 progress QA."""
    inventory_path = root / "mappings/precinct_sources_2026.csv"
    inventory = load_inventory_index(inventory_path)
    profiles = [profile_source(root, source, inventory) for source in PASDA_SOURCES]
    artifact_dir = root / "artifacts/poc008"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        artifact_dir / "pasda_candidate_audit.json",
        {
            "task": "POC008",
            "reviewed_at": "2026-08-29",
            "source_count": len(profiles),
            "registered_candidate_count": sum(
                profile["disposition"] == "registered_candidate" for profile in profiles
            ),
            "rejected_source_count": sum(
                profile["disposition"] != "registered_candidate" for profile in profiles
            ),
            "sources": profiles,
        },
    )
    qa = write_qa(inventory_path, artifact_dir / "inventory_qa.json")
    return {
        "source_count": len(profiles),
        "registered_candidate_count": 11,
        "rejected_source_count": 1,
        "inventory": qa.as_dict(),
    }


def load_inventory_index(path: Path) -> dict[str, dict[str, str]]:
    """Load the tracked inventory keyed by zero-padded county FIPS."""
    with path.open(newline="", encoding="utf-8") as source:
        return {row["county_fips"]: row for row in csv.DictReader(source)}


def profile_source(
    root: Path,
    source: PasdaSource,
    inventory: dict[str, dict[str, str]],
) -> dict[str, object]:
    """Return provenance and schema diagnostics for one frozen layer."""
    geojson_path = root / source.geojson_path
    metadata_path = root / source.metadata_path
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    frame = gpd.read_file(geojson_path)
    digest = sha256(geojson_path)
    if source.disposition == "registered_candidate":
        validate_registered_candidate(
            source, inventory[source.county_fips], digest, len(frame)
        )
    return {
        "county_fips": source.county_fips,
        "county_name": source.county_name,
        "producer": metadata.get("copyrightText")
        or f"{source.county_name} County via PASDA",
        "exact_product": metadata["name"],
        "retrieval_timestamp": datetime.fromtimestamp(
            geojson_path.stat().st_mtime, UTC
        ).isoformat(),
        "reference_vintage": None,
        "source_url": source.query_url,
        "sha256": digest,
        "metadata_sha256": sha256(metadata_path),
        "license_access": inventory[source.county_fips].get("license_access")
        or "Public PASDA service; redistribution terms require review",
        "crs": str(frame.crs),
        "schema": {
            "geometry_types": sorted(frame.geometry.geom_type.unique()),
            "property_fields": [
                column for column in frame.columns if column != "geometry"
            ],
            "feature_rows": len(frame),
            "invalid_geometries": int((~frame.geometry.is_valid).sum()),
            "empty_geometries": int(frame.geometry.is_empty.sum()),
        },
        "geographic_universe": f"{source.county_name} County precinct/voting polygons",
        "relative_path": source.geojson_path,
        "metadata_relative_path": source.metadata_path,
        "disposition": source.disposition,
    }


def validate_registered_candidate(
    source: PasdaSource,
    row: dict[str, str],
    observed_sha256: str,
    observed_rows: int,
) -> None:
    """Require the tracked candidate row to match the exact local retrieval."""
    expected = {
        "resolution_status": "candidate",
        "boundary_source_url": source.query_url,
        "sha256": observed_sha256,
        "expected_precinct_count": str(observed_rows),
    }
    mismatches = {
        field: {"expected": value, "observed": row.get(field, "")}
        for field, value in expected.items()
        if row.get(field, "") != value
    }
    if mismatches:
        raise ValueError(
            f"inventory mismatch for county {source.county_fips}: {mismatches}"
        )


def sha256(path: Path) -> str:
    """Hash one exact local retrieval."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict[str, object]) -> None:
    """Write stable, inspectable JSON."""
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run(args.root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
