"""Run POC001-POC005 for Cumberland County."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from census_pa_poc.crosswalk import (
    build_direct_crosswalk,
    build_representative_point_crosswalk,
    profile_direct_fields,
)
from census_pa_poc.sources import (
    CUMBERLAND_COUNTY_FIPS,
    load_census_blocks,
    load_lrc_blocks,
    load_lrc_precincts,
    load_pl94_block_population,
    sha256,
)
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    validate_crosswalk,
    write_immutable_parquet,
    write_json,
)

EXPECTED = {
    "block_count": 5_609,
    "precinct_count": 119,
    "population": 259_469,
    "crs": "EPSG:4269",
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
        "population_universe": None,
        "relative_path": ("data/raw/census_2020_pa_blocks/tl_2020_42_tabblock20.zip"),
    },
    "census_population": {
        "source_id": "census_2020_pa_pl",
        "producer": "U.S. Census Bureau",
        "product": "2020 Census State Redistricting Data PL 94-171 Summary File",
        "reference_vintage": "2020-04-01",
        "effective_vintage": "2020-04-01",
        "release_date": "2021-08-12",
        "url": "https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/Pennsylvania/pa2020.pl.zip",
        "sha256": "2d33a7dab29c8dd5692bbde203d253e06eebbc44fcbaa96b1caa958d454026ae",
        "license_access": "Public federal data; cite U.S. Census Bureau",
        "crs": None,
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
        "url": "https://www.redistricting.state.pa.us/resources/GISData/Census/2021/2021-DataSet1-WithoutPrisoner/2021%20LRC%20Data%20Release%201b%20-%20Geography.zip",
        "sha256": "14187001c627c6a16bf967415059408c4ef7007d366fd9105b5be30763250e3b",
        "license_access": "Public download; redistribution terms not stated",
        "crs": "EPSG:4269",
        "geographic_universe": (
            "Pennsylvania corrected 2020 blocks and voting districts"
        ),
        "population_universe": "Standard total population, P0010001",
        "relative_path": (
            "data/raw/pa_lrc_2021_release_1b_geography/"
            "2021 LRC Data Release 1b - Geography.zip"
        ),
    },
}


def run(root: Path) -> dict[str, object]:
    """Execute the complete checksum-to-comparison Cumberland experiment."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc001_poc005"
    processed_dir = root / "data/processed/cumberland"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    manifest = _build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    _require_manifest_hashes(manifest)

    block_archive = root / SOURCES["census_blocks"]["relative_path"]
    population_archive = root / SOURCES["census_population"]["relative_path"]
    lrc_archive = root / SOURCES["lrc_geography"]["relative_path"]

    census_blocks = load_census_blocks(block_archive, CUMBERLAND_COUNTY_FIPS)
    population = load_pl94_block_population(population_archive, CUMBERLAND_COUNTY_FIPS)
    lrc_blocks = load_lrc_blocks(lrc_archive, CUMBERLAND_COUNTY_FIPS)
    precincts = load_lrc_precincts(lrc_archive, CUMBERLAND_COUNTY_FIPS)

    source_gate = _source_gate(census_blocks, population, lrc_blocks, precincts)
    write_json(artifact_dir / "source_gate.json", source_gate)
    if not source_gate["passed"]:
        raise RuntimeError("POC001 source gate failed; inspect source_gate.json")

    profile = profile_direct_fields(lrc_blocks)
    precinct_ids = set(precincts["GEOID20"])
    direct_ids = set(
        lrc_blocks["STATEFP20"] + lrc_blocks["COUNTYFP20"] + lrc_blocks["VTDST20"]
    )
    profile["direct_targets_match_precinct_layer"] = direct_ids == precinct_ids
    write_json(artifact_dir / "lrc_block_profile.json", profile)

    direct = build_direct_crosswalk(census_blocks, lrc_blocks)
    spatial, geometry_diagnostics = build_representative_point_crosswalk(
        census_blocks, precincts
    )
    direct_write = write_immutable_parquet(
        direct,
        processed_dir / "crosswalk_lrc_direct_v1.parquet",
        ["source_block_geoid"],
    )
    spatial_write = write_immutable_parquet(
        spatial,
        processed_dir / "crosswalk_representative_point_v1.parquet",
        ["source_block_geoid"],
    )

    direct_checks = validate_crosswalk(direct, EXPECTED["block_count"], precinct_ids)
    spatial_checks = validate_crosswalk(spatial, EXPECTED["block_count"], precinct_ids)
    crosswalk_qa = {
        "direct": direct_checks,
        "representative_point": spatial_checks,
        "geometry_diagnostics": geometry_diagnostics,
        "artifact_writes": {
            "direct": direct_write,
            "representative_point": spatial_write,
        },
        "hashes": {
            "direct": logical_frame_hash(direct, ["source_block_geoid"]),
            "representative_point": logical_frame_hash(spatial, ["source_block_geoid"]),
        },
    }

    results, comparison = _aggregate_and_compare(population, precincts, direct, spatial)
    results.to_parquet(processed_dir / "precinct_population.parquet", index=False)
    results.to_csv(processed_dir / "precinct_population.csv", index=False)
    comparison.to_parquet(processed_dir / "method_comparison.parquet", index=False)
    comparison.to_csv(processed_dir / "method_comparison.csv", index=False)

    result_qa = _result_checks(results, comparison, precinct_ids)
    qa = {
        "tasks": ["POC001", "POC002", "POC003", "POC004", "POC005"],
        "crosswalk": crosswalk_qa,
        "result": result_qa,
        "passed": (
            all_pass(direct_checks) and all_pass(spatial_checks) and all_pass(result_qa)
        ),
    }
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(
        _render_report(source_gate, profile, qa, comparison)
    )
    if not qa["passed"]:
        raise RuntimeError("POC001-POC005 QA failed; inspect qa_results.json")
    return qa


