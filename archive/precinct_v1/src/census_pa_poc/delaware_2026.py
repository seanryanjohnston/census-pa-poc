"""Build the Delaware County 2026 post-consolidation precinct candidate."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pdfplumber

from census_pa_poc.senate_overlay import (
    logical_geoframe_hash,
    write_immutable_geoparquet,
)
from census_pa_poc.sources import sha256
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

ACTIVE_PATTERN = re.compile(
    r"^(?P<target_precinct_id>\S+)\s+"
    r"(?P<body>.*?)\s+"
    r"(?P<school>SD\S+)\s+"
    r"(?P<municipality>MN\S+)\s+"
    r"(?P<mdj>MD\S+)\s+"
    r"(?P<house>STH\S+)\s+"
    r"(?P<senate>STS\S+)\s+"
    r"(?P<congress>\d+)"
    r"(?:\s+(?P<school_region>\S+))?$"
)
ELIMINATED_PATTERN = re.compile(r"^(?P<source_precinct_id>\S+-1) ELIMINATED$")

METHOD_ID = "delaware_official_consolidation_dissolve_v1"
OFFICIAL_LIST_URL = (
    "https://www.delcopa.gov/sites/default/files/2026-01/"
    "2026-List-of-Delaware-County-Precincts-after-consolidations.pdf"
)
CONSOLIDATION_URL = (
    "https://www.delcopa.gov/sites/default/files/2026-02/"
    "2026-Precinct-Consolidation-Overview-and-Maps-2-19-2026.pdf"
)
PASDA_URL = (
    "https://maps.pasda.psu.edu/ArcGIS/rest/services/pasda/"
    "DelawareCounty/MapServer/9/query?where=1%3D1&outFields=*"
    "&returnGeometry=true&outSR=4269&orderByFields=OBJECTID_1&f=geojson"
)


def load_official_precinct_list(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse the official post-consolidation table into active/eliminated rows."""
    active = []
    eliminated = []
    unparsed_data_lines = []
    with pdfplumber.open(path) as document:
        for page in document.pages:
            for raw_line in (
                page.extract_text(x_tolerance=1, y_tolerance=3) or ""
            ).splitlines():
                line = " ".join(raw_line.split())
                if match := ELIMINATED_PATTERN.match(line):
                    eliminated.append(match.groupdict())
                elif match := ACTIVE_PATTERN.match(line):
                    active.append(split_official_body(match.groupdict()))
                elif re.match(r"^\S+-1\s", line):
                    unparsed_data_lines.append(line)
    if unparsed_data_lines:
        raise ValueError(f"Unparsed official precinct rows: {unparsed_data_lines}")
    return (
        pd.DataFrame(active).sort_values("target_precinct_id").reset_index(drop=True),
        pd.DataFrame(eliminated)
        .sort_values("source_precinct_id")
        .reset_index(drop=True),
    )


def split_official_body(row: dict[str, str | None]) -> dict[str, str | None]:
    """Separate the active precinct name from its optional previous-unit rule."""
    body = str(row.pop("body"))
    if " Prev." not in body:
        return {**row, "precinct_name": body, "previous_expression": None}
    name, previous = body.split(" Prev.", 1)
    return {
        **row,
        "precinct_name": name,
        "previous_expression": previous.strip(),
    }


