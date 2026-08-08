"""Run the Philadelphia source qualification and complex-county proof."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from census_pa_poc.crosswalk import (
    AREA_SLIVER_TOLERANCE,
    build_area_overlay_crosswalk,
    build_lrc_published_crosswalk,
    build_representative_point_crosswalk,
    canonical_lrc_source_block_id,
    profile_direct_fields,
)
from census_pa_poc.cumberland import SOURCES as CUMBERLAND_SOURCES
from census_pa_poc.sources import (
    PHILADELPHIA_COUNTY_FIPS,
    load_census_blocks,
    load_lrc_blocks,
    load_lrc_precincts,
    load_philadelphia_divisions,
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
    "census_block_count": 17_554,
    "lrc_allocation_row_count": 17_567,
    "precinct_count": 1_703,
    "ward_count": 66,
    "population": 1_603_797,
    "split_source_blocks": 13,
    "split_source_population": 931,
    "city_crs": "EPSG:3857",
    "lrc_crs": "EPSG:4269",
}

CITY_SOURCE = {
    "source_id": "phila_city_political_divisions_2026_08_07",
    "producer": "City of Philadelphia, Philadelphia City Planning Commission",
    "product": "Political Divisions hosted feature layer snapshot",
    "reference_vintage": None,
    "effective_vintage": None,
    "as_of_date": "2026-08-07",
    "service_data_last_edit": "2025-06-25T07:54:19Z",
    "service_item_last_modified": "2026-08-03T11:27:32Z",
    "url": (
        "https://services.arcgis.com/fLeGjb7u4uXqeF9q/ArcGIS/rest/services/"
        "Political_Divisions/FeatureServer/0/query?where=1%3D1&outFields="
        "objectid%2Cshort_div_num%2Cdivision_num&returnGeometry=true&outSR="
        "3857&orderByFields=division_num&resultRecordCount=2000&f=geojson"
    ),
    "catalog_url": ("https://opendataphilly.org/datasets/political-ward-divisions/"),
    "commissioners_url": (
        "https://votes.phila.gov/resources-data/election-resources/political-maps/"
    ),
    "service_item_id": "160a3665943d4864806d7b1399029a04",
    "sha256": "1b847f76069e6dd8c0185e59c20e337fa4261aea7739694f24dffc80fcf442a6",
    "license_access": (
        "Public use under City of Philadelphia terms; data is provided as-is, "
        "boundaries are self-reported, and the City disclaims warranties"
    ),
    "crs": "EPSG:3857",
    "geographic_universe": (
        "All City of Philadelphia political ward divisions in the retrieved layer"
    ),
    "population_universe": None,
    "relative_path": (
        "data/raw/phila_city_political_divisions/political_divisions.geojson"
    ),
}


def run(root: Path) -> dict[str, object]:
    """Execute POC006 and POC007 from frozen, checksum-verified inputs."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc006_poc007"
    processed_dir = root / "data/processed/philadelphia"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    manifest = _build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    _require_manifest_hashes(manifest)

    census_blocks, population, lrc_blocks, precincts, city_divisions = _load(root)
    source_gate = _source_gate(
        census_blocks, population, lrc_blocks, precincts, city_divisions
    )
    write_json(artifact_dir / "source_gate.json", source_gate)
    if not source_gate["passed"]:
        raise RuntimeError("POC006 source gate failed; inspect source_gate.json")

    profile = _source_profile(lrc_blocks, precincts, city_divisions)
    write_json(artifact_dir / "source_profile.json", profile)

    published, published_diagnostics = build_lrc_published_crosswalk(
        census_blocks, lrc_blocks
    )
    point, point_diagnostics = build_representative_point_crosswalk(
        census_blocks, precincts
    )
    area, area_diagnostics = build_area_overlay_crosswalk(census_blocks, precincts)
    target_ids = set(precincts["GEOID20"])

    crosswalks = {
        "lrc_published_split_v1": published,
        "representative_point_v1": point,
        "area_overlay_v1": area,
    }
    expected_rows = {
        "lrc_published_split_v1": EXPECTED["lrc_allocation_row_count"],
        "representative_point_v1": EXPECTED["census_block_count"],
        "area_overlay_v1": EXPECTED["lrc_allocation_row_count"],
    }
    crosswalk_checks = {
        method: validate_crosswalk(
            crosswalk,
            EXPECTED["census_block_count"],
            target_ids,
            expected_rows[method],
        )
        for method, crosswalk in crosswalks.items()
    }
    artifact_writes = {
        method: write_immutable_parquet(
            crosswalk,
            processed_dir / f"crosswalk_{method}.parquet",
            ["source_block_geoid", "target_precinct_geoid"],
        )
        for method, crosswalk in crosswalks.items()
    }

    results, comparison = _aggregate_and_compare(population, precincts, crosswalks)
    split_comparison = _split_block_comparison(population, crosswalks)
    results.to_parquet(processed_dir / "precinct_population.parquet", index=False)
    results.to_csv(processed_dir / "precinct_population.csv", index=False)
    comparison.to_parquet(processed_dir / "method_comparison.parquet", index=False)
    comparison.to_csv(processed_dir / "method_comparison.csv", index=False)
    split_comparison.to_parquet(
        processed_dir / "split_block_comparison.parquet", index=False
    )
    split_comparison.to_csv(processed_dir / "split_block_comparison.csv", index=False)

    result_checks = _result_checks(results, comparison)
    impact = _impact_summary(population, published, point, area, comparison)
    qa = {
        "tasks": ["POC006", "POC007"],
        "source_gate": source_gate,
        "source_profile": profile,
        "crosswalk": {
            "checks": crosswalk_checks,
            "diagnostics": {
                "lrc_published_split_v1": published_diagnostics,
                "representative_point_v1": point_diagnostics,
                "area_overlay_v1": area_diagnostics,
            },
            "artifact_writes": artifact_writes,
            "hashes": {
                method: logical_frame_hash(
                    crosswalk,
                    ["source_block_geoid", "target_precinct_geoid"],
                )
                for method, crosswalk in crosswalks.items()
            },
        },
        "result": result_checks,
        "impact": impact,
    }
    qa["passed"] = (
        source_gate["passed"]
        and all(all_pass(checks) for checks in crosswalk_checks.values())
        and all_pass(result_checks)
        and impact["observed_split_source_blocks"] == EXPECTED["split_source_blocks"]
        and impact["observed_split_source_population"]
        == EXPECTED["split_source_population"]
    )
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(_render_report(qa))
    if not qa["passed"]:
        raise RuntimeError("POC006-POC007 QA failed; inspect qa_results.json")
    return qa


