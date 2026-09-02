"""Profile the official State Senate plan inputs for POC022."""

from __future__ import annotations

import argparse
import csv
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import shapely

from census_pa_poc.sources import sha256, vsi_zip_member
from census_pa_poc.validation import all_pass, write_json

EXPECTED_DISTRICTS = set(range(1, 51))
TOPOLOGY_TOLERANCE_SQUARE_METERS = 1.0

PLAN_SOURCES = {
    "pa_senate_1981_plan": {
        "producer": "Pennsylvania Legislative Reapportionment Commission",
        "product": "1981 State Senate district plan SHAPE",
        "reference_vintage": "1981",
        "effective_vintage": "used for the 1990 election within POC scope",
        "url": "https://www.redistricting.state.pa.us/Resources/GISData/Districts/Legislative/Senate/1981/SHAPE/1981SenateDistrictShapeFile.zip",
        "sha256": "f12d88b92ad5c63ee00038ca92d294df1d1e9eee6091bcc0889384148b6f0388",
        "relative_path": (
            "data/raw/pa_senate_plans/1981/1981SenateDistrictShapeFile.zip"
        ),
        "member": "1981SenateDistrictShapeFile.shp",
        "district_field": "District_1",
    },
    "pa_senate_1991_final": {
        "producer": "Pennsylvania Legislative Reapportionment Commission",
        "product": "1991 Final State Senate district plan SHAPE",
        "reference_vintage": "1991",
        "effective_vintage": "used for 1992-2000 elections",
        "url": "https://www.redistricting.state.pa.us/Resources/GISData/Districts/Legislative/Senate/1991/SHAPE/PA-Senate-Districts-1991.zip",
        "sha256": "f7dd6a06d3ce24aafa5addce2fddc9772664fa6358cd6f85cc6e00afc9a87e6f",
        "relative_path": (
            "data/raw/pa_senate_plans/1991/PA-Senate-Districts-1991.zip"
        ),
        "member": "1991SenateDistrictShapeFile.shp",
        "district_field": "District_1",
    },
    "pa_senate_2001_final": {
        "producer": "Pennsylvania Legislative Reapportionment Commission",
        "product": "2001 Final State Senate district plan SHAPE",
        "reference_vintage": "2001",
        "effective_vintage": "used for 2002-2012 elections",
        "url": "https://www.redistricting.state.pa.us/Resources/GISData/Districts/Legislative/Senate/2001/SHAPE/PA-Senate-Districts-2001.zip",
        "sha256": "01319695d77d9ad1d787549332e8d3f236cae9510411a9cc7d9e538c500b17d4",
        "relative_path": (
            "data/raw/pa_senate_plans/2001/PA-Senate-Districts-2001.zip"
        ),
        "member": "2001SenateDistrictShapeFile.shp",
        "district_field": "District_1",
    },
    "pa_senate_2012_revised_final": {
        "producer": "Pennsylvania Legislative Reapportionment Commission",
        "product": "2012 Revised Final State Senate district plan SHAPE",
        "reference_vintage": "2012",
        "effective_vintage": "used for 2014-2020 elections",
        "url": "https://www.redistricting.state.pa.us/Resources/GISData/Districts/Legislative/senate/2011-Revised-final/SHAPE/FinalSenatePlan2012.zip",
        "sha256": "801da910909aea05be2201b755fcaa0fd3f890d9b438ace641250f4037105b04",
        "relative_path": (
            "data/raw/pa_senate_plans/2012_revised_final/FinalSenatePlan2012.zip"
        ),
        "member": "FinalSenatePlan2012.shp",
        "district_field": "District_1",
    },
    "pa_senate_2021_final": {
        "producer": "Pennsylvania Legislative Reapportionment Commission",
        "product": "2021 Final State Senate district plan SHAPE",
        "reference_vintage": "2021",
        "effective_vintage": "used for 2022-2026 elections",
        "url": "https://www.redistricting.state.pa.us/Resources/GISData/Districts/Legislative/Senate/2021-Final/SHAPE/2022%20LRC-Senate-Final.zip",
        "sha256": "4dcfd5f111ddf7de58484585205ecc5b01631e4a1b20c0745889f741ec137e14",
        "relative_path": (
            "data/raw/pa_senate_plans/2021_final/2022 LRC-Senate-Final.zip"
        ),
        "member": "2022 LRC-Senate-Final.shp",
        "district_field": "DISTRICT",
    },
}