def canonicalize_pasda_source(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Correct four evidenced ID defects while retaining the unnamed exception."""
    result = frame.copy()
    corrections = [canonical_source_id(row) for row in result.itertuples(index=False)]
    result["source_precinct_id"] = pd.Series(
        [value for value, _ in corrections], dtype="string"
    )
    result["identifier_diagnostic"] = [diagnostic for _, diagnostic in corrections]
    return result


def canonical_source_id(row: object) -> tuple[str | None, str]:
    """Return the canonical old ID and an explicit correction diagnostic."""
    source_id = "".join(str(getattr(row, "precinctid", "")).split())
    name = normalize_name(str(getattr(row, "name", "")))
    if not source_id:
        return None, "missing_source_identifier"
    if source_id == "010000W-1":
        return "0100000W-1", "pad_aldan_west_identifier"
    if source_id == "14001001-1" and "PRECINCT 2" in name:
        return "14001002-1", "repair_darby_ward_1_precinct_2_identifier"
    if source_id == "14002001-1" and "PRECINCT 2" in name:
        return "14002002-1", "repair_darby_ward_2_precinct_2_identifier"
    if source_id != str(getattr(row, "precinctid", "")):
        return source_id, "remove_identifier_whitespace"
    return source_id, "unchanged"


def normalize_name(value: str) -> str:
    return " ".join(value.upper().replace(",", " ").split())


def build_consolidation_crosswalk(
    active: pd.DataFrame,
    source_ids: set[str],
) -> pd.DataFrame:
    """Map every old precinct exactly once using the official Previous column."""
    rows = []
    for record in active.to_dict("records"):
        target = str(record["target_precinct_id"])
        previous = record["previous_expression"]
        for source_id in source_ids_for_record(target, previous, source_ids):
            rows.append(
                {
                    "source_precinct_id": source_id,
                    "target_precinct_id": target,
                    "weight": 1.0,
                    "method_id": METHOD_ID,
                    "source_vintage": "PASDA Delaware Voting Areas 202601 label; effective date unproven",
                    "target_vintage": "2026 primary and later",
                    "weighting_universe": "official whole-precinct consolidation/renumbering",
                    "previous_expression": previous,
                    "nearest_assignment": False,
                }
            )
    crosswalk = (
        pd.DataFrame(rows).sort_values("source_precinct_id").reset_index(drop=True)
    )
    duplicated = crosswalk["source_precinct_id"].duplicated(keep=False)
    if duplicated.any():
        raise ValueError(
            "Old precincts mapped more than once: "
            f"{crosswalk.loc[duplicated, 'source_precinct_id'].tolist()}"
        )
    observed = set(crosswalk["source_precinct_id"])
    if observed != source_ids:
        raise ValueError(
            f"Old precinct mapping mismatch: missing={sorted(source_ids - observed)}, "
            f"unexpected={sorted(observed - source_ids)}"
        )
    return crosswalk


def source_ids_for_record(
    target_id: str,
    previous_expression: object,
    source_ids: set[str],
) -> list[str]:
    """Resolve one official Previous expression to canonical old precinct IDs."""
    if pd.isna(previous_expression):
        return [target_id]
    municipality = target_id[:2]
    tokens = [
        token.strip()
        for token in re.split(r"\s*&\s*|\s*,\s*", str(previous_expression))
    ]
    return [source_id_for_token(municipality, token, source_ids) for token in tokens]


def source_id_for_token(
    municipality: str,
    token: str,
    source_ids: set[str],
) -> str:
    """Resolve numeric, ward-precinct, or named prior-unit notation."""
    if "-" in token:
        ward, precinct = token.split("-", 1)
        return f"{municipality}{ward.zfill(3)}{precinct.zfill(3)}-1"
    if token.isdigit():
        return f"{municipality}000{token.zfill(3)}-1"
    matches = sorted(
        source_id
        for source_id in source_ids
        if source_id.startswith(municipality)
        and source_id.removesuffix("-1").endswith(token)
    )
    if len(matches) != 1:
        raise ValueError(
            f"Expected one named old precinct for {municipality}/{token}; found {matches}"
        )
    return matches[0]


def build_target_geometry(
    source: gpd.GeoDataFrame,
    crosswalk: pd.DataFrame,
    active: pd.DataFrame,
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Dissolve named old polygons; return the unnamed feature separately."""
    unassigned = source[source["source_precinct_id"].isna()].copy()
    named = source[source["source_precinct_id"].notna()].copy()
    named = named.merge(
        crosswalk[["source_precinct_id", "target_precinct_id"]],
        on="source_precinct_id",
        how="left",
        validate="many_to_one",
    )
    if named["target_precinct_id"].isna().any():
        raise ValueError("Named source feature missing consolidation target")
    geometry = named[["target_precinct_id", "geometry"]].dissolve(
        by="target_precinct_id", as_index=False
    )
    attributes = active.drop(columns=["previous_expression"])
    target = geometry.merge(
        attributes,
        on="target_precinct_id",
        how="left",
        validate="one_to_one",
    )
    target["method_id"] = METHOD_ID
    target["nearest_assignment_count"] = 0
    return gpd.GeoDataFrame(target, geometry="geometry", crs=source.crs), unassigned


def run(root: Path) -> dict[str, object]:
    """Execute and save the Delaware 2026 candidate reconstruction."""
    raw_dir = root / "data/raw"
    official_path = (
        raw_dir
        / "delaware_2026_precinct_consolidations/precinct_list_after_consolidations.pdf"
    )
    consolidation_path = (
        raw_dir
        / "delaware_2026_precinct_consolidations/consolidation_overview_maps.pdf"
    )
    pasda_path = raw_dir / "poc008_pasda_2026_candidates/045_delaware_precincts.geojson"
    active, eliminated = load_official_precinct_list(official_path)
    source = canonicalize_pasda_source(gpd.read_file(pasda_path))
    source_ids = set(source["source_precinct_id"].dropna())
    crosswalk = build_consolidation_crosswalk(active, source_ids)
    target, unassigned = build_target_geometry(source, crosswalk, active)
    unassigned_area = float(unassigned.to_crs(5070).geometry.area.sum())
    checks = build_checks(active, eliminated, source, crosswalk, target, unassigned)
    qa = {
        "task": "POC008",
        "county_fips": "045",
        "county_name": "Delaware",
        "passed": all_pass(checks),
        "qualified_2026_target": False,
        "checks": checks,
        "diagnostics": {
            "unassigned_feature_rows": len(unassigned),
            "unassigned_area_square_meters": unassigned_area,
            "unassigned_legislative_attributes": unassigned[
                ["Leg", "Senate", "Congress"]
            ].to_dict("records"),
            "nearest_assignment_count": 0,
            "qualification_blockers": [
                "one material source polygon lacks a precinct identifier",
                "PASDA publication label does not prove November 3 2026 effectiveness",
                "the statewide operational cutoff has not yet been met",
            ],
        },
        "hashes": {
            "crosswalk": logical_frame_hash(crosswalk, ["source_precinct_id"]),
            "target_geometry": logical_geoframe_hash(target, ["target_precinct_id"]),
        },
    }
    if not qa["passed"]:
        raise RuntimeError("Delaware 2026 candidate QA failed")
    processed_dir = root / "data/processed/poc008"
    crosswalk_status = write_immutable_parquet(
        crosswalk,
        processed_dir / "delaware_old_to_2026_precinct_v1.parquet",
        ["source_precinct_id"],
    )
    target_status = write_immutable_geoparquet(
        target,
        processed_dir / "delaware_2026_precinct_candidate_v1.parquet",
        ["target_precinct_id"],
    )
    artifact_dir = root / "artifacts/poc008"
    write_json(artifact_dir / "delaware_2026_candidate_qa.json", qa)
    write_json(
        artifact_dir / "delaware_2026_candidate_input_manifest.json",
        build_manifest(official_path, consolidation_path, pasda_path),
    )
    (artifact_dir / "delaware_2026_candidate_report.md").write_text(
        render_report(qa, crosswalk_status, target_status)
    )
    return {
        **qa,
        "artifact_writes": {"crosswalk": crosswalk_status, "target": target_status},
    }


def build_checks(
    active: pd.DataFrame,
    eliminated: pd.DataFrame,
    source: gpd.GeoDataFrame,
    crosswalk: pd.DataFrame,
    target: gpd.GeoDataFrame,
    unassigned: gpd.GeoDataFrame,
) -> list[dict[str, object]]:
    """Return explicit candidate reconstruction checks."""
    named = source[source["source_precinct_id"].notna()]
    return [
        check("official_active_precincts", len(active) == 383, len(active)),
        check("official_eliminated_precincts", len(eliminated) == 45, len(eliminated)),
        check(
            "official_total_rows",
            len(active) + len(eliminated) == 428,
            len(active) + len(eliminated),
        ),
        check(
            "official_ids_unique",
            active["target_precinct_id"].nunique() == 383,
            active["target_precinct_id"].nunique(),
        ),
        check(
            "official_assignments_complete",
            not active[["house", "senate", "congress"]].isna().any().any(),
            active[["house", "senate", "congress"]].isna().sum().to_dict(),
        ),
        check("pasda_feature_rows", len(source) == 434, len(source)),
        check(
            "pasda_named_source_units",
            named["source_precinct_id"].nunique() == 428,
            named["source_precinct_id"].nunique(),
        ),
        check(
            "all_named_sources_mapped_once",
            len(crosswalk) == 428 and crosswalk["source_precinct_id"].nunique() == 428,
            len(crosswalk),
        ),
        check(
            "all_official_targets_built",
            len(target) == 383 and target["target_precinct_id"].nunique() == 383,
            len(target),
        ),
        check(
            "target_geometry_valid",
            bool(target.geometry.is_valid.all()),
            int((~target.geometry.is_valid).sum()),
        ),
        check(
            "target_geometry_nonempty",
            bool((~target.geometry.is_empty).all()),
            int(target.geometry.is_empty.sum()),
        ),
        check(
            "unnamed_exception_typed",
            len(unassigned) == 1
            and unassigned["identifier_diagnostic"]
            .eq("missing_source_identifier")
            .all(),
            len(unassigned),
        ),
        check(
            "no_nearest_assignment",
            crosswalk["nearest_assignment"].eq(False).all(),
            int(crosswalk["nearest_assignment"].sum()),
        ),
    ]


def build_manifest(
    official_path: Path,
    consolidation_path: Path,
    pasda_path: Path,
) -> dict[str, object]:
    return {
        "task": "POC008",
        "created_at": datetime.now(UTC).isoformat(),
        "sources": [
            manifest_entry(
                official_path,
                "Delaware County Elections Department",
                "2026 List of Delaware County Precincts after consolidations",
                "2026 primary and later",
                OFFICIAL_LIST_URL,
                "12-page PDF table; 383 active and 45 eliminated rows",
            ),
            manifest_entry(
                consolidation_path,
                "Delaware County Board of Elections and Delaware County GIS",
                "2026 Precinct Consolidation Overview and Maps",
                "2026 primary and later",
                CONSOLIDATION_URL,
                "46-page PDF with official consolidation maps and effective-date evidence",
            ),
            manifest_entry(
                pasda_path,
                "Delaware County via PASDA",
                "Delaware County Voting Areas 202601",
                "not established",
                PASDA_URL,
                "434 EPSG:4269 polygon features; one unnamed feature",
                crs="EPSG:4269",
            ),
        ],
    }


def manifest_entry(
    path: Path,
    producer: str,
    product: str,
    reference_vintage: str,
    url: str,
    schema: str,
    crs: str | None = None,
) -> dict[str, object]:
    return {
        "producer": producer,
        "exact_product": product,
        "retrieval_timestamp": datetime.fromtimestamp(
            path.stat().st_mtime, UTC
        ).isoformat(),
        "reference_vintage": reference_vintage,
        "source_url": url,
        "sha256": sha256(path),
        "license_access": "Public official county/PASDA source; redistribution terms require review",
        "crs": crs,
        "schema": schema,
        "geographic_universe": "Delaware County election precincts",
        "relative_path": data_raw_relative_path(path),
    }


def data_raw_relative_path(path: Path) -> str:
    """Return a stable repository-relative raw-data path for provenance."""
    parts = path.parts
    for index in range(len(parts) - 1):
        if parts[index : index + 2] == ("data", "raw"):
            return Path(*parts[index:]).as_posix()
    raise ValueError(f"Source is not under data/raw: {path}")


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(
    qa: dict[str, object], crosswalk_status: str, target_status: str
) -> str:
    return f"""# Delaware County 2026 precinct candidate

Status: **candidate reconstruction passed; not yet qualified**.

- Official active precincts: `383`
- Official eliminated precincts: `45`
- Canonical old precincts mapped: `428`
- PASDA feature rows: `434`
- Unnamed PASDA features retained as typed exceptions: `1`
- Unnamed area: `{qa["diagnostics"]["unassigned_area_square_meters"]:.3f}` m²
- Nearest assignments: `0`
- Crosswalk artifact: `{crosswalk_status}`
- Target artifact: `{target_status}`
- Crosswalk logical SHA-256: `{qa["hashes"]["crosswalk"]}`
- Target logical SHA-256: `{qa["hashes"]["target_geometry"]}`

The official table maps every one of the 428 named old precincts exactly once
to 383 post-consolidation precincts and supplies complete House, Senate, and
congressional assignments. The candidate remains unqualified because one
material PASDA polygon has no precinct identifier, the PASDA layer label does
not prove November 3, 2026 effectiveness, and the statewide cutoff has not yet
been met. No nearest or adjacency assignment is made.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(json.dumps(run(args.root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