def _build_manifest(root: Path) -> dict[str, object]:
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
                "schema": _schema_for(str(source["source_id"])),
            }
        )
        entries.append(entry)
    return {"manifest_version": "1.0.0", "sources": entries}


def _schema_for(source_id: str) -> dict[str, object]:
    if source_id == "census_2020_pa_blocks":
        return {"format": "ESRI Shapefile", "id": "GEOID20"}
    if source_id == "census_2020_pa_pl":
        return {
            "format": "pipe-delimited legacy summary file",
            "geography_member": "pageo2020.pl",
            "file01_member": "pa000012020.pl",
            "join": "LOGRECNO",
            "metric": "P0010001",
        }
    return {
        "format": "ESRI Shapefile",
        "block_layer": "Geography/WP_Blocks.shp",
        "precinct_layer": "Geography/WP_VotingDistricts.shp",
        "block_id": "GEOID20",
        "precinct_id": "GEOID20",
        "direct_precinct_fields": ["STATEFP20", "COUNTYFP20", "VTDST20"],
    }


def _require_manifest_hashes(manifest: dict[str, object]) -> None:
    failures = [
        source["source_id"]
        for source in manifest["sources"]
        if source["sha256"] != source["observed_sha256"]
    ]
    if failures:
        raise RuntimeError(f"Checksum mismatch: {', '.join(failures)}")