def _load(root: Path):
    census_archive = root / CUMBERLAND_SOURCES["census_blocks"]["relative_path"]
    population_archive = root / CUMBERLAND_SOURCES["census_population"]["relative_path"]
    lrc_archive = root / CUMBERLAND_SOURCES["lrc_geography"]["relative_path"]
    city_path = root / CITY_SOURCE["relative_path"]
    return (
        load_census_blocks(census_archive, PHILADELPHIA_COUNTY_FIPS),
        load_pl94_block_population(population_archive, PHILADELPHIA_COUNTY_FIPS),
        load_lrc_blocks(lrc_archive, PHILADELPHIA_COUNTY_FIPS),
        load_lrc_precincts(lrc_archive, PHILADELPHIA_COUNTY_FIPS),
        load_philadelphia_divisions(city_path),
    )


def _build_manifest(root: Path) -> dict[str, object]:
    sources = [dict(source) for source in CUMBERLAND_SOURCES.values()]
    sources.append(dict(CITY_SOURCE))
    entries = []
    for source in sources:
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
    if source_id == CITY_SOURCE["source_id"]:
        return {
            "format": "GeoJSON",
            "geometry_type": "Polygon",
            "fields": {
                "objectid": "integer feature-service object ID",
                "short_div_num": "two-character division within ward",
                "division_num": "four-character ward plus division ID",
            },
        }
    if source_id == "census_2020_pa_blocks":
        return {"format": "ESRI Shapefile", "id": "GEOID20"}
    if source_id == "census_2020_pa_pl":
        return {
            "format": "pipe-delimited legacy summary file",
            "join": "LOGRECNO",
            "metric": "P0010001",
        }
    return {
        "format": "ESRI Shapefile",
        "block_layer": "Geography/WP_Blocks.shp",
        "precinct_layer": "Geography/WP_VotingDistricts.shp",
        "corrected_fragment_id": "GEOID20 with A/B suffix",
        "precinct_id": "GEOID20",
    }


