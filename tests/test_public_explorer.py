from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = ROOT / "site"
RELEASE_ROOT = SITE_ROOT / "data" / "releases" / "poc039-v2"
PANELS = (
    (
        "pa_house_district_election_features_v2.csv",
        3_654,
        "46d7260b42bd52b45c3d271f28ca1d45a0e0b9a99c48d8bf87a3a857a9bc2e55",
    ),
    (
        "pa_senate_district_election_features_v2.csv",
        900,
        "59641c43353ed1a295119428a4b62f75af4269be97e13dfa3a6341aaedbdbe58",
    ),
)
GEOMETRY_SUFFIXES = {".geojson", ".gpkg", ".kml", ".parquet", ".shp"}


def test_published_panels_retain_accepted_poc039_v2_identities() -> None:
    for filename, expected_rows, expected_sha256 in PANELS:
        path = RELEASE_ROOT / filename
        with path.open(newline="", encoding="utf-8") as handle:
            rows = csv.reader(handle)
            header = next(rows)
            row_count = sum(1 for _ in rows)

        assert len(header) == 95
        assert row_count == expected_rows
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256


def test_release_stays_inside_declared_size_and_content_boundary() -> None:
    files = [path for path in RELEASE_ROOT.rglob("*") if path.is_file()]
    total_bytes = sum(path.stat().st_size for path in files)

    assert total_bytes < 6 * 1_024 * 1_024
    assert not any(path.suffix.lower() in GEOMETRY_SUFFIXES for path in files)

    release = json.loads((RELEASE_ROOT / "release.json").read_text())
    assert release["release_id"] == "poc039-v2"
    assert "legislative-plan geometry" in release["excluded"]
    assert release["sensitivity_review"]
    assert release["reuse_notice"]


def test_explorer_defaults_to_2026_and_links_versioned_release_files() -> None:
    app = (SITE_ROOT / "app.js").read_text()
    page = (SITE_ROOT / "index.html").read_text()

    assert 'const RELEASE_PATH = "data/releases/poc039-v2"' in app
    assert "year: 2026" in app
    assert 'class="plan-bridge"' in app
    assert "bindTrendTooltips(history, metric)" in app
    assert 'class="plan-marker"' not in app
    assert "1992–2026" in page
    assert 'id="plan-legend"' in page
    assert "pa_house_district_election_features_v2.csv" in page
    assert "pa_senate_district_election_features_v2.csv" in page
    assert '<script src="http' not in page
    assert "github.com/seanryanjohnston/census-pa-poc" in page