def _source_gate(census_blocks, population, lrc_blocks, precincts) -> dict[str, object]:
    census_ids = set(census_blocks["GEOID20"])
    population_ids = set(population["source_block_geoid"])
    lrc_ids = set(lrc_blocks["GEOID20"])
    checks = [
        _check(
            "census_block_count",
            len(census_blocks) == EXPECTED["block_count"],
            len(census_blocks),
        ),
        _check(
            "population_block_count",
            len(population) == EXPECTED["block_count"],
            len(population),
        ),
        _check(
            "lrc_block_count",
            len(lrc_blocks) == EXPECTED["block_count"],
            len(lrc_blocks),
        ),
        _check(
            "precinct_count",
            len(precincts) == EXPECTED["precinct_count"],
            len(precincts),
        ),
        _check(
            "census_block_ids_unique",
            census_blocks["GEOID20"].is_unique,
            int(census_blocks["GEOID20"].nunique()),
        ),
        _check(
            "population_block_ids_unique",
            population["source_block_geoid"].is_unique,
            int(population["source_block_geoid"].nunique()),
        ),
        _check(
            "lrc_block_ids_unique",
            lrc_blocks["GEOID20"].is_unique,
            int(lrc_blocks["GEOID20"].nunique()),
        ),
        _check(
            "precinct_ids_unique",
            precincts["GEOID20"].is_unique,
            int(precincts["GEOID20"].nunique()),
        ),
        _check(
            "exact_block_key_match",
            census_ids == population_ids == lrc_ids,
            {
                "census": len(census_ids),
                "population": len(population_ids),
                "lrc": len(lrc_ids),
            },
        ),
        _check(
            "population_non_null",
            population["P0010001"].notna().all(),
            int(population["P0010001"].isna().sum()),
        ),
        _check(
            "population_total",
            int(population["P0010001"].sum()) == EXPECTED["population"],
            int(population["P0010001"].sum()),
        ),
        _check(
            "lrc_block_population_total",
            int(lrc_blocks["P0010001"].sum()) == EXPECTED["population"],
            int(lrc_blocks["P0010001"].sum()),
        ),
        _check(
            "lrc_precinct_population_total",
            int(precincts["P0010001"].sum()) == EXPECTED["population"],
            int(precincts["P0010001"].sum()),
        ),
        _check(
            "census_crs",
            census_blocks.crs.to_string() == EXPECTED["crs"],
            census_blocks.crs.to_string(),
        ),
        _check(
            "lrc_block_crs",
            lrc_blocks.crs.to_string() == EXPECTED["crs"],
            lrc_blocks.crs.to_string(),
        ),
        _check(
            "lrc_precinct_crs",
            precincts.crs.to_string() == EXPECTED["crs"],
            precincts.crs.to_string(),
        ),
        _check(
            "census_geometry_present",
            census_blocks.geometry.notna().all()
            and (~census_blocks.geometry.is_empty).all(),
            int(
                census_blocks.geometry.isna().sum()
                + census_blocks.geometry.is_empty.sum()
            ),
        ),
        _check(
            "precinct_geometry_present",
            precincts.geometry.notna().all() and (~precincts.geometry.is_empty).all(),
            int(precincts.geometry.isna().sum() + precincts.geometry.is_empty.sum()),
        ),
    ]
    return {"checks": checks, "passed": all_pass(checks)}


def _aggregate(
    population: pd.DataFrame, crosswalk: pd.DataFrame, method_id: str
) -> pd.DataFrame:
    allocated = population.merge(
        crosswalk, on="source_block_geoid", validate="one_to_one"
    )
    allocated["population"] = allocated["P0010001"] * allocated["weight"]
    totals = allocated.groupby("target_precinct_geoid", as_index=False)[
        "population"
    ].sum()
    totals["population"] = totals["population"].astype("int64")
    totals["population_product_id"] = "census_2020_pa_pl"
    totals["population_reference_date"] = "2020-04-01"
    totals["population_release_date"] = "2021-08-12"
    totals["target_snapshot_id"] = "pa_lrc_2021_release_1b_geography"
    totals["target_effective_vintage"] = "2021-10-05"
    totals["general_election_date"] = None
    totals["method_id"] = method_id
    totals["metric"] = "P0010001"
    totals["population_universe"] = "standard_total_population"
    return totals


def _aggregate_and_compare(population, precincts, direct, spatial):
    direct_totals = _aggregate(population, direct, "lrc_direct_v1")
    spatial_totals = _aggregate(population, spatial, "representative_point_v1")
    results = pd.concat([direct_totals, spatial_totals], ignore_index=True)
    targets = precincts[["GEOID20", "NAME", "P0010001"]].rename(
        columns={
            "GEOID20": "target_precinct_geoid",
            "P0010001": "lrc_population",
        }
    )
    comparison = targets.merge(
        direct_totals[["target_precinct_geoid", "population"]].rename(
            columns={"population": "direct_population"}
        ),
        on="target_precinct_geoid",
        how="left",
        validate="one_to_one",
    ).merge(
        spatial_totals[["target_precinct_geoid", "population"]].rename(
            columns={"population": "spatial_population"}
        ),
        on="target_precinct_geoid",
        how="left",
        validate="one_to_one",
    )
    for column in ["direct_population", "spatial_population"]:
        comparison[column] = comparison[column].fillna(0).astype("int64")
    comparison["direct_minus_lrc"] = (
        comparison["direct_population"] - comparison["lrc_population"]
    )
    comparison["spatial_minus_lrc"] = (
        comparison["spatial_population"] - comparison["lrc_population"]
    )
    comparison["spatial_minus_direct"] = (
        comparison["spatial_population"] - comparison["direct_population"]
    )
    return (
        results.sort_values(["method_id", "target_precinct_geoid"]),
        comparison.sort_values("target_precinct_geoid"),
    )