SUPPORTING_SOURCES = {
    "pa_senate_2012_revised_final_kml": {
        "producer": "Pennsylvania Legislative Reapportionment Commission",
        "product": "2012 Revised Final State Senate district plan KML",
        "reference_vintage": "2012",
        "effective_vintage": "used for 2014-2020 elections",
        "url": "https://www.redistricting.state.pa.us/Resources/GISData/Districts/Legislative/senate/2011-Revised-final/KML/FinalSenatePlan2012.kml.zip",
        "sha256": "a74c005840f2a059841039be1e33a01391258730fd5006e30c26799a6129af51",
        "relative_path": (
            "data/raw/pa_senate_plans/2012_revised_final/"
            "FinalSenatePlan2012.kml.zip"
        ),
        "member": "FinalSenatePlan2012.kml",
    }
}

LRC_SOURCE = {
    "source_id": "pa_lrc_2021_release_1b_geography",
    "producer": "Pennsylvania Legislative Reapportionment Commission",
    "product": "2021-10-05 LRC Data Release No. 1b Data Set 1 geography",
    "reference_vintage": "2020",
    "effective_vintage": "2021-10-05",
    "url": "https://www.redistricting.state.pa.us/resources/GISData/Census/2021/2021-DataSet1-WithoutPrisoner/2021%20LRC%20Data%20Release%201b%20-%20Geography.zip",
    "sha256": "14187001c627c6a16bf967415059408c4ef7007d366fd9105b5be30763250e3b",
    "relative_path": (
        "data/raw/pa_lrc_2021_release_1b_geography/"
        "2021 LRC Data Release 1b - Geography.zip"
    ),
}


def run(root: Path) -> dict[str, object]:
    """Freeze, validate, and profile the five official plan archives."""
    root = root.resolve()
    artifact_dir = root / "artifacts/work/poc022"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    require_manifest_hashes(manifest)

    lrc_archive = root / LRC_SOURCE["relative_path"]
    precincts = gpd.read_file(
        vsi_zip_member(lrc_archive, "Geography/WP_VotingDistricts.shp"),
        columns=["GEOID20"],
    )
    blocks = gpd.read_file(
        vsi_zip_member(lrc_archive, "Geography/WP_Blocks.shp"),
        columns=["GEOID20", "P0010001"],
    )

    profiles = {}
    source_checks = []
    for source_id, source in PLAN_SOURCES.items():
        plan = load_plan(root, source)
        repaired, invalid_before = repair_plan_geometry(plan)
        profile = profile_plan(
            source_id,
            repaired,
            invalid_before,
            precincts,
            blocks,
        )
        profiles[source_id] = profile
        source_checks.extend(source_profile_checks(profile))

    kml_profile = profile_supporting_kml(root)
    mapping_checks = validate_cycle_mapping(root, set(PLAN_SOURCES))
    topology_checks = topology_readiness_checks(profiles, kml_profile)
    source_gate_passed = all_pass(source_checks) and all_pass(mapping_checks)
    overlay_ready = all_pass(topology_checks)

    qa = {
        "task": "POC022",
        "source_gate_passed": source_gate_passed,
        "overlay_ready": overlay_ready,
        "task_complete": source_gate_passed and overlay_ready,
        "source_checks": source_checks,
        "mapping_checks": mapping_checks,
        "topology_readiness_checks": topology_checks,
        "next_action": (
            "Adopt and test a non-nearest topology completion rule for historical "
            "state-line gaps and resolve the official 2012 District 1/8 overlap."
        ),
    }
    write_json(artifact_dir / "source_profiles.json", profiles)
    write_json(artifact_dir / "supporting_kml_profile.json", kml_profile)
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(
        render_report(qa, profiles, kml_profile)
    )
    if not source_gate_passed:
        raise RuntimeError(
            "POC022 source gate failed; inspect artifacts/work/poc022"
        )
    return qa