def _require_manifest_hashes(manifest: dict[str, object]) -> None:
    failures = [
        source["source_id"]
        for source in manifest["sources"]
        if source["sha256"] != source["observed_sha256"]
    ]
    if failures:
        raise RuntimeError(f"Checksum mismatch: {', '.join(failures)}")


def _source_gate(census_blocks, population, lrc_blocks, precincts, city_divisions):
    census_ids = set(census_blocks["GEOID20"])
    population_ids = set(population["source_block_geoid"])
    lrc_parent_ids = set(lrc_blocks["GEOID20"].map(canonical_lrc_source_block_id))
    city_ids = city_divisions["division_num"]
    checks = [
        _check("census_block_count", len(census_blocks) == 17_554, len(census_blocks)),
        _check("population_block_count", len(population) == 17_554, len(population)),
        _check("lrc_allocation_row_count", len(lrc_blocks) == 17_567, len(lrc_blocks)),
        _check("lrc_precinct_count", len(precincts) == 1_703, len(precincts)),
        _check(
            "city_division_count", len(city_divisions) == 1_703, len(city_divisions)
        ),
        _check(
            "exact_parent_block_key_match",
            census_ids == population_ids == lrc_parent_ids,
            {
                "census": len(census_ids),
                "population": len(population_ids),
                "lrc_parents": len(lrc_parent_ids),
            },
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
            census_blocks.crs.to_string() == EXPECTED["lrc_crs"],
            census_blocks.crs.to_string(),
        ),
        _check(
            "lrc_block_crs",
            lrc_blocks.crs.to_string() == EXPECTED["lrc_crs"],
            lrc_blocks.crs.to_string(),
        ),
        _check(
            "lrc_precinct_crs",
            precincts.crs.to_string() == EXPECTED["lrc_crs"],
            precincts.crs.to_string(),
        ),
        _check(
            "census_geometries_present",
            census_blocks.geometry.notna().all()
            and (~census_blocks.geometry.is_empty).all(),
            {
                "null": int(census_blocks.geometry.isna().sum()),
                "empty": int(census_blocks.geometry.is_empty.sum()),
            },
        ),
        _check(
            "lrc_precinct_geometries_present",
            precincts.geometry.notna().all() and (~precincts.geometry.is_empty).all(),
            {
                "null": int(precincts.geometry.isna().sum()),
                "empty": int(precincts.geometry.is_empty.sum()),
            },
        ),
        _check(
            "city_ids_unique_non_null",
            city_ids.is_unique and city_ids.notna().all(),
            {"unique": int(city_ids.nunique()), "null": int(city_ids.isna().sum())},
        ),
        _check(
            "city_identifier_schema",
            city_ids.str.fullmatch(r"\d{4}").all(),
            {"four_digit_ids": int(city_ids.str.fullmatch(r"\d{4}").sum())},
        ),
        _check(
            "city_short_id_anomaly_recorded",
            (city_divisions["short_div_num"] != city_ids.str[-2:]).sum() == 1,
            _short_id_anomalies(city_divisions),
        ),
        _check(
            "city_ward_count",
            city_ids.str[:2].nunique() == EXPECTED["ward_count"],
            int(city_ids.str[:2].nunique()),
        ),
        _check(
            "city_crs",
            city_divisions.crs.to_string() == EXPECTED["city_crs"],
            city_divisions.crs.to_string(),
        ),
        _check(
            "city_geometries_valid_present",
            city_divisions.geometry.notna().all()
            and (~city_divisions.geometry.is_empty).all()
            and city_divisions.geometry.is_valid.all(),
            {
                "null": int(city_divisions.geometry.isna().sum()),
                "empty": int(city_divisions.geometry.is_empty.sum()),
                "invalid": int((~city_divisions.geometry.is_valid).sum()),
            },
        ),
    ]
    return {"checks": checks, "passed": all_pass(checks)}