def _result_checks(results, comparison, precinct_ids):
    direct = results[results["method_id"] == "lrc_direct_v1"]
    spatial = results[results["method_id"] == "representative_point_v1"]
    grain = [
        "population_product_id",
        "target_snapshot_id",
        "method_id",
        "target_precinct_geoid",
        "metric",
        "population_universe",
    ]
    return [
        _check(
            "result_grain_unique",
            not results.duplicated(grain).any(),
            int(results.duplicated(grain).sum()),
        ),
        _check(
            "direct_target_count",
            set(direct["target_precinct_geoid"]) == precinct_ids,
            len(direct),
        ),
        _check(
            "spatial_target_count",
            set(spatial["target_precinct_geoid"]) == precinct_ids,
            len(spatial),
        ),
        _check(
            "direct_population_conserved",
            int(direct["population"].sum()) == EXPECTED["population"],
            int(direct["population"].sum()),
        ),
        _check(
            "spatial_population_conserved",
            int(spatial["population"].sum()) == EXPECTED["population"],
            int(spatial["population"].sum()),
        ),
        _check(
            "direct_reconciles_lrc",
            bool(comparison["direct_minus_lrc"].eq(0).all()),
            {
                "different_precincts": int(comparison["direct_minus_lrc"].ne(0).sum()),
                "absolute_delta": int(comparison["direct_minus_lrc"].abs().sum()),
            },
        ),
        _check(
            "method_comparison_recorded",
            len(comparison) == EXPECTED["precinct_count"],
            {
                "precincts": len(comparison),
                "different_precincts": int(
                    comparison["spatial_minus_direct"].ne(0).sum()
                ),
                "absolute_delta": int(comparison["spatial_minus_direct"].abs().sum()),
                "max_absolute_delta": int(
                    comparison["spatial_minus_direct"].abs().max()
                ),
            },
        ),
    ]


def _render_report(source_gate, profile, qa, comparison) -> str:
    changed = comparison[comparison["spatial_minus_direct"] != 0]
    result_checks = {check["check_id"]: check for check in qa["result"]}
    method_delta = result_checks["method_comparison_recorded"]["observed"]
    status = "PASS" if qa["passed"] else "FAIL"
    source_status = "PASS" if source_gate["passed"] else "FAIL"
    return f"""# Cumberland 2020 population proof — POC001–POC005

Generated from checksum-verified local copies of the three sources in
`input_manifest.json`. All machine-readable checks are in `qa_results.json`.

## Outcome

- Overall QA: **{status}**
- Source gate: **{source_status}**
- Census/LRC block keys: {EXPECTED["block_count"]:,} exact matches
- LRC precinct targets: {EXPECTED["precinct_count"]}
- County population conserved by both methods: {EXPECTED["population"]:,}
- Direct assignment reconciles every LRC precinct total:
  **{result_checks["direct_reconciles_lrc"]["passed"]}**
- Direct versus representative-point differences:
  {method_delta["different_precincts"]} precincts,
  {method_delta["absolute_delta"]:,} total absolute persons,
  {method_delta["max_absolute_delta"]:,} maximum absolute precinct delta

## Published-field profile

```json
{json.dumps(profile, indent=2, sort_keys=True)}
```

## Interpretation

The LRC block layer provides one complete published precinct key per Cumberland
block. The direct crosswalk therefore reproduces the LRC precinct population
table exactly. The representative-point method is independently derived from
Census block and LRC precinct geometries; its measured differences are retained
in `method_comparison.parquet` rather than silently resolved.

Changed precinct rows: {len(changed)}.
"""


def _check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(json.dumps({"passed": qa["passed"]}, sort_keys=True))


if __name__ == "__main__":
    main()
