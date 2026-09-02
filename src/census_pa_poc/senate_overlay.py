"""Build split-aware fixed-precinct overlays for the five Senate plans."""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

from census_pa_poc.senate_plans import (
    LRC_SOURCE,
    PLAN_SOURCES,
    load_plan,
    repair_plan_geometry,
)
from census_pa_poc.sources import vsi_zip_member
from census_pa_poc.validation import all_pass, logical_frame_hash, write_json

AREA_CRS = "EPSG:5070"
MATERIAL_AREA_SQUARE_METERS = 1.0
WEIGHT_TOLERANCE = 1e-9


def run(root: Path) -> dict[str, object]:
    root = root.resolve()
    artifact_dir = root / "artifacts/work/poc022"
    processed_dir = root / "data/processed/senate_overlays"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    lrc_archive = root / LRC_SOURCE["relative_path"]
    precincts = gpd.read_file(
        vsi_zip_member(lrc_archive, "Geography/WP_VotingDistricts.shp"),
        columns=["GEOID20"],
    )
    blocks = gpd.read_file(
        vsi_zip_member(lrc_archive, "Geography/WP_Blocks.shp"),
        columns=["P0010001", "STATEFP20", "COUNTYFP20", "VTDST20"],
    )
    blocks["target_precinct_geoid"] = (
        blocks["STATEFP20"] + blocks["COUNTYFP20"] + blocks["VTDST20"]
    )

    summaries = []
    plan_checks = {}
    artifact_writes = {}
    hashes = {}
    for plan_id, source in PLAN_SOURCES.items():
        plan, _ = repair_plan_geometry(load_plan(root, source))
        overlay, diagnostics = build_precinct_plan_overlay(precincts, plan, plan_id)
        diagnostics.update(
            unresolved_population_diagnostics(blocks, plan, diagnostics)
        )
        checks = validate_overlay(overlay, diagnostics)
        plan_checks[plan_id] = checks
        summaries.append(diagnostics)
        path = processed_dir / f"{plan_id}_fixed_precinct_overlay_v3.parquet"
        artifact_writes[plan_id] = write_immutable_geoparquet(
            overlay, path, ["target_precinct_geoid", "senate_district"]
        )
        hashes[plan_id] = logical_geoframe_hash(
            overlay, ["target_precinct_geoid", "senate_district"]
        )

    summary = pd.DataFrame(summaries).sort_values("senate_plan_id")
    summary.to_csv(processed_dir / "senate_overlay_summary_v3.csv", index=False)
    passed = all(all_pass(checks) for checks in plan_checks.values())
    qa = {
        "task": "POC022",
        "method_id": "fixed_precinct_senate_overlay_v3",
        "area_crs": AREA_CRS,
        "material_area_square_meters": MATERIAL_AREA_SQUARE_METERS,
        "weight_tolerance": WEIGHT_TOLERANCE,
        "normalization_rules": [
            (
                "Remove duplicated district overlap from the district with less "
                "raw intersection area within that fixed precinct."
            ),
            (
                "Fill uncovered plan/state-line geometry only when the precinct "
                "has one material intersecting district."
            ),
            (
                "Assign sub-one-square-meter numerical gaps to the largest "
                "district intersection within the precinct."
            ),
            (
                "Leave material multi-district gaps unassigned as typed exceptions "
                "only when no uncovered LRC fragment representative point falls "
                "inside them; normalize weights over covered area."
            ),
            "Never use nearest-boundary assignment.",
        ],
        "plan_checks": plan_checks,
        "artifact_writes": artifact_writes,
        "hashes": hashes,
        "passed": passed,
    }
    write_json(artifact_dir / "overlay_qa_results.json", qa)
    (artifact_dir / "overlay_report.md").write_text(render_report(qa, summary))
    if not passed:
        raise RuntimeError("POC022 overlay QA failed; inspect overlay_qa_results.json")
    return qa