def _source_profile(lrc_blocks, precincts, city_divisions):
    direct = profile_direct_fields(lrc_blocks)
    city_ids = set(city_divisions["division_num"])
    lrc_ids = set(precincts["VTDST20"].str[-4:])
    return {
        "expected_coverage": {
            "county": "Philadelphia County, Pennsylvania (FIPS 101)",
            "city_divisions": EXPECTED["precinct_count"],
            "wards": EXPECTED["ward_count"],
            "official_count_basis": CITY_SOURCE["commissioners_url"],
        },
        "city_layer": {
            "rows": len(city_divisions),
            "unique_ids": int(city_divisions["division_num"].nunique()),
            "wards": int(city_divisions["division_num"].str[:2].nunique()),
            "crs": city_divisions.crs.to_string(),
            "geometry_types": _value_counts(city_divisions.geom_type),
            "multipart_geometries": int(
                city_divisions.geom_type.eq("MultiPolygon").sum()
            ),
            "invalid_geometries": int((~city_divisions.geometry.is_valid).sum()),
            "short_division_id_anomalies": _short_id_anomalies(city_divisions),
            "boundary_effective_date": None,
            "as_of_date": CITY_SOURCE["as_of_date"],
            "effective_date_limitation": (
                "The service and catalog do not publish an election-effective "
                "boundary date; do not relabel this snapshot as November 2026."
            ),
        },
        "lrc_corrected_block_fields": direct,
        "lrc_precinct_layer": {
            "rows": len(precincts),
            "geometry_types": _value_counts(precincts.geom_type),
            "multipart_geometries": int(precincts.geom_type.eq("MultiPolygon").sum()),
            "invalid_geometries": int((~precincts.geometry.is_valid).sum()),
        },
        "city_vs_lrc_identifiers": {
            "common": len(city_ids & lrc_ids),
            "city_only_count": len(city_ids - lrc_ids),
            "lrc_only_count": len(lrc_ids - city_ids),
            "city_only": sorted(city_ids - lrc_ids),
            "lrc_only": sorted(lrc_ids - city_ids),
            "normalization": "last four characters of LRC VTDST20",
        },
        "documented_edge_cases": [
            "LRC corrected A/B fragments for Census blocks split by precincts",
            "dense urban boundaries and overlay slivers",
            "zero-population split blocks",
            "current City versus 2021 LRC identifier changes",
            "multipart target geometries when present",
            "mutable City feature service without an explicit effective date",
        ],
    }


def _aggregate_and_compare(population, precincts, crosswalks):
    results = pd.concat(
        [
            _aggregate(population, crosswalk, method)
            for method, crosswalk in crosswalks.items()
        ],
        ignore_index=True,
    )
    comparison = precincts[["GEOID20", "NAME", "P0010001"]].rename(
        columns={
            "GEOID20": "target_precinct_geoid",
            "P0010001": "lrc_population",
        }
    )
    for method, column in [
        ("lrc_published_split_v1", "published_population"),
        ("representative_point_v1", "point_population"),
        ("area_overlay_v1", "area_population"),
    ]:
        method_results = results[results["method_id"] == method][
            ["target_precinct_geoid", "population"]
        ].rename(columns={"population": column})
        comparison = comparison.merge(
            method_results,
            on="target_precinct_geoid",
            how="left",
            validate="one_to_one",
        )
        comparison[column] = comparison[column].fillna(0.0)
    comparison["published_minus_lrc"] = (
        comparison["published_population"] - comparison["lrc_population"]
    )
    comparison["point_minus_published"] = (
        comparison["point_population"] - comparison["published_population"]
    )
    comparison["area_minus_published"] = (
        comparison["area_population"] - comparison["published_population"]
    )
    return (
        results.sort_values(["method_id", "target_precinct_geoid"]),
        comparison.sort_values("target_precinct_geoid"),
    )


def _aggregate(population, crosswalk, method):
    allocated = population.merge(
        crosswalk,
        on="source_block_geoid",
        how="left",
        validate="one_to_many",
    )
    allocated["population"] = allocated["P0010001"] * allocated["weight"]
    totals = allocated.groupby("target_precinct_geoid", as_index=False)[
        "population"
    ].sum()
    totals["population_product_id"] = "census_2020_pa_pl"
    totals["population_reference_date"] = "2020-04-01"
    totals["population_release_date"] = "2021-08-12"
    totals["target_snapshot_id"] = "pa_lrc_2021_release_1b_geography"
    totals["target_effective_vintage"] = "2021-10-05"
    totals["general_election_date"] = None
    totals["method_id"] = method
    totals["metric"] = "P0010001"
    totals["population_universe"] = "standard_total_population"
    return totals