def load_plan(root: Path, source: dict[str, str]) -> gpd.GeoDataFrame:
    path = root / source["relative_path"]
    plan = gpd.read_file(vsi_zip_member(path, source["member"]))
    district = plan[source["district_field"]].astype("int64")
    return gpd.GeoDataFrame(
        {"senate_district": district}, geometry=plan.geometry, crs=plan.crs
    )


def repair_plan_geometry(
    plan: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, int]:
    invalid_before = int((~plan.geometry.is_valid).sum())
    repaired = plan.copy()
    repaired.geometry = shapely.make_valid(repaired.geometry.array)
    return repaired, invalid_before


def profile_plan(
    source_id: str,
    plan: gpd.GeoDataFrame,
    invalid_before: int,
    precincts: gpd.GeoDataFrame,
    blocks: gpd.GeoDataFrame,
) -> dict[str, object]:
    plan_union = shapely.union_all(plan.geometry.array)
    block_points = shapely.point_on_surface(blocks.geometry.array)
    block_covered = shapely.covers(plan_union, block_points)

    plan_projected = plan.to_crs("EPSG:5070")
    precinct_projected = precincts.to_crs("EPSG:5070")
    plan_union_projected = shapely.union_all(plan_projected.geometry.array)
    precinct_union_projected = shapely.union_all(precinct_projected.geometry.array)
    overlap_area = float(
        shapely.area(plan_projected.geometry.array).sum()
        - shapely.area(plan_union_projected)
    )
    if abs(overlap_area) < 0.01:
        overlap_area = 0.0

    overlap_pairs = find_overlap_pairs(plan_projected)
    uncovered = blocks.loc[~block_covered, ["GEOID20", "P0010001"]]
    return {
        "source_id": source_id,
        "row_count": len(plan),
        "district_count": int(plan["senate_district"].nunique()),
        "district_ids": sorted(plan["senate_district"].unique().tolist()),
        "crs": plan.crs.to_string(),
        "null_or_empty_geometry_count": int(
            (plan.geometry.isna() | plan.geometry.is_empty).sum()
        ),
        "invalid_geometry_count_before_repair": invalid_before,
        "invalid_geometry_count_after_repair": int((~plan.geometry.is_valid).sum()),
        "geometry_types_after_repair": plan.geom_type.value_counts().to_dict(),
        "statewide_missing_area_square_meters": float(
            shapely.area(
                shapely.difference(precinct_union_projected, plan_union_projected)
            )
        ),
        "statewide_extra_area_square_meters": float(
            shapely.area(
                shapely.difference(plan_union_projected, precinct_union_projected)
            )
        ),
        "district_overlap_area_square_meters": overlap_area,
        "district_overlap_pairs": overlap_pairs,
        "uncovered_block_representative_point_count": len(uncovered),
        "uncovered_positive_population_fragment_count": int(
            uncovered["P0010001"].gt(0).sum()
        ),
        "uncovered_fragment_population": int(uncovered["P0010001"].sum()),
        "uncovered_fragment_ids": uncovered["GEOID20"].tolist(),
    }


def find_overlap_pairs(plan: gpd.GeoDataFrame) -> list[dict[str, object]]:
    pairs = []
    for left_index in range(len(plan)):
        for right_index in range(left_index + 1, len(plan)):
            overlap = shapely.intersection(
                plan.geometry.iloc[left_index], plan.geometry.iloc[right_index]
            )
            area = float(shapely.area(overlap))
            if area <= TOPOLOGY_TOLERANCE_SQUARE_METERS:
                continue
            pairs.append(
                {
                    "left_district": int(plan["senate_district"].iloc[left_index]),
                    "right_district": int(plan["senate_district"].iloc[right_index]),
                    "area_square_meters": area,
                }
            )
    return pairs