def build_precinct_plan_overlay(
    precincts: gpd.GeoDataFrame,
    plan: gpd.GeoDataFrame,
    plan_id: str,
) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    fixed = precincts[["GEOID20", "geometry"]].rename(
        columns={"GEOID20": "target_precinct_geoid"}
    ).to_crs(AREA_CRS)
    senate = plan[["senate_district", "geometry"]].to_crs(AREA_CRS)
    raw = gpd.overlay(fixed, senate, how="intersection", keep_geom_type=True)
    raw = raw[~raw.geometry.is_empty].copy()
    raw["raw_area_square_meters"] = raw.geometry.area

    precinct_geometry = fixed.set_index("target_precinct_geoid").geometry
    rows = []
    unresolved = []
    for precinct_id, group in raw.groupby("target_precinct_geoid", sort=True):
        normalized, issue = normalize_precinct_fragments(
            precinct_id,
            precinct_geometry.loc[precinct_id],
            group,
        )
        rows.extend(normalized)
        if issue is not None:
            unresolved.append(issue)

    result = gpd.GeoDataFrame(rows, geometry="geometry", crs=AREA_CRS)
    result["senate_plan_id"] = plan_id
    result["source_precinct_dataset_id"] = "pa_lrc_2021_release_1b_geography"
    result["source_precinct_effective_vintage"] = "2021-10-05"
    result["target_senate_plan_reference_vintage"] = PLAN_SOURCES.get(
        plan_id, {"reference_vintage": "fixture"}
    )["reference_vintage"]
    result["method_id"] = "fixed_precinct_senate_overlay_v3"
    result["weighting_universe"] = "EPSG:5070 fixed precinct polygon area"
    result["assignment_status"] = "assigned"
    result["nearest_assignment_used"] = False
    result = result[
        [
            "senate_plan_id",
            "source_precinct_dataset_id",
            "source_precinct_effective_vintage",
            "target_senate_plan_reference_vintage",
            "target_precinct_geoid",
            "senate_district",
            "area_weight",
            "fragment_area_square_meters",
            "precinct_area_square_meters",
            "coverage_ratio",
            "raw_area_square_meters",
            "overlap_removed_square_meters",
            "gap_added_square_meters",
            "normalization_status",
            "method_id",
            "weighting_universe",
            "assignment_status",
            "nearest_assignment_used",
            "geometry",
        ]
    ].sort_values(["target_precinct_geoid", "senate_district"])

    target_counts = result.groupby("target_precinct_geoid")[
        "senate_district"
    ].nunique()
    diagnostics = {
        "senate_plan_id": plan_id,
        "allocation_rows": len(result),
        "precinct_count": int(result["target_precinct_geoid"].nunique()),
        "senate_district_count": int(result["senate_district"].nunique()),
        "split_precinct_count": int(target_counts.gt(1).sum()),
        "max_districts_per_precinct": int(target_counts.max()),
        "overlap_removed_square_meters": float(
            result["overlap_removed_square_meters"].sum()
        ),
        "gap_added_square_meters": float(result["gap_added_square_meters"].sum()),
        "gap_filled_precinct_count": int(result["gap_added_square_meters"].gt(0).sum()),
        "unresolved_precinct_count": len(unresolved),
        "unresolved_precincts": unresolved,
        "unresolved_gap_area_square_meters": float(
            sum(issue["gap_area_square_meters"] for issue in unresolved)
        ),
        "nearest_assignment_count": int(result["nearest_assignment_used"].sum()),
    }
    return result, diagnostics