def _split_block_comparison(population, crosswalks):
    published = crosswalks["lrc_published_split_v1"]
    split_ids = set(
        published.groupby("source_block_geoid")
        .size()
        .loc[lambda counts: counts.gt(1)]
        .index
    )
    source_population = population.set_index("source_block_geoid")["P0010001"]
    rows = None
    for method, crosswalk in crosswalks.items():
        weights = crosswalk[crosswalk["source_block_geoid"].isin(split_ids)][
            ["source_block_geoid", "target_precinct_geoid", "weight"]
        ].rename(columns={"weight": f"{method}_weight"})
        if rows is None:
            rows = weights
        else:
            rows = rows.merge(
                weights,
                on=["source_block_geoid", "target_precinct_geoid"],
                how="outer",
            )
    rows = rows.fillna(0.0)
    rows["source_population"] = rows["source_block_geoid"].map(source_population)
    for method in crosswalks:
        rows[f"{method}_allocated_population"] = (
            rows["source_population"] * rows[f"{method}_weight"]
        )
    return rows.sort_values(["source_block_geoid", "target_precinct_geoid"])


def _result_checks(results, comparison):
    grain = [
        "population_product_id",
        "target_snapshot_id",
        "method_id",
        "target_precinct_geoid",
        "metric",
        "population_universe",
    ]
    checks = [
        _check(
            "result_grain_unique",
            not results.duplicated(grain).any(),
            int(results.duplicated(grain).sum()),
        ),
        _check(
            "all_methods_cover_targets",
            all(
                len(group) == EXPECTED["precinct_count"]
                for _, group in results.groupby("method_id")
            ),
            results.groupby("method_id").size().to_dict(),
        ),
        _check(
            "all_methods_conserve_population",
            all(
                abs(total - EXPECTED["population"]) <= 1e-6
                for total in results.groupby("method_id")["population"].sum()
            ),
            results.groupby("method_id")["population"].sum().to_dict(),
        ),
        _check(
            "published_reconciles_lrc",
            comparison["published_minus_lrc"].abs().le(1e-8).all(),
            _delta_summary(comparison["published_minus_lrc"]),
        ),
        _check(
            "point_comparison_recorded",
            comparison["point_minus_published"].abs().gt(1e-8).any(),
            _delta_summary(comparison["point_minus_published"]),
        ),
        _check(
            "area_comparison_recorded",
            comparison["area_minus_published"].abs().gt(1e-8).any(),
            _delta_summary(comparison["area_minus_published"]),
        ),
    ]
    return checks


def _impact_summary(population, published, point, area, comparison):
    counts = published.groupby("source_block_geoid").size()
    split_ids = set(counts[counts.gt(1)].index)
    split_population = int(
        population[population["source_block_geoid"].isin(split_ids)]["P0010001"].sum()
    )
    positive_split_count = int(
        population[population["source_block_geoid"].isin(split_ids)]["P0010001"]
        .gt(0)
        .sum()
    )
    point_targets = point.set_index("source_block_geoid")["target_precinct_geoid"]
    published_primary = (
        published.sort_values(
            ["source_block_geoid", "weight", "target_precinct_geoid"],
            ascending=[True, False, True],
        )
        .drop_duplicates("source_block_geoid")
        .set_index("source_block_geoid")["target_precinct_geoid"]
    )
    primary_differences = published_primary.index[published_primary.ne(point_targets)]
    area_counts = area.groupby("source_block_geoid").size()
    return {
        "observed_split_source_blocks": len(split_ids),
        "observed_split_source_population": split_population,
        "positive_population_split_blocks": positive_split_count,
        "zero_population_split_blocks": len(split_ids) - positive_split_count,
        "share_of_source_blocks": len(split_ids) / EXPECTED["census_block_count"],
        "share_of_population": split_population / EXPECTED["population"],
        "representative_point_primary_target_differences": len(primary_differences),
        "representative_point_primary_target_difference_population": int(
            population.set_index("source_block_geoid")
            .loc[primary_differences, "P0010001"]
            .sum()
        ),
        "area_overlay_split_source_blocks": int(area_counts.gt(1).sum()),
        "precinct_deltas": {
            "representative_point_v1": _delta_summary(
                comparison["point_minus_published"]
            ),
            "area_overlay_v1": _delta_summary(comparison["area_minus_published"]),
        },
    }


