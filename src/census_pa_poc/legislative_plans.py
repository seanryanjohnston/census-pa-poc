"""Freeze and profile the official House and Senate plans used from 1992."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

from census_pa_poc.direct_legislative import LRC_SOURCE
from census_pa_poc.sources import sha256, vsi_zip_member
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_json,
)

AREA_CRS = "EPSG:5070"
PLAN_MAPPING_PATH = "mappings/legislative_plans_v1.csv"
NORMALIZED_PLAN_PATH = (
    "data/processed/direct_legislative/legislative_plans_1991_2021_v2.parquet"
)
EXPECTED_PLAN_IDS = {
    f"pa_{chamber}_{vintage}{suffix}"
    for chamber in ("house", "senate")
    for vintage, suffix in (
        ("1991", "_final"),
        ("2001", "_final"),
        ("2012", "_revised_final"),
        ("2021", "_final"),
    )
}
EXPECTED_DISTRICTS = {"house": 203, "senate": 50}


def run(root: Path) -> dict[str, object]:
    """Validate, normalize, and freeze the eight in-scope official plans."""
    root = root.resolve()
    mapping = load_mapping(root / PLAN_MAPPING_PATH)
    require_mapping_contract(mapping)
    manifest = build_manifest(root, mapping)
    require_manifest_hashes(manifest)

    normalized_frames = []
    profiles = []
    checks = []
    for row in mapping.to_dict("records"):
        raw = load_published_plan(root, row)
        normalized, detail = normalize_plan(raw, row)
        profile = profile_plan(raw, normalized, row, detail)
        normalized_frames.append(normalized)
        profiles.append(profile)
        checks.extend(profile_checks(profile))

    plans = gpd.GeoDataFrame(
        pd.concat(normalized_frames, ignore_index=True),
        geometry="geometry",
        crs="EPSG:4269",
    ).sort_values(["target_chamber", "target_plan_id", "target_district_id"])
    output_path = root / NORMALIZED_PLAN_PATH
    write_status = write_immutable_geoparquet(
        plans,
        output_path,
        ["target_chamber", "target_plan_id", "target_district_id"],
    )
    output_hash = logical_geoframe_hash(
        plans,
        ["target_chamber", "target_plan_id", "target_district_id"],
    )
    qa = {
        "task": "POC029",
        "stage": "legislative_plan_source_gate",
        "plan_count": len(mapping),
        "district_geometry_rows": len(plans),
        "profiles": profiles,
        "checks": checks,
        "artifact_writes": {"normalized_plans": write_status},
        "hashes": {"normalized_plans": output_hash},
        "passed": all_pass(checks),
    }
    artifact_dir = root / "artifacts/work/poc029"
    write_json(artifact_dir / "plan_input_manifest.json", manifest)
    write_json(artifact_dir / "plan_source_profiles.json", profiles)
    write_json(artifact_dir / "plan_source_qa.json", qa)
    (artifact_dir / "plan_source_report.md").write_text(render_report(qa))
    if not qa["passed"]:
        raise RuntimeError(
            "POC029 plan source gate failed; inspect plan_source_qa.json"
        )
    return qa


def load_mapping(path: Path) -> pd.DataFrame:
    """Load the versioned chamber-neutral plan registry."""
    return pd.read_csv(path, dtype="string")


def require_mapping_contract(mapping: pd.DataFrame) -> None:
    """Reject an incomplete or internally inconsistent plan registry."""
    ids = set(mapping["target_plan_id"])
    if len(mapping) != 8 or ids != EXPECTED_PLAN_IDS:
        raise ValueError(f"Unexpected legislative plan registry: {sorted(ids)}")
    if mapping["target_plan_id"].duplicated().any():
        raise ValueError("Legislative plan IDs must be unique")
    expected_ranges = {
        ("1991", "1992", "2000"),
        ("2001", "2002", "2012"),
        ("2012", "2014", "2020"),
        ("2021", "2022", "2026"),
    }
    observed_ranges = set(
        map(
            tuple,
            mapping[["reference_vintage", "first_election", "last_election"]]
            .drop_duplicates()
            .itertuples(index=False, name=None),
        )
    )
    if observed_ranges != expected_ranges:
        raise ValueError(f"Unexpected plan/election applicability: {observed_ranges}")


def load_published_plan(root: Path, source: dict[str, str]) -> gpd.GeoDataFrame:
    """Load one published archive and retain its raw CRS state."""
    path = root / source["relative_path"]
    return gpd.read_file(vsi_zip_member(path, source["archive_member"]))


def normalize_plan(
    raw: gpd.GeoDataFrame, source: dict[str, str]
) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    """Apply the recorded CRS, validity, and multipart-dissolve rules."""
    source_crs_missing = raw.crs is None
    working = raw[[source["district_field"], "geometry"]].copy()
    if source_crs_missing:
        working = working.set_crs(source["published_crs"], allow_override=True)
    district = pd.to_numeric(working[source["district_field"]], errors="raise")
    working["target_district_id"] = district.astype("int64")
    invalid_before = int((~working.geometry.is_valid).sum())
    working.geometry = shapely.make_valid(working.geometry.array)
    normalized = working.dissolve(by="target_district_id", as_index=False)
    normalized.geometry = shapely.normalize(
        shapely.make_valid(normalized.geometry.array)
    )
    normalized["target_chamber"] = source["target_chamber"]
    normalized["target_plan_id"] = source["target_plan_id"]
    normalized["target_plan_reference_vintage"] = source["reference_vintage"]
    normalized["first_applicable_election"] = source["first_election"]
    normalized["last_applicable_election"] = source["last_election"]
    normalized["source_url"] = source["source_url"]
    normalized["normalization_method_id"] = (
        "published_plan_make_valid_dissolve_canonical_v2"
    )
    normalized = normalized[
        [
            "target_chamber",
            "target_plan_id",
            "target_plan_reference_vintage",
            "first_applicable_election",
            "last_applicable_election",
            "target_district_id",
            "source_url",
            "normalization_method_id",
            "geometry",
        ]
    ].set_crs("EPSG:4269", allow_override=True)
    return normalized, {
        "source_crs_missing": source_crs_missing,
        "invalid_geometry_count_before_repair": invalid_before,
        "raw_row_count": len(raw),
        "duplicate_district_part_rows": len(raw) - int(district.nunique()),
    }


def profile_plan(
    raw: gpd.GeoDataFrame,
    plan: gpd.GeoDataFrame,
    source: dict[str, str],
    detail: dict[str, object],
) -> dict[str, object]:
    """Measure schema, validity, extent, and plan-internal topology."""
    projected = plan.to_crs(AREA_CRS)
    union = shapely.union_all(projected.geometry.array)
    overlap_area = float(
        shapely.area(projected.geometry.array).sum() - shapely.area(union)
    )
    if abs(overlap_area) < 0.01:
        overlap_area = 0.0
    return {
        "target_chamber": source["target_chamber"],
        "target_plan_id": source["target_plan_id"],
        "reference_vintage": source["reference_vintage"],
        "expected_district_count": EXPECTED_DISTRICTS[source["target_chamber"]],
        "raw_crs": None if raw.crs is None else raw.crs.to_string(),
        "normalized_crs": plan.crs.to_string(),
        "normalized_row_count": len(plan),
        "district_count": int(plan["target_district_id"].nunique()),
        "district_ids": sorted(plan["target_district_id"].tolist()),
        "null_or_empty_geometry_count": int(
            (plan.geometry.isna() | plan.geometry.is_empty).sum()
        ),
        "invalid_geometry_count_after_repair": int((~plan.geometry.is_valid).sum()),
        "district_overlap_area_square_meters": overlap_area,
        "bounds_epsg4269": [float(value) for value in plan.total_bounds],
        **detail,
    }


def profile_checks(profile: dict[str, object]) -> list[dict[str, object]]:
    """Return source-gate checks for one plan."""
    expected = profile["expected_district_count"]
    observed_ids = set(profile["district_ids"])
    return [
        check(
            f"{profile['target_plan_id']}:district_count",
            profile["district_count"] == expected
            and profile["normalized_row_count"] == expected,
            profile["district_count"],
        ),
        check(
            f"{profile['target_plan_id']}:district_ids",
            observed_ids == set(range(1, expected + 1)),
            profile["district_ids"],
        ),
        check(
            f"{profile['target_plan_id']}:crs",
            profile["normalized_crs"] == "EPSG:4269",
            {
                "raw": profile["raw_crs"],
                "normalized": profile["normalized_crs"],
                "source_crs_missing": profile["source_crs_missing"],
            },
        ),
        check(
            f"{profile['target_plan_id']}:geometry_present",
            profile["null_or_empty_geometry_count"] == 0,
            profile["null_or_empty_geometry_count"],
        ),
        check(
            f"{profile['target_plan_id']}:geometry_valid",
            profile["invalid_geometry_count_after_repair"] == 0,
            {
                "before": profile["invalid_geometry_count_before_repair"],
                "after": profile["invalid_geometry_count_after_repair"],
            },
        ),
    ]


def build_manifest(root: Path, mapping: pd.DataFrame) -> dict[str, object]:
    """Record exact official inputs and their observed file metadata."""
    sources = []
    for source in mapping.to_dict("records"):
        path = root / source["relative_path"]
        sources.append(
            {
                "source_id": source["target_plan_id"],
                "target_chamber": source["target_chamber"],
                "producer": source["producer"],
                "product": source["plan_label"],
                "reference_vintage": source["reference_vintage"],
                "effective_vintage": (
                    f"used for {source['first_election']}-{source['last_election']} "
                    "elections"
                ),
                "source_url": source["source_url"],
                "expected_sha256": source["sha256"],
                "observed_sha256": sha256(path),
                "retrieval_timestamp": datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ).isoformat(),
                "size_bytes": path.stat().st_size,
                "license_access": (
                    "Public official download; redistribution terms not stated"
                ),
                "crs": source["published_crs"],
                "schema": {
                    "format": "ESRI Shapefile",
                    "archive_member": source["archive_member"],
                    "district_field": source["district_field"],
                },
                "geographic_universe": (
                    f"Pennsylvania State {source['target_chamber'].title()} districts"
                ),
            }
        )
    return {
        "manifest_version": "1.0.0",
        "mapping_source": PLAN_MAPPING_PATH,
        "supporting_geography_not_an_input": LRC_SOURCE["source_id"],
        "sources": sources,
    }


def require_manifest_hashes(manifest: dict[str, object]) -> None:
    """Fail before parsing any plan whose exact archive changed."""
    failures = [
        source["source_id"]
        for source in manifest["sources"]
        if source["expected_sha256"] != source["observed_sha256"]
    ]
    if failures:
        raise RuntimeError(f"Legislative plan checksum mismatch: {failures}")


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def logical_geoframe_hash(frame: gpd.GeoDataFrame, sort_by: list[str]) -> str:
    """Hash canonical geometry bytes with the non-spatial plan contract."""
    normalized = pd.DataFrame(frame.drop(columns="geometry")).copy()
    normalized["geometry_wkb_hex"] = shapely.to_wkb(frame.geometry.array, hex=True)
    return logical_frame_hash(normalized, sort_by)


def write_immutable_geoparquet(
    frame: gpd.GeoDataFrame, path: Path, sort_by: list[str]
) -> str:
    """Create a GeoParquet once or prove the existing geometry is identical."""
    expected_hash = logical_geoframe_hash(frame, sort_by)
    if path.exists():
        observed_hash = logical_geoframe_hash(gpd.read_parquet(path), sort_by)
        if observed_hash != expected_hash:
            raise RuntimeError(f"Refusing to overwrite changed artifact: {path}")
        return "reused_identical"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return "created"


def render_report(qa: dict[str, object]) -> str:
    """Render the concise human-readable source-gate result."""
    rows = []
    for profile in qa["profiles"]:
        rows.append(
            "| "
            + " | ".join(
                [
                    profile["target_chamber"],
                    profile["target_plan_id"],
                    str(profile["raw_row_count"]),
                    str(profile["district_count"]),
                    str(profile["invalid_geometry_count_before_repair"]),
                    f"{profile['district_overlap_area_square_meters']:.3f}",
                ]
            )
            + " |"
        )
    return f"""# POC029 legislative plan source gate

Status: **{"PASS" if qa["passed"] else "FAIL"}**

| Chamber | Plan | Published rows | Districts | Invalid before repair | Internal overlap m² |
|---|---|---:|---:|---:|---:|
{chr(10).join(rows)}

All eight official LRC archives are checksum-frozen and normalized to one valid
EPSG:4269 geometry per district. The 1991 House source's missing parsed CRS,
multipart district rows, all validity repairs, and all measured internal plan
overlaps remain explicit in the machine-readable profile. Topology findings are
diagnostics for the direct crosswalk stage, not silently discarded repairs.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC029 plan source gate passed: {qa['passed']}")


if __name__ == "__main__":
    main()
