"""Audit the statewide 2021 LRC fixed precinct target for POC021."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely

from census_pa_poc.sources import sha256, vsi_zip_member
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

EXPECTED = {
    "census_parent_blocks": 336_985,
    "lrc_fragments": 337_039,
    "lrc_parent_blocks": 336_985,
    "precincts": 9_178,
    "split_parent_blocks": 53,
    "split_fragments": 107,
    "two_target_parents": 52,
    "three_target_parents": 1,
}

PRECISION_TOLERANCE = {
    "max_outside_area_square_meters": 1.0,
    "total_outside_area_square_meters": 10.0,
}

SOURCES = {
    "census_blocks": {
        "source_id": "census_2020_pa_blocks",
        "producer": "U.S. Census Bureau",
        "product": "2020 PL 94-171 TIGER/Line Pennsylvania tabulation blocks",
        "reference_vintage": "2020",
        "effective_vintage": "2020-01-01",
        "url": "https://www2.census.gov/geo/tiger/TIGER2020PL/STATE/42_PENNSYLVANIA/42/tl_2020_42_tabblock20.zip",
        "sha256": "f2afff2b2a84170a3cf16bca52137562828d2811133419f22981ec790b2fbebb",
        "license_access": "Public federal data; acknowledge U.S. Census Bureau",
        "crs": "EPSG:4269",
        "geographic_universe": "2020 Census tabulation blocks in Pennsylvania",
        "relative_path": "data/raw/census_2020_pa_blocks/tl_2020_42_tabblock20.zip",
        "schema": {
            "format": "ESRI Shapefile",
            "layer": "tl_2020_42_tabblock20.shp",
            "id": "GEOID20",
        },
    },
    "lrc_geography": {
        "source_id": "pa_lrc_2021_release_1b_geography",
        "producer": "Pennsylvania Legislative Reapportionment Commission",
        "product": "2021-10-05 LRC Data Release No. 1b Data Set 1 geography",
        "reference_vintage": "2020",
        "effective_vintage": "2021-10-05",
        "url": "https://www.redistricting.state.pa.us/resources/GISData/Census/2021/2021-DataSet1-WithoutPrisoner/2021%20LRC%20Data%20Release%201b%20-%20Geography.zip",
        "sha256": "14187001c627c6a16bf967415059408c4ef7007d366fd9105b5be30763250e3b",
        "license_access": "Public download; redistribution terms not stated",
        "crs": "EPSG:4269",
        "geographic_universe": (
            "Pennsylvania corrected 2020 blocks and voting districts"
        ),
        "relative_path": (
            "data/raw/pa_lrc_2021_release_1b_geography/"
            "2021 LRC Data Release 1b - Geography.zip"
        ),
        "schema": {
            "format": "ESRI Shapefile",
            "block_layer": "Geography/WP_Blocks.shp",
            "precinct_layer": "Geography/WP_VotingDistricts.shp",
            "fragment_id": "GEOID20",
            "target_id": "GEOID20",
        },
    },
}

REQUIRED_LRC_FIELDS = [
    "FIPS",
    "VTD",
    "STATEFP20",
    "COUNTYFP20",
    "VTDST20",
    "GEOID20",
    "VTD_NAME",
]


def run(root: Path) -> dict[str, object]:
    """Execute the checksum-to-topology statewide fixed-target audit."""
    root = root.resolve()
    artifact_dir = root / "artifacts/work/poc021"
    processed_dir = root / "data/processed/statewide_fixed_geography"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    require_manifest_hashes(manifest)

    census_archive = root / SOURCES["census_blocks"]["relative_path"]
    lrc_archive = root / SOURCES["lrc_geography"]["relative_path"]
    census_blocks = load_census_block_ids(census_archive)
    lrc_blocks = load_lrc_blocks(lrc_archive)
    precincts = load_lrc_precincts(lrc_archive)

    assignments = build_assignment_inventory(lrc_blocks)
    geometry, precision_exceptions = audit_assignment_geometry(
        lrc_blocks, precincts, assignments
    )
    checks = build_checks(census_blocks, lrc_blocks, precincts, assignments, geometry)

    assignment_write = write_immutable_parquet(
        assignments,
        processed_dir / "lrc_fragment_to_fixed_precinct_v1.parquet",
        ["source_fragment_geoid"],
    )
    split_assignments = assignments[assignments["is_split_parent"]].copy()
    split_write = write_immutable_parquet(
        split_assignments,
        processed_dir / "split_parent_block_fragments_v1.parquet",
        ["source_parent_block_geoid", "source_fragment_geoid"],
    )
    precision_write = write_immutable_parquet(
        precision_exceptions,
        processed_dir / "precision_exceptions_v1.parquet",
        ["source_fragment_geoid"],
    )

    qa = {
        "task": "POC021",
        "method_id": "lrc_published_fragment_assignment_v1",
        "precision_tolerance": PRECISION_TOLERANCE,
        "checks": checks,
        "geometry_diagnostics": geometry,
        "artifact_writes": {
            "assignments": assignment_write,
            "split_assignments": split_write,
            "precision_exceptions": precision_write,
        },
        "hashes": {
            "assignments": logical_frame_hash(
                assignments, ["source_fragment_geoid"]
            ),
            "split_assignments": logical_frame_hash(
                split_assignments,
                ["source_parent_block_geoid", "source_fragment_geoid"],
            ),
            "precision_exceptions": logical_frame_hash(
                precision_exceptions, ["source_fragment_geoid"]
            ),
        },
        "nearest_assignment_count": 0,
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(render_report(qa, assignments))
    if not qa["passed"]:
        raise RuntimeError(
            "POC021 QA failed; inspect artifacts/work/poc021/qa_results.json"
        )
    return qa


def load_census_block_ids(archive: Path) -> pd.DataFrame:
    """Load only the statewide Census block identity needed by this audit."""
    return gpd.read_file(
        vsi_zip_member(archive, "tl_2020_42_tabblock20.shp"),
        columns=["GEOID20"],
        ignore_geometry=True,
    )


def load_lrc_blocks(archive: Path) -> gpd.GeoDataFrame:
    """Load statewide LRC corrected fragments and published target fields."""
    return gpd.read_file(
        vsi_zip_member(archive, "Geography/WP_Blocks.shp"),
        columns=[*REQUIRED_LRC_FIELDS, "P0010001"],
    )


def load_lrc_precincts(archive: Path) -> gpd.GeoDataFrame:
    """Load statewide LRC fixed-target precinct polygons."""
    return gpd.read_file(
        vsi_zip_member(archive, "Geography/WP_VotingDistricts.shp"),
        columns=["GEOID20", "P0010001", "STATEFP20", "COUNTYFP20", "VTDST20"],
    )


def build_assignment_inventory(lrc_blocks: gpd.GeoDataFrame) -> pd.DataFrame:
    """Create one published direct-assignment row per corrected LRC fragment."""
    fragment_ids = lrc_blocks["GEOID20"].astype("string")
    parent_ids = fragment_ids.str.slice(0, 15)
    target_ids = (
        lrc_blocks["STATEFP20"].astype("string")
        + lrc_blocks["COUNTYFP20"].astype("string")
        + lrc_blocks["VTDST20"].astype("string")
    )
    fragment_counts = parent_ids.groupby(parent_ids).transform("size")
    target_counts = target_ids.groupby(parent_ids).transform("nunique")
    return pd.DataFrame(
        {
            "source_dataset_id": "pa_lrc_2021_release_1b_geography",
            "source_reference_vintage": "2020",
            "source_fragment_geoid": fragment_ids,
            "source_parent_block_geoid": parent_ids,
            "target_dataset_id": "pa_lrc_2021_release_1b_geography",
            "target_effective_vintage": "2021-10-05",
            "target_precinct_geoid": target_ids,
            "fragment_population": lrc_blocks["P0010001"].astype("int64"),
            "parent_fragment_count": fragment_counts.astype("int64"),
            "parent_target_count": target_counts.astype("int64"),
            "is_split_parent": target_counts.gt(1),
            "weight": 1.0,
            "weighting_universe": "published_lrc_corrected_fragment",
            "method_id": "lrc_published_fragment_assignment_v1",
            "assignment_status": "assigned",
            "nearest_assignment_used": False,
        }
    )


def audit_assignment_geometry(
    lrc_blocks: gpd.GeoDataFrame,
    precincts: gpd.GeoDataFrame,
    assignments: pd.DataFrame,
) -> tuple[dict[str, object], pd.DataFrame]:
    """Check assigned targets by representative point and strict polygon cover."""
    target_geometry = precincts.set_index("GEOID20").geometry
    assigned_geometry = gpd.GeoSeries(
        target_geometry.reindex(assignments["target_precinct_geoid"]).array,
        crs=precincts.crs,
    )
    fragments = lrc_blocks.geometry.reset_index(drop=True)

    fragment_missing = fragments.isna() | fragments.is_empty
    precinct_missing = precincts.geometry.isna() | precincts.geometry.is_empty
    fragment_invalid = ~fragments.is_valid
    precinct_invalid = ~precincts.geometry.is_valid
    assigned_target_missing = assigned_geometry.isna() | assigned_geometry.is_empty

    geometry_ready = not bool(
        fragment_missing.any()
        or precinct_missing.any()
        or fragment_invalid.any()
        or precinct_invalid.any()
        or assigned_target_missing.any()
    )
    if not geometry_ready:
        diagnostics = {
            "fragment_null_or_empty": int(fragment_missing.sum()),
            "fragment_invalid": int(fragment_invalid.sum()),
            "precinct_null_or_empty": int(precinct_missing.sum()),
            "precinct_invalid": int(precinct_invalid.sum()),
            "assigned_target_missing": int(assigned_target_missing.sum()),
            "representative_point_exceptions": None,
            "strict_cover_exceptions": None,
            "max_outside_area_square_meters": None,
            "total_outside_area_square_meters": None,
        }
        return diagnostics, empty_precision_exceptions()

    representative_points = shapely.point_on_surface(fragments.array)
    representative_covered = shapely.covers(
        assigned_geometry.array, representative_points
    )
    strict_covered = shapely.covers(assigned_geometry.array, fragments.array)
    exception_mask = ~strict_covered

    precision = build_precision_exceptions(
        lrc_blocks,
        assigned_geometry,
        assignments,
        exception_mask,
    )
    max_outside = float(precision["outside_area_square_meters"].max()) if len(
        precision
    ) else 0.0
    total_outside = float(precision["outside_area_square_meters"].sum())
    diagnostics = {
        "fragment_null_or_empty": 0,
        "fragment_invalid": 0,
        "precinct_null_or_empty": 0,
        "precinct_invalid": 0,
        "assigned_target_missing": 0,
        "representative_point_exceptions": int((~representative_covered).sum()),
        "strict_cover_exceptions": int(exception_mask.sum()),
        "max_outside_area_square_meters": max_outside,
        "total_outside_area_square_meters": total_outside,
    }
    return diagnostics, precision


def build_precision_exceptions(
    lrc_blocks: gpd.GeoDataFrame,
    assigned_geometry: gpd.GeoSeries,
    assignments: pd.DataFrame,
    exception_mask,
) -> pd.DataFrame:
    """Measure strict-cover slivers in an equal-area CRS."""
    if not exception_mask.any():
        return empty_precision_exceptions()

    fragment_projected = gpd.GeoSeries(
        lrc_blocks.loc[exception_mask].geometry.array,
        crs=lrc_blocks.crs,
    ).to_crs("EPSG:5070")
    target_projected = gpd.GeoSeries(
        assigned_geometry.loc[exception_mask].array,
        crs=assigned_geometry.crs,
    ).to_crs("EPSG:5070")
    outside = shapely.difference(fragment_projected.array, target_projected.array)
    selected = assignments.loc[
        exception_mask, ["source_fragment_geoid", "target_precinct_geoid"]
    ].reset_index(drop=True)
    selected["outside_area_square_meters"] = shapely.area(outside)
    selected["exception_type"] = "numerical_or_linework_precision"
    return selected


def empty_precision_exceptions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_fragment_geoid": pd.Series(dtype="string"),
            "target_precinct_geoid": pd.Series(dtype="string"),
            "outside_area_square_meters": pd.Series(dtype="float64"),
            "exception_type": pd.Series(dtype="string"),
        }
    )


def build_checks(
    census_blocks: pd.DataFrame,
    lrc_blocks: gpd.GeoDataFrame,
    precincts: gpd.GeoDataFrame,
    assignments: pd.DataFrame,
    geometry: dict[str, object],
    expected: dict[str, int] = EXPECTED,
) -> list[dict[str, object]]:
    """Return explicit statewide coverage and topology checks."""
    census_ids = set(census_blocks["GEOID20"].astype("string"))
    parent_ids = set(assignments["source_parent_block_geoid"])
    precinct_ids = set(precincts["GEOID20"].astype("string"))
    target_ids = set(assignments["target_precinct_geoid"])
    target_counts = assignments.groupby("source_parent_block_geoid")[
        "target_precinct_geoid"
    ].nunique()
    split = assignments[assignments["is_split_parent"]]
    null_counts = {
        field: int(lrc_blocks[field].isna().sum()) for field in REQUIRED_LRC_FIELDS
    }
    checks = [
        check(
            "census_parent_block_count",
            len(census_ids) == expected["census_parent_blocks"],
            len(census_ids),
        ),
        check(
            "census_block_ids_unique",
            census_blocks["GEOID20"].is_unique,
            int(census_blocks["GEOID20"].nunique()),
        ),
        check(
            "lrc_fragment_count",
            len(assignments) == expected["lrc_fragments"],
            len(assignments),
        ),
        check(
            "lrc_fragment_ids_unique",
            assignments["source_fragment_geoid"].is_unique,
            int(assignments["source_fragment_geoid"].nunique()),
        ),
        check(
            "lrc_parent_block_count",
            len(parent_ids) == expected["lrc_parent_blocks"],
            len(parent_ids),
        ),
        check(
            "exact_parent_block_key_match",
            census_ids == parent_ids,
            {
                "census_only": len(census_ids - parent_ids),
                "lrc_only": len(parent_ids - census_ids),
            },
        ),
        check(
            "precinct_count",
            len(precinct_ids) == expected["precincts"],
            len(precinct_ids),
        ),
        check(
            "precinct_ids_unique",
            precincts["GEOID20"].is_unique,
            int(precincts["GEOID20"].nunique()),
        ),
        check(
            "exact_target_key_match",
            target_ids == precinct_ids,
            {
                "targets_without_polygon": len(target_ids - precinct_ids),
                "polygons_without_target": len(precinct_ids - target_ids),
            },
        ),
        check(
            "required_fields_non_null",
            not any(null_counts.values()),
            null_counts,
        ),
        check(
            "split_parent_block_count",
            split["source_parent_block_geoid"].nunique()
            == expected["split_parent_blocks"],
            int(split["source_parent_block_geoid"].nunique()),
        ),
        check(
            "split_fragment_count",
            len(split) == expected["split_fragments"],
            len(split),
        ),
        check(
            "two_target_parent_count",
            int(target_counts.eq(2).sum()) == expected["two_target_parents"],
            int(target_counts.eq(2).sum()),
        ),
        check(
            "three_target_parent_count",
            int(target_counts.eq(3).sum()) == expected["three_target_parents"],
            int(target_counts.eq(3).sum()),
        ),
        check(
            "fragment_geometry_valid",
            geometry["fragment_null_or_empty"] == 0
            and geometry["fragment_invalid"] == 0,
            {
                "null_or_empty": geometry["fragment_null_or_empty"],
                "invalid": geometry["fragment_invalid"],
            },
        ),
        check(
            "precinct_geometry_valid",
            geometry["precinct_null_or_empty"] == 0
            and geometry["precinct_invalid"] == 0,
            {
                "null_or_empty": geometry["precinct_null_or_empty"],
                "invalid": geometry["precinct_invalid"],
            },
        ),
        check(
            "all_assigned_targets_present",
            geometry["assigned_target_missing"] == 0,
            geometry["assigned_target_missing"],
        ),
        check(
            "representative_points_covered",
            geometry["representative_point_exceptions"] == 0,
            geometry["representative_point_exceptions"],
        ),
        check(
            "strict_cover_exceptions_below_tolerance",
            precision_below_tolerance(geometry),
            {
                "exception_count": geometry["strict_cover_exceptions"],
                "max_outside_area_square_meters": geometry[
                    "max_outside_area_square_meters"
                ],
                "total_outside_area_square_meters": geometry[
                    "total_outside_area_square_meters"
                ],
            },
        ),
        check(
            "no_nearest_assignments",
            not assignments["nearest_assignment_used"].any(),
            int(assignments["nearest_assignment_used"].sum()),
        ),
    ]
    return checks


def precision_below_tolerance(geometry: dict[str, object]) -> bool:
    max_outside = geometry["max_outside_area_square_meters"]
    total_outside = geometry["total_outside_area_square_meters"]
    if max_outside is None or total_outside is None:
        return False
    return bool(
        max_outside <= PRECISION_TOLERANCE["max_outside_area_square_meters"]
        and total_outside
        <= PRECISION_TOLERANCE["total_outside_area_square_meters"]
    )


def build_manifest(root: Path) -> dict[str, object]:
    entries = []
    for source in SOURCES.values():
        path = root / source["relative_path"]
        entry = dict(source)
        entry.update(
            {
                "retrieval_timestamp": datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ).isoformat(),
                "size_bytes": path.stat().st_size,
                "observed_sha256": sha256(path),
            }
        )
        entries.append(entry)
    return {"manifest_version": "1.0.0", "sources": entries}


def require_manifest_hashes(manifest: dict[str, object]) -> None:
    failures = [
        source["source_id"]
        for source in manifest["sources"]
        if source["sha256"] != source["observed_sha256"]
    ]
    if failures:
        raise RuntimeError(f"Checksum mismatch: {', '.join(failures)}")


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(qa: dict[str, object], assignments: pd.DataFrame) -> str:
    geometry = qa["geometry_diagnostics"]
    split = assignments[assignments["is_split_parent"]]
    return f"""# POC021 statewide fixed-precinct audit

Status: **{'PASS' if qa['passed'] else 'FAIL'}**

- Census parent blocks: {assignments['source_parent_block_geoid'].nunique():,}
- LRC corrected fragments: {len(assignments):,}
- Fixed LRC precinct targets: {assignments['target_precinct_geoid'].nunique():,}
- Split parent blocks: {split['source_parent_block_geoid'].nunique():,}
- Split fragments: {len(split):,}
- Representative-point coverage exceptions: {geometry['representative_point_exceptions']:,}
- Strict-cover precision exceptions: {geometry['strict_cover_exceptions']:,}
- Maximum outside area: {geometry['max_outside_area_square_meters']:.12g} square meters
- Total outside area: {geometry['total_outside_area_square_meters']:.12g} square meters
- Nearest-boundary assignments: {qa['nearest_assignment_count']:,}

The direct assignment unit is each published LRC corrected fragment. Parent
block splits remain explicit. Strict-cover exceptions pass only when their
projected outside area remains below the declared numerical/linework tolerance;
nearest-boundary assignment is never used.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC021 {'passed' if qa['passed'] else 'failed'}")


if __name__ == "__main__":
    main()