def source_profile_checks(profile: dict[str, object]) -> list[dict[str, object]]:
    source_id = profile["source_id"]
    return [
        check(
            f"{source_id}:district_count",
            profile["district_count"] == 50 and profile["row_count"] == 50,
            {
                "rows": profile["row_count"],
                "districts": profile["district_count"],
            },
        ),
        check(
            f"{source_id}:district_ids",
            set(profile["district_ids"]) == EXPECTED_DISTRICTS,
            profile["district_ids"],
        ),
        check(f"{source_id}:crs", profile["crs"] == "EPSG:4269", profile["crs"]),
        check(
            f"{source_id}:geometry_present",
            profile["null_or_empty_geometry_count"] == 0,
            profile["null_or_empty_geometry_count"],
        ),
        check(
            f"{source_id}:geometry_valid_after_recorded_repair",
            profile["invalid_geometry_count_after_repair"] == 0,
            {
                "before": profile["invalid_geometry_count_before_repair"],
                "after": profile["invalid_geometry_count_after_repair"],
            },
        ),
    ]


def topology_readiness_checks(
    profiles: dict[str, dict[str, object]],
    kml_profile: dict[str, object],
) -> list[dict[str, object]]:
    checks = []
    for source_id, profile in profiles.items():
        checks.extend(
            [
                check(
                    f"{source_id}:no_populated_uncovered_representative_points",
                    profile["uncovered_fragment_population"] == 0,
                    {
                        "fragments": profile[
                            "uncovered_block_representative_point_count"
                        ],
                        "positive_fragments": profile[
                            "uncovered_positive_population_fragment_count"
                        ],
                        "population": profile["uncovered_fragment_population"],
                    },
                ),
                check(
                    f"{source_id}:no_material_district_overlap",
                    profile["district_overlap_area_square_meters"]
                    <= TOPOLOGY_TOLERANCE_SQUARE_METERS,
                    {
                        "area_square_meters": profile[
                            "district_overlap_area_square_meters"
                        ],
                        "pairs": profile["district_overlap_pairs"],
                    },
                ),
            ]
        )
    checks.append(
        check(
            "2012_kml_confirms_shape_overlap",
            kml_profile["district_overlap_area_square_meters"]
            > TOPOLOGY_TOLERANCE_SQUARE_METERS,
            kml_profile["district_overlap_area_square_meters"],
        )
    )
    return checks


def profile_supporting_kml(root: Path) -> dict[str, object]:
    source = SUPPORTING_SOURCES["pa_senate_2012_revised_final_kml"]
    path = root / source["relative_path"]
    plan = gpd.read_file(vsi_zip_member(path, source["member"]))
    district = plan["Name"].str.extract(r"(\d+)", expand=False).astype("int64")
    normalized = gpd.GeoDataFrame(
        {"senate_district": district}, geometry=plan.geometry, crs=plan.crs
    ).to_crs("EPSG:5070")
    overlap_area = float(
        shapely.area(normalized.geometry.array).sum()
        - shapely.area(shapely.union_all(normalized.geometry.array))
    )
    return {
        "source_id": "pa_senate_2012_revised_final_kml",
        "row_count": len(normalized),
        "district_count": int(normalized["senate_district"].nunique()),
        "district_overlap_area_square_meters": overlap_area,
        "district_overlap_pairs": find_overlap_pairs(normalized),
    }


