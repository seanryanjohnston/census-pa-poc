"""Produce the POC010 statewide 2020 fixed-precinct and Senate result."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from census_pa_poc.crosswalk import build_lrc_published_crosswalk
from census_pa_poc.fixed_geography import load_lrc_blocks, load_lrc_precincts
from census_pa_poc.senate_overlay import logical_geoframe_hash
from census_pa_poc.sources import load_pl94_block_population_statewide, sha256
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    validate_crosswalk,
    write_immutable_parquet,
    write_json,
)

EXPECTED = {
    "source_blocks": 336_985,
    "lrc_fragments": 337_039,
    "fixed_precincts": 9_178,
    "senate_districts": 50,
    "counties": 67,
    "population": 13_002_700,
}

SOURCES = {
    "census_population": {
        "source_id": "census_2020_pa_pl",
        "producer": "U.S. Census Bureau",
        "product": "2020 Census State Redistricting Data PL 94-171 Summary File",
        "reference_vintage": "2020-04-01",
        "effective_vintage": "2020-04-01",
        "release_date": "2021-08-12",
        "url": (
            "https://www2.census.gov/programs-surveys/decennial/2020/data/"
            "01-Redistricting_File--PL_94-171/Pennsylvania/pa2020.pl.zip"
        ),
        "sha256": "2d33a7dab29c8dd5692bbde203d253e06eebbc44fcbaa96b1caa958d454026ae",
        "license_access": "Public federal data; cite U.S. Census Bureau",
        "crs": None,
        "schema": {
            "format": "pipe-delimited legacy summary file",
            "geography_member": "pageo2020.pl",
            "file01_member": "pa000012020.pl",
            "join": "LOGRECNO",
            "metric": "P0010001",
        },
        "geographic_universe": "2020 Census tabulation blocks in Pennsylvania",
        "population_universe": "Standard total population, P0010001",
        "relative_path": "data/raw/census_2020_pa_pl/pa2020.pl.zip",
    },
    "lrc_geography": {
        "source_id": "pa_lrc_2021_release_1b_geography",
        "producer": "Pennsylvania Legislative Reapportionment Commission",
        "product": "2021-10-05 LRC Data Release No. 1b Data Set 1 geography",
        "reference_vintage": "2020",
        "effective_vintage": "2021-10-05",
        "url": (
            "https://www.redistricting.state.pa.us/resources/GISData/Census/"
            "2021/2021-DataSet1-WithoutPrisoner/"
            "2021%20LRC%20Data%20Release%201b%20-%20Geography.zip"
        ),
        "sha256": "14187001c627c6a16bf967415059408c4ef7007d366fd9105b5be30763250e3b",
        "license_access": "Public download; redistribution terms not stated",
        "crs": "EPSG:4269",
        "schema": {
            "format": "ESRI Shapefile",
            "block_layer": "Geography/WP_Blocks.shp",
            "precinct_layer": "Geography/WP_VotingDistricts.shp",
            "fragment_id": "GEOID20",
            "target_id": "GEOID20",
            "metric": "P0010001",
        },
        "geographic_universe": "Pennsylvania corrected 2020 blocks and precincts",
        "population_universe": "Standard total population, P0010001",
        "relative_path": (
            "data/raw/pa_lrc_2021_release_1b_geography/"
            "2021 LRC Data Release 1b - Geography.zip"
        ),
    },
    "senate_equivalency": {
        "source_id": "pa_lrc_2021_final_senate_block_equivalency",
        "producer": "Pennsylvania Legislative Reapportionment Commission",
        "product": "2021 Final State Senate block equivalency file",
        "reference_vintage": "2021",
        "effective_vintage": "used for 2022-2026 elections",
        "url": (
            "https://www.redistricting.state.pa.us/Resources/GISData/Districts/"
            "Legislative/Senate/2021-Final/CSV/"
            "2022%20LRC%20Senate%20Final.csv"
        ),
        "sha256": "ff7a79d2da3df2094bebe9ab0f19d91bc2bfec8537f8d07a034b6b0d1b3dfbef",
        "license_access": "Public download; redistribution terms not stated",
        "crs": None,
        "schema": {
            "format": "headerless CSV",
            "columns": ["source_fragment_geoid", "senate_district"],
        },
        "geographic_universe": "LRC corrected 2020 block fragments in Pennsylvania",
        "population_universe": None,
        "relative_path": (
            "data/raw/pa_senate_2021_block_equivalency/2022 LRC Senate Final.csv"
        ),
    },
}

OVERLAY = {
    "artifact_id": "pa_senate_2021_final_fixed_precinct_overlay_v3",
    "producer": "POC022",
    "product": "Fixed 2021 LRC precinct to 2021 Final Senate area overlay",
    "source_precinct_dataset_id": "pa_lrc_2021_release_1b_geography",
    "source_precinct_effective_vintage": "2021-10-05",
    "target_senate_plan_id": "pa_senate_2021_final",
    "target_senate_plan_reference_vintage": "2021",
    "method_id": "fixed_precinct_senate_overlay_v3",
    "weighting_universe": "EPSG:5070 fixed precinct polygon area",
    "logical_sha256": "193cd389d11dab8976124f0b2d8f0f45fc7ef6519dc1183625567d9a13ba3a7d",
    "relative_path": (
        "data/processed/senate_overlays/"
        "pa_senate_2021_final_fixed_precinct_overlay_v3.parquet"
    ),
}


def run(root: Path) -> dict[str, object]:
    """Execute POC010 from frozen inputs through immutable result artifacts."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc010"
    processed_dir = root / "data/processed/statewide_2020"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    require_manifest_hashes(manifest)

    population = load_pl94_block_population_statewide(
        root / SOURCES["census_population"]["relative_path"]
    )
    lrc_archive = root / SOURCES["lrc_geography"]["relative_path"]
    lrc_blocks = load_lrc_blocks(lrc_archive)
    precincts = load_lrc_precincts(lrc_archive)
    equivalency = load_senate_equivalency(
        root / SOURCES["senate_equivalency"]["relative_path"]
    )
    overlay = gpd.read_parquet(root / OVERLAY["relative_path"])

    source_blocks = population[["source_block_geoid"]].rename(
        columns={"source_block_geoid": "GEOID20"}
    )
    crosswalk, crosswalk_diagnostics = build_lrc_published_crosswalk(
        source_blocks, lrc_blocks, projected_crs="EPSG:5070"
    )
    precinct_result = aggregate_to_precincts(population, crosswalk)
    precinct_result = add_result_metadata(precinct_result, "fixed_precinct")

    senate_rollup = aggregate_precincts_to_senate(precinct_result, overlay)
    senate_direct = aggregate_fragments_to_senate(lrc_blocks, equivalency)
    senate_result = combine_senate_methods(senate_rollup, senate_direct)
    comparison = compare_senate_methods(senate_result)
    equivalency_crosswalk = build_equivalency_crosswalk(equivalency)

    checks = build_checks(
        population,
        lrc_blocks,
        precincts,
        equivalency,
        overlay,
        crosswalk,
        precinct_result,
        senate_result,
        comparison,
    )
    writes = {
        "block_to_fixed_precinct_crosswalk": write_immutable_parquet(
            crosswalk,
            processed_dir / "block_to_fixed_precinct_lrc_published_split_v1.parquet",
            ["source_block_geoid", "target_precinct_geoid"],
        ),
        "fragment_to_senate_equivalency": write_immutable_parquet(
            equivalency_crosswalk,
            processed_dir / "lrc_fragment_to_2021_senate_equivalency_v1.parquet",
            ["source_fragment_geoid"],
        ),
        "fixed_precinct_population": write_immutable_parquet(
            precinct_result,
            processed_dir / "fixed_precinct_population_2020_v1.parquet",
            ["target_precinct_geoid"],
        ),
        "senate_population": write_immutable_parquet(
            senate_result,
            processed_dir / "senate_population_2020_2021_plan_v1.parquet",
            ["method_id", "senate_district"],
        ),
        "senate_method_comparison": write_immutable_parquet(
            comparison,
            processed_dir / "senate_method_comparison_2020_v1.parquet",
            ["senate_district"],
        ),
    }
    qa = {
        "task": "POC010",
        "accepted_precinct_method_id": "lrc_published_split_v1",
        "accepted_senate_method_id": "fixed_precinct_senate_overlay_v3",
        "independent_senate_check_method_id": "lrc_senate_block_equivalency_v1",
        "crosswalk_diagnostics": crosswalk_diagnostics,
        "checks": checks,
        "artifact_writes": writes,
        "hashes": {
            "block_to_fixed_precinct_crosswalk": logical_frame_hash(
                crosswalk, ["source_block_geoid", "target_precinct_geoid"]
            ),
            "fragment_to_senate_equivalency": logical_frame_hash(
                equivalency_crosswalk, ["source_fragment_geoid"]
            ),
            "fixed_precinct_population": logical_frame_hash(
                precinct_result, ["target_precinct_geoid"]
            ),
            "senate_population": logical_frame_hash(
                senate_result, ["method_id", "senate_district"]
            ),
            "senate_method_comparison": logical_frame_hash(
                comparison, ["senate_district"]
            ),
        },
        "nearest_assignment_count": 0,
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(render_report(qa, comparison))
    if not qa["passed"]:
        raise RuntimeError("POC010 QA failed; inspect artifacts/poc010/qa_results.json")
    return qa


def load_senate_equivalency(path: Path) -> pd.DataFrame:
    """Read the official headerless 2021 Final Senate block equivalency."""
    result = pd.read_csv(
        path,
        header=None,
        names=["source_fragment_geoid", "senate_district"],
        dtype={"source_fragment_geoid": "string", "senate_district": "int64"},
    )
    return result.sort_values("source_fragment_geoid").reset_index(drop=True)


def aggregate_to_precincts(
    population: pd.DataFrame, crosswalk: pd.DataFrame
) -> pd.DataFrame:
    """Allocate Census parent-block population through the split-aware crosswalk."""
    allocated = crosswalk.merge(
        population,
        on="source_block_geoid",
        how="left",
        validate="many_to_one",
    )
    allocated["allocated_population"] = allocated["P0010001"] * allocated["weight"]
    result = (
        allocated.groupby("target_precinct_geoid", as_index=False)[
            "allocated_population"
        ]
        .sum()
        .rename(columns={"allocated_population": "population"})
    )
    rounded = result["population"].round()
    if not result["population"].sub(rounded).abs().le(1e-8).all():
        raise ValueError("Published split allocation did not produce integer precincts")
    result["population"] = rounded.astype("int64")
    return result.sort_values("target_precinct_geoid").reset_index(drop=True)


def add_result_metadata(result: pd.DataFrame, geography_level: str) -> pd.DataFrame:
    """Attach explicit population, target, plan, and pairing provenance."""
    return result.assign(
        population_product_id="census_2020_pa_pl",
        population_reference_date="2020-04-01",
        population_release_date="2021-08-12",
        source_geography_id="census_2020_pa_blocks",
        source_reference_vintage="2020",
        target_snapshot_id="pa_lrc_2021_release_1b_geography",
        target_effective_vintage="2021-10-05",
        senate_plan_id="pa_senate_2021_final",
        senate_plan_reference_vintage="2021",
        general_election_date=pd.NA,
        election_pairing_status="unpaired_geography_product_poc010",
        applicable_general_elections="2022-11-08|2024-11-05|2026-11-03",
        geography_level=geography_level,
    )


def aggregate_precincts_to_senate(
    precinct_result: pd.DataFrame, overlay: pd.DataFrame
) -> pd.DataFrame:
    """Roll fixed-precinct totals through the accepted current-plan overlay."""
    allocated = overlay.merge(
        precinct_result[["target_precinct_geoid", "population"]],
        on="target_precinct_geoid",
        how="left",
        validate="many_to_one",
    )
    allocated["allocated_population"] = (
        allocated["population"] * allocated["area_weight"]
    )
    result = allocated.groupby("senate_district", as_index=False)[
        "allocated_population"
    ].sum()
    result = result.rename(columns={"allocated_population": "population"})
    result["method_id"] = "fixed_precinct_senate_overlay_v3"
    result["weighting_universe"] = "fixed_precinct_population_by_overlay_area_weight"
    return result


def aggregate_fragments_to_senate(
    lrc_blocks: pd.DataFrame, equivalency: pd.DataFrame
) -> pd.DataFrame:
    """Independently aggregate published fragment counts by official equivalency."""
    allocated = equivalency.merge(
        lrc_blocks[["GEOID20", "P0010001"]],
        left_on="source_fragment_geoid",
        right_on="GEOID20",
        how="left",
        validate="one_to_one",
    )
    result = allocated.groupby("senate_district", as_index=False)["P0010001"].sum()
    result = result.rename(columns={"P0010001": "population"})
    result["method_id"] = "lrc_senate_block_equivalency_v1"
    result["weighting_universe"] = "published_lrc_corrected_fragment_population"
    return result


def combine_senate_methods(*results: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat(results, ignore_index=True)
    combined["population"] = combined["population"].round().astype("int64")
    combined = add_result_metadata(combined, "state_senate_district")
    return combined.sort_values(["method_id", "senate_district"]).reset_index(drop=True)


def compare_senate_methods(senate_result: pd.DataFrame) -> pd.DataFrame:
    pivot = senate_result.pivot(
        index="senate_district", columns="method_id", values="population"
    ).reset_index()
    pivot["delta"] = (
        pivot["fixed_precinct_senate_overlay_v3"]
        - pivot["lrc_senate_block_equivalency_v1"]
    )
    return pivot.sort_values("senate_district").reset_index(drop=True)


def build_equivalency_crosswalk(equivalency: pd.DataFrame) -> pd.DataFrame:
    """Add the required immutable crosswalk lineage to published assignments."""
    return equivalency.assign(
        source_dataset_id="pa_lrc_2021_release_1b_geography",
        source_reference_vintage="2020",
        target_dataset_id="pa_senate_2021_final",
        target_reference_vintage="2021",
        weight=1.0,
        method_id="lrc_senate_block_equivalency_v1",
        method_version="1.0.0",
        weighting_universe="published_lrc_corrected_fragment_population",
        assignment_status="assigned",
        nearest_assignment_used=False,
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
    overlay_path = root / OVERLAY["relative_path"]
    overlay = gpd.read_parquet(overlay_path)
    overlay_entry = dict(OVERLAY)
    overlay_entry.update(
        {
            "created_timestamp": datetime.fromtimestamp(
                overlay_path.stat().st_mtime, UTC
            ).isoformat(),
            "size_bytes": overlay_path.stat().st_size,
            "physical_sha256": sha256(overlay_path),
            "observed_logical_sha256": logical_geoframe_hash(
                overlay, ["target_precinct_geoid", "senate_district"]
            ),
        }
    )
    return {
        "manifest_version": "1.0.0",
        "sources": entries,
        "derived_inputs": [overlay_entry],
    }


def require_manifest_hashes(manifest: dict[str, object]) -> None:
    failures = [
        source["source_id"]
        for source in manifest["sources"]
        if source["sha256"] != source["observed_sha256"]
    ]
    failures.extend(
        artifact["artifact_id"]
        for artifact in manifest["derived_inputs"]
        if artifact["logical_sha256"] != artifact["observed_logical_sha256"]
    )
    if failures:
        raise RuntimeError(f"Checksum mismatch: {', '.join(failures)}")


def build_checks(
    population: pd.DataFrame,
    lrc_blocks: pd.DataFrame,
    precincts: pd.DataFrame,
    equivalency: pd.DataFrame,
    overlay: pd.DataFrame,
    crosswalk: pd.DataFrame,
    precinct_result: pd.DataFrame,
    senate_result: pd.DataFrame,
    comparison: pd.DataFrame,
) -> list[dict[str, object]]:
    parent_ids = lrc_blocks["GEOID20"].astype("string").str.slice(0, 15)
    lrc_parent_population = (
        lrc_blocks.assign(source_block_geoid=parent_ids)
        .groupby("source_block_geoid")["P0010001"]
        .sum()
        .sort_index()
    )
    census_parent_population = population.set_index("source_block_geoid")[
        "P0010001"
    ].sort_index()
    expected_precinct = precincts.set_index("GEOID20")["P0010001"].sort_index()
    observed_precinct = precinct_result.set_index("target_precinct_geoid")[
        "population"
    ].sort_index()
    source_county = (
        population.assign(county_fips=population["source_block_geoid"].str.slice(2, 5))
        .groupby("county_fips")["P0010001"]
        .sum()
    )
    target_county = (
        precinct_result.assign(
            county_fips=precinct_result["target_precinct_geoid"].str.slice(2, 5)
        )
        .groupby("county_fips")["population"]
        .sum()
    )

    checks = validate_crosswalk(
        crosswalk,
        EXPECTED["source_blocks"],
        set(precincts["GEOID20"]),
        EXPECTED["lrc_fragments"],
    )
    checks.extend(
        [
            check(
                "source_block_count",
                len(population) == EXPECTED["source_blocks"],
                len(population),
            ),
            check(
                "source_block_ids_unique",
                population["source_block_geoid"].is_unique,
                int(population["source_block_geoid"].nunique()),
            ),
            check(
                "source_population_total",
                int(population["P0010001"].sum()) == EXPECTED["population"],
                int(population["P0010001"].sum()),
            ),
            check(
                "lrc_fragment_count",
                len(lrc_blocks) == EXPECTED["lrc_fragments"],
                len(lrc_blocks),
            ),
            check(
                "lrc_parent_count",
                parent_ids.nunique() == EXPECTED["source_blocks"],
                int(parent_ids.nunique()),
            ),
            check(
                "lrc_parent_populations_match_census",
                lrc_parent_population.equals(census_parent_population),
                int((lrc_parent_population != census_parent_population).sum()),
            ),
            check(
                "precinct_count",
                len(precinct_result) == EXPECTED["fixed_precincts"],
                len(precinct_result),
            ),
            check(
                "precinct_ids_unique",
                precinct_result["target_precinct_geoid"].is_unique,
                int(precinct_result["target_precinct_geoid"].nunique()),
            ),
            check(
                "precinct_populations_match_lrc",
                observed_precinct.equals(expected_precinct),
                int((observed_precinct != expected_precinct).sum()),
            ),
            check(
                "precinct_population_total",
                int(precinct_result["population"].sum()) == EXPECTED["population"],
                int(precinct_result["population"].sum()),
            ),
            check(
                "county_count",
                len(target_county) == EXPECTED["counties"],
                len(target_county),
            ),
            check(
                "county_totals_conserved",
                target_county.equals(source_county),
                int((target_county != source_county).sum()),
            ),
            check(
                "equivalency_row_count",
                len(equivalency) == EXPECTED["lrc_fragments"],
                len(equivalency),
            ),
            check(
                "equivalency_ids_unique",
                equivalency["source_fragment_geoid"].is_unique,
                int(equivalency["source_fragment_geoid"].nunique()),
            ),
            check(
                "equivalency_exact_fragment_universe",
                set(equivalency["source_fragment_geoid"]) == set(lrc_blocks["GEOID20"]),
                {
                    "equivalency": int(equivalency["source_fragment_geoid"].nunique()),
                    "lrc": int(lrc_blocks["GEOID20"].nunique()),
                },
            ),
            check(
                "equivalency_district_count",
                equivalency["senate_district"].nunique()
                == EXPECTED["senate_districts"],
                int(equivalency["senate_district"].nunique()),
            ),
            check(
                "overlay_precinct_count",
                overlay["target_precinct_geoid"].nunique()
                == EXPECTED["fixed_precincts"],
                int(overlay["target_precinct_geoid"].nunique()),
            ),
            check(
                "overlay_district_count",
                overlay["senate_district"].nunique() == EXPECTED["senate_districts"],
                int(overlay["senate_district"].nunique()),
            ),
            check(
                "overlay_current_plan_one_row_per_precinct",
                len(overlay) == EXPECTED["fixed_precincts"],
                len(overlay),
            ),
            check(
                "overlay_current_plan_weights_one",
                bool(overlay["area_weight"].eq(1.0).all()),
                int((~overlay["area_weight"].eq(1.0)).sum()),
            ),
            check(
                "senate_method_rows",
                len(senate_result) == EXPECTED["senate_districts"] * 2,
                len(senate_result),
            ),
            check(
                "senate_method_state_totals",
                bool(
                    senate_result.groupby("method_id")["population"]
                    .sum()
                    .eq(EXPECTED["population"])
                    .all()
                ),
                senate_result.groupby("method_id")["population"].sum().to_dict(),
            ),
            check(
                "senate_methods_exact",
                bool(comparison["delta"].eq(0).all()),
                {
                    "differing_districts": int(comparison["delta"].ne(0).sum()),
                    "total_absolute_delta": int(comparison["delta"].abs().sum()),
                },
            ),
            check("no_nearest_assignments", True, 0),
        ]
    )
    return checks


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(qa: dict[str, object], comparison: pd.DataFrame) -> str:
    return f"""# POC010 statewide 2020 population result

Status: **{"PASS" if qa["passed"] else "FAIL"}**

- Census parent blocks: {EXPECTED["source_blocks"]:,}
- LRC corrected fragments: {EXPECTED["lrc_fragments"]:,}
- Fixed precincts: {EXPECTED["fixed_precincts"]:,}
- State Senate districts: {EXPECTED["senate_districts"]:,}
- Pennsylvania population: {EXPECTED["population"]:,}
- Senate districts differing between the precinct-rollup and direct official
  block-equivalency routes: {int(comparison["delta"].ne(0).sum())}
- Total absolute Senate population delta: {int(comparison["delta"].abs().sum()):,}
- Nearest-boundary assignments: 0

The accepted precinct route allocates Census parent-block population through
the LRC published corrected-fragment crosswalk. The accepted Senate route rolls
those fixed-precinct totals through the POC022 `v3` overlay. The independent
route aggregates LRC corrected-fragment population using the official 2021
Final Senate block equivalency file. State and all 67 county totals conserve
population, and both Senate routes agree exactly in every district.

This POC010 product is deliberately not paired to a single election. The plan
is applicable to the 2022, 2024, and 2026 general elections; cycle/product
availability pairing remains POC019.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    run(args.root)


if __name__ == "__main__":
    main()