def normalize_precinct_fragments(
    precinct_id: str,
    precinct_geometry,
    raw_group: gpd.GeoDataFrame,
) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    by_district = {
        int(district): shapely.union_all(group.geometry.array)
        for district, group in raw_group.groupby("senate_district")
    }
    raw_areas = {
        district: float(shapely.area(geometry))
        for district, geometry in by_district.items()
    }
    overlap_removed = {district: 0.0 for district in by_district}
    gap_added = {district: 0.0 for district in by_district}
    statuses = {district: set() for district in by_district}

    material_districts = [
        district
        for district, area in raw_areas.items()
        if area > MATERIAL_AREA_SQUARE_METERS
    ]
    if material_districts:
        for district in set(by_district) - set(material_districts):
            statuses[district].add("numerical_sliver_removed")
            by_district.pop(district)

    districts = sorted(by_district)
    for left_index, left in enumerate(districts):
        for right in districts[left_index + 1 :]:
            overlap = shapely.intersection(by_district[left], by_district[right])
            overlap_area = float(shapely.area(overlap))
            if overlap_area <= MATERIAL_AREA_SQUARE_METERS:
                continue
            loser = choose_overlap_loser(left, right, raw_areas)
            by_district[loser] = shapely.difference(by_district[loser], overlap)
            overlap_removed[loser] += overlap_area
            statuses[loser].add("district_overlap_removed")

    by_district = {
        district: geometry
        for district, geometry in by_district.items()
        if not shapely.is_empty(geometry)
    }
    covered = shapely.union_all(list(by_district.values()))
    gap = shapely.difference(precinct_geometry, covered)
    gap_area = float(shapely.area(gap))
    issue = None
    if gap_area > 0:
        material_districts = [
            district
            for district, geometry in by_district.items()
            if shapely.area(geometry) > MATERIAL_AREA_SQUARE_METERS
        ]
        recipient = choose_gap_recipient(
            by_district, material_districts, gap_area
        )
        if recipient is None:
            issue = {
                "target_precinct_geoid": precinct_id,
                "gap_area_square_meters": gap_area,
                "material_districts": material_districts,
            }
        else:
            by_district[recipient] = shapely.union(by_district[recipient], gap)
            gap_added[recipient] += gap_area
            status = (
                "single_district_state_line_gap_fill"
                if gap_area > MATERIAL_AREA_SQUARE_METERS
                else "numerical_gap_fill"
            )
            statuses[recipient].add(status)

    precinct_area = float(shapely.area(precinct_geometry))
    covered_area = float(
        sum(shapely.area(geometry) for geometry in by_district.values())
    )
    rows = []
    for district, geometry in sorted(by_district.items()):
        fragment_area = float(shapely.area(geometry))
        rows.append(
            {
                "target_precinct_geoid": precinct_id,
                "senate_district": district,
                "area_weight": fragment_area / covered_area,
                "fragment_area_square_meters": fragment_area,
                "precinct_area_square_meters": precinct_area,
                "coverage_ratio": covered_area / precinct_area,
                "raw_area_square_meters": raw_areas[district],
                "overlap_removed_square_meters": overlap_removed[district],
                "gap_added_square_meters": gap_added[district],
                "normalization_status": (
                    "+".join(sorted(statuses[district]))
                    if statuses[district]
                    else "raw_intersection"
                ),
                "geometry": geometry,
            }
        )
    return rows, issue


def choose_overlap_loser(
    left: int, right: int, raw_areas: dict[int, float]
) -> int:
    if raw_areas[left] == raw_areas[right]:
        return max(left, right)
    return left if raw_areas[left] < raw_areas[right] else right


def choose_gap_recipient(
    by_district: dict[int, object],
    material_districts: list[int],
    gap_area: float,
) -> int | None:
    if len(material_districts) == 1:
        return material_districts[0]
    if gap_area <= MATERIAL_AREA_SQUARE_METERS and by_district:
        return max(
            by_district, key=lambda district: shapely.area(by_district[district])
        )
    return None


def unresolved_population_diagnostics(
    blocks: gpd.GeoDataFrame,
    plan: gpd.GeoDataFrame,
    diagnostics: dict[str, object],
) -> dict[str, object]:
    unresolved_ids = {
        issue["target_precinct_geoid"]
        for issue in diagnostics["unresolved_precincts"]
    }
    if not unresolved_ids:
        return {
            "unresolved_uncovered_fragment_count": 0,
            "unresolved_uncovered_fragment_population": 0,
        }
    candidate = blocks[blocks["target_precinct_geoid"].isin(unresolved_ids)]
    plan_union = shapely.union_all(plan.geometry.array)
    representative_points = shapely.point_on_surface(candidate.geometry.array)
    uncovered = candidate.loc[~shapely.covers(plan_union, representative_points)]
    return {
        "unresolved_uncovered_fragment_count": len(uncovered),
        "unresolved_uncovered_fragment_population": int(
            uncovered["P0010001"].sum()
        ),
    }