def validate_cycle_mapping(
    root: Path, known_plan_ids: set[str]
) -> list[dict[str, object]]:
    with (root / "mappings/election_cycles.csv").open(newline="") as source:
        cycles = list(csv.DictReader(source))
    observed_plan_ids = {row["senate_plan_id"] for row in cycles}
    election_ids = {row["election_id"] for row in cycles}
    return [
        check("cycle_count", len(cycles) == 19, len(cycles)),
        check(
            "cycle_ids_unique", len(election_ids) == len(cycles), len(election_ids)
        ),
        check(
            "all_cycle_plan_ids_known",
            observed_plan_ids == known_plan_ids,
            {
                "unknown": sorted(observed_plan_ids - known_plan_ids),
                "unused": sorted(known_plan_ids - observed_plan_ids),
            },
        ),
    ]


def build_manifest(root: Path) -> dict[str, object]:
    sources = []
    source_items = [
        *[(source_id, value) for source_id, value in PLAN_SOURCES.items()],
        *[(source_id, value) for source_id, value in SUPPORTING_SOURCES.items()],
        (LRC_SOURCE["source_id"], LRC_SOURCE),
    ]
    for source_id, source in source_items:
        path = root / source["relative_path"]
        sources.append(
            {
                "source_id": source_id,
                "producer": source["producer"],
                "product": source["product"],
                "reference_vintage": source["reference_vintage"],
                "effective_vintage": source["effective_vintage"],
                "url": source["url"],
                "expected_sha256": source["sha256"],
                "observed_sha256": sha256(path),
                "retrieval_timestamp": datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ).isoformat(),
                "size_bytes": path.stat().st_size,
                "license_access": (
                    "Public official download; redistribution terms not stated"
                ),
                "crs": "EPSG:4269" if source_id != "pa_senate_2012_revised_final_kml" else "EPSG:4326",
                "schema": {
                    "archive_member": source.get("member"),
                    "district_field": source.get("district_field"),
                },
                "geographic_universe": "Pennsylvania",
            }
        )
    return {"manifest_version": "1.0.0", "sources": sources}


def require_manifest_hashes(manifest: dict[str, object]) -> None:
    failures = [
        source["source_id"]
        for source in manifest["sources"]
        if source["expected_sha256"] != source["observed_sha256"]
    ]
    if failures:
        raise RuntimeError(f"Checksum mismatch: {', '.join(failures)}")


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(
    qa: dict[str, object],
    profiles: dict[str, dict[str, object]],
    kml_profile: dict[str, object],
) -> str:
    rows = []
    for source_id, profile in profiles.items():
        rows.append(
            "| "
            + " | ".join(
                [
                    source_id,
                    str(profile["invalid_geometry_count_before_repair"]),
                    f"{profile['statewide_missing_area_square_meters']:.3f}",
                    f"{profile['district_overlap_area_square_meters']:.3f}",
                    str(profile["uncovered_block_representative_point_count"]),
                    str(profile["uncovered_fragment_population"]),
                ]
            )
            + " |"
        )
    return f"""# POC022 State Senate plan source gate

Source gate: **{'PASS' if qa['source_gate_passed'] else 'FAIL'}**

Overlay ready: **{'YES' if qa['overlay_ready'] else 'NO'}**

| Plan | Invalid before repair | Fixed-target gap m² | District overlap m² | Uncovered fragment points | Uncovered fragment population |
|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

All five checksum-frozen SHAPE archives contain exactly 50 districts numbered
1–50 in EPSG:4269. The 1991 District 48 self-intersection is repaired by the
recorded `make_valid` rule.

The overlay is not yet accepted. Historical plan/state linework leaves populated
representative-point gaps (84 people in the 1991–2012 products; 87 in 1981).
The 2012 SHAPE has a {profiles['pa_senate_2012_revised_final']['district_overlap_area_square_meters']:.3f}
square-meter District 1/8 overlap, independently reproduced in the official KML
at {kml_profile['district_overlap_area_square_meters']:.3f} square meters. No
nearest-boundary repair has been applied.

Next: {qa['next_action']}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    status = "source gate passed; overlay pending" if not qa["overlay_ready"] else "passed"
    print(f"POC022 {status}")


if __name__ == "__main__":
    main()