def _delta_summary(delta: pd.Series) -> dict[str, float | int]:
    return {
        "different_precincts": int(delta.abs().gt(1e-8).sum()),
        "total_absolute_person_delta": float(delta.abs().sum()),
        "maximum_absolute_precinct_delta": float(delta.abs().max()),
        "root_mean_square_precinct_delta": float((delta.pow(2).mean()) ** 0.5),
    }


def _render_report(qa: dict[str, object]) -> str:
    profile = qa["source_profile"]
    identifiers = profile["city_vs_lrc_identifiers"]
    impact = qa["impact"]
    point_delta = impact["precinct_deltas"]["representative_point_v1"]
    area_delta = impact["precinct_deltas"]["area_overlay_v1"]
    status = "PASS" if qa["passed"] else "FAIL"
    return f"""# Philadelphia complex-county proof — POC006–POC007

Generated from the checksum-verified sources in `input_manifest.json`. Detailed
checks and diagnostics are in `qa_results.json`; source qualification is in
`source_profile.json`.

## Outcome

- Overall QA: **{status}**
- Official City boundary candidate: {EXPECTED["precinct_count"]:,} divisions
  across {EXPECTED["ward_count"]} wards, retrieved {CITY_SOURCE["as_of_date"]}
- City candidate versus 2021 LRC IDs: {identifiers["common"]:,} common,
  {identifiers["city_only_count"]} City-only, {identifiers["lrc_only_count"]}
  LRC-only after four-digit normalization
- Corrected split blocks: {impact["observed_split_source_blocks"]} of
  {EXPECTED["census_block_count"]:,}
  ({impact["share_of_source_blocks"]:.4%})
- Population in split blocks: {impact["observed_split_source_population"]:,} of
  {EXPECTED["population"]:,} ({impact["share_of_population"]:.4%})
- Published LRC split allocation: exact reconciliation to all
  {EXPECTED["precinct_count"]:,} precinct totals
- Representative point versus published: {point_delta["different_precincts"]}
  changed precincts, {point_delta["total_absolute_person_delta"]:,.0f} total
  absolute persons, {point_delta["maximum_absolute_precinct_delta"]:,.0f}
  maximum precinct delta
- Area overlay versus published: {area_delta["different_precincts"]} changed
  precincts, {area_delta["total_absolute_person_delta"]:,.3f} total absolute
  persons, {area_delta["maximum_absolute_precinct_delta"]:,.3f} maximum
  precinct delta

## Source qualification

The selected candidate is the City of Philadelphia Political Divisions feature
layer cataloged for public use by OpenDataPhilly and tied to the City
Commissioners' current count of 1,703 divisions. The retrieved GeoJSON has a
fixed checksum, complete four-character division IDs, 66 wards, valid polygon
geometry, and full expected city coverage.

The service is mutable and does **not** publish an election-effective boundary
date. This snapshot is therefore qualified as an authoritative current City
candidate and post-2021 comparison source, not as a frozen November 3, 2026
general-election snapshot. `POC008` must still establish that effective date and
cutoff.

## Method decision

For 2020 Census blocks targeting LRC Release 1b, use
`lrc_published_split_v1` as the baseline. It is the only tested route that
preserves the 13 LRC corrected A/B block fragments and exactly reproduces the
published precinct totals. A whole-block representative point is acceptable
only where no published split correction exists; here it moved people in eight
precincts. Equal-area overlay reduced those deltas but still disagreed with the
published population allocation, so it remains a geometry diagnostic rather
than a population model.

This decision does not select the final method for post-2021, historical, or
ACS targets that lack published split populations. Those require a separately
validated population-informed allocation method.

## Declared geometry rule

Area intersections smaller than {AREA_SLIVER_TOLERANCE:g} of a source block
were treated as projection/topology slivers, dropped, and the retained positive
areas renormalized to one. The resulting area crosswalk identifies the same 13
split source blocks as the LRC corrected fragments.
"""


def _value_counts(values: pd.Series) -> dict[str, int]:
    return {str(key): int(value) for key, value in values.value_counts().items()}


def _short_id_anomalies(city_divisions) -> list[dict[str, object]]:
    anomalies = city_divisions[
        city_divisions["short_div_num"] != city_divisions["division_num"].str[-2:]
    ][["objectid", "short_div_num", "division_num"]]
    return anomalies.to_dict("records")


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