def validate_overlay(
    overlay: gpd.GeoDataFrame, diagnostics: dict[str, object]
) -> list[dict[str, object]]:
    weight_sums = overlay.groupby("target_precinct_geoid")["area_weight"].sum()
    return [
        check(
            "all_precincts_supported",
            diagnostics["precinct_count"] == 9_178,
            diagnostics["precinct_count"],
        ),
        check(
            "all_districts_supported",
            diagnostics["senate_district_count"] == 50,
            diagnostics["senate_district_count"],
        ),
        check(
            "weights_in_range",
            bool(overlay["area_weight"].between(0, 1, inclusive="both").all()),
            int((~overlay["area_weight"].between(0, 1, inclusive="both")).sum()),
        ),
        check(
            "weights_sum_to_one",
            bool((weight_sums.sub(1).abs() <= WEIGHT_TOLERANCE).all()),
            float(weight_sums.sub(1).abs().max()),
        ),
        check(
            "ambiguous_gaps_have_no_population_support",
            diagnostics["unresolved_uncovered_fragment_count"] == 0
            and diagnostics["unresolved_uncovered_fragment_population"] == 0,
            {
                "gap_precincts": diagnostics["unresolved_precinct_count"],
                "gap_area_square_meters": diagnostics[
                    "unresolved_gap_area_square_meters"
                ],
                "uncovered_fragments": diagnostics[
                    "unresolved_uncovered_fragment_count"
                ],
                "uncovered_population": diagnostics[
                    "unresolved_uncovered_fragment_population"
                ],
            },
        ),
        check(
            "no_nearest_assignments",
            diagnostics["nearest_assignment_count"] == 0,
            diagnostics["nearest_assignment_count"],
        ),
        check(
            "geometry_valid",
            bool(
                overlay.geometry.notna().all()
                and (~overlay.geometry.is_empty).all()
                and overlay.geometry.is_valid.all()
            ),
            {
                "null": int(overlay.geometry.isna().sum()),
                "empty": int(overlay.geometry.is_empty.sum()),
                "invalid": int((~overlay.geometry.is_valid).sum()),
            },
        ),
        check(
            "coverage_ratio_in_range",
            bool(
                overlay["coverage_ratio"].gt(0).all()
                and overlay["coverage_ratio"].le(1 + WEIGHT_TOLERANCE).all()
            ),
            {
                "minimum": float(overlay["coverage_ratio"].min()),
                "maximum": float(overlay["coverage_ratio"].max()),
            },
        ),
    ]


def logical_geoframe_hash(frame: gpd.GeoDataFrame, sort_by: list[str]) -> str:
    normalized = pd.DataFrame(frame.drop(columns="geometry")).copy()
    normalized["geometry_wkb_hex"] = shapely.to_wkb(frame.geometry.array, hex=True)
    return logical_frame_hash(normalized, sort_by)


def write_immutable_geoparquet(
    frame: gpd.GeoDataFrame, path: Path, sort_by: list[str]
) -> str:
    expected_hash = logical_geoframe_hash(frame, sort_by)
    if path.exists():
        observed_hash = logical_geoframe_hash(gpd.read_parquet(path), sort_by)
        if observed_hash != expected_hash:
            raise RuntimeError(f"Refusing to overwrite changed artifact: {path}")
        return "reused_identical"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return "created"


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(qa: dict[str, object], summary: pd.DataFrame) -> str:
    table_rows = []
    for row in summary.itertuples(index=False):
        table_rows.append(
            f"| {row.senate_plan_id} | {row.allocation_rows:,} | "
            f"{row.split_precinct_count:,} | {row.overlap_removed_square_meters:.3f} | "
            f"{row.gap_added_square_meters:.3f} | {row.unresolved_precinct_count} |"
        )
    return f"""# POC022 fixed-precinct/State Senate overlays

Status: **{'PASS' if qa['passed'] else 'FAIL'}**

| Plan | Rows | Split fixed precincts | Overlap removed m² | Gap filled m² | Unresolved |
|---|---:|---:|---:|---:|---:|
{chr(10).join(table_rows)}

Every fixed precinct is represented, all 50 Senate districts are supported in
each plan, area weights sum to one within `{WEIGHT_TOLERANCE}`, and no nearest
assignment is used. Geometry is measured and stored in `{AREA_CRS}`.

Historical state-line gaps are filled only where the fixed precinct otherwise
intersects one material district. District overlaps are removed from the
district with less raw area inside that precinct. The normalization remains
explicit in every allocation row and the QA summary.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC022 overlay {'passed' if qa['passed'] else 'failed'}")


if __name__ == "__main__":
    main()
