"""Validate the POC014 inventory of ACS five-year population products."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from census_pa_poc.sources import sha256
from census_pa_poc.validation import all_pass, logical_frame_hash, write_json

EXPECTED_YEARS = set(range(2009, 2025))


def run(root: Path) -> dict[str, object]:
    """Validate inventory fields and checksum-frozen public API metadata."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc014"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    inventory = load_inventory(root / "mappings/acs5_products.csv")
    manifest, profiles = build_metadata_manifest(root, inventory)
    write_json(artifact_dir / "api_metadata_manifest.json", manifest)
    write_json(artifact_dir / "product_profiles.json", profiles)

    checks = build_checks(root, inventory, manifest, profiles)
    qa = {
        "task": "POC014",
        "inventory_logical_sha256": logical_frame_hash(inventory, ["estimate_year"]),
        "checks": checks,
        "available_product_count": len(inventory),
        "api_block_group_product_count": int(
            inventory["api_block_group_supported"].sum()
        ),
        "summary_file_required_product_count": int(
            (~inventory["api_block_group_supported"]).sum()
        ),
        "api_key_required_for_data_queries_as_of": "2026-08-29",
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(render_report(qa, inventory))
    if not qa["passed"]:
        raise RuntimeError("POC014 QA failed; inspect artifacts/poc014/qa_results.json")
    return qa


def load_inventory(path: Path) -> pd.DataFrame:
    result = pd.read_csv(path, dtype="string", keep_default_na=False)
    result["estimate_year"] = result["estimate_year"].astype("int64")
    result["api_block_group_supported"] = result["api_block_group_supported"].eq("true")
    return result.sort_values("estimate_year").reset_index(drop=True)


def build_metadata_manifest(
    root: Path, inventory: pd.DataFrame
) -> tuple[dict[str, object], dict[str, object]]:
    entries = []
    profiles = {}
    for row in inventory.itertuples(index=False):
        variables_path = (
            root / f"data/raw/acs5_api_metadata/{row.estimate_year}_B01003.json"
        )
        geography_path = (
            root / f"data/raw/acs5_api_metadata/{row.estimate_year}_geography.json"
        )
        entries.extend(
            [
                metadata_entry(
                    row.product_id,
                    "B01003_variables",
                    row.variables_metadata_url,
                    row.variables_metadata_sha256,
                    variables_path,
                ),
                metadata_entry(
                    row.product_id,
                    "geography",
                    row.geography_metadata_url,
                    row.geography_metadata_sha256,
                    geography_path,
                ),
            ]
        )
        profiles[row.product_id] = profile_product_metadata(
            variables_path,
            geography_path,
            row.estimate_variable,
            row.moe_variable,
        )
    return {"manifest_version": "1.0.0", "entries": entries}, profiles


def metadata_entry(
    product_id: str,
    metadata_type: str,
    url: str,
    expected_sha256: str,
    path: Path,
) -> dict[str, object]:
    return {
        "product_id": product_id,
        "metadata_type": metadata_type,
        "producer": "U.S. Census Bureau",
        "url": url,
        "retrieval_timestamp": datetime.fromtimestamp(
            path.stat().st_mtime, UTC
        ).isoformat(),
        "size_bytes": path.stat().st_size,
        "expected_sha256": expected_sha256,
        "observed_sha256": sha256(path),
        "relative_path": str(path),
        "license_access": "Public federal metadata; cite U.S. Census Bureau",
    }


def profile_product_metadata(
    variables_path: Path,
    geography_path: Path,
    estimate_variable: str,
    moe_variable: str,
) -> dict[str, object]:
    variables = json.loads(variables_path.read_text())["variables"]
    geographies = json.loads(geography_path.read_text())["fips"]
    block_groups = [item for item in geographies if item["name"] == "block group"]
    return {
        "estimate": variable_profile(variables.get(estimate_variable)),
        "margin_of_error": variable_profile(variables.get(moe_variable)),
        "block_group_supported_by_api_manifest": bool(block_groups),
        "block_group_geography": block_groups,
    }


def variable_profile(value: dict[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        key: value.get(key)
        for key in ["label", "concept", "predicateType", "group", "universe"]
    }


def build_checks(
    root: Path,
    inventory: pd.DataFrame,
    manifest: dict[str, object],
    profiles: dict[str, object],
) -> list[dict[str, object]]:
    years = set(inventory["estimate_year"])
    required = [
        "product_id",
        "period_start",
        "period_end",
        "release_date",
        "source_geography_id",
        "estimate_variable",
        "moe_variable",
        "api_dataset_url",
        "variables_metadata_url",
        "geography_metadata_url",
        "primary_access_route",
        "summary_file_url",
        "release_source_url",
    ]
    expected_starts = pd.to_datetime(
        inventory["estimate_year"].sub(4).astype("string") + "-01-01"
    )
    expected_ends = pd.to_datetime(
        inventory["estimate_year"].astype("string") + "-12-31"
    )
    starts = pd.to_datetime(inventory["period_start"])
    ends = pd.to_datetime(inventory["period_end"])
    releases = pd.to_datetime(inventory["release_date"])
    checksum_failures = [
        entry["product_id"] + ":" + entry["metadata_type"]
        for entry in manifest["entries"]
        if entry["expected_sha256"] != entry["observed_sha256"]
    ]
    profile_failures = [
        product_id
        for product_id, profile in profiles.items()
        if not profile_passes(profile)
    ]
    geography_mismatches = [
        row.product_id
        for row in inventory.itertuples(index=False)
        if profiles[row.product_id]["block_group_supported_by_api_manifest"]
        != row.api_block_group_supported
    ]
    route_mismatches = [
        row.product_id
        for row in inventory.itertuples(index=False)
        if not route_matches(row)
    ]
    period_registry = pd.read_csv(
        root / "mappings/population_periods.csv", dtype="string", keep_default_na=False
    )
    unavailable_1990s = period_registry.loc[
        period_registry["series_id"].eq("mid_1990s")
    ]
    return [
        check("product_count", len(inventory) == len(EXPECTED_YEARS), len(inventory)),
        check("estimate_years_complete", years == EXPECTED_YEARS, sorted(years)),
        check(
            "product_ids_unique",
            inventory["product_id"].is_unique,
            int(inventory["product_id"].nunique()),
        ),
        check(
            "required_fields_complete",
            bool(inventory[required].ne("").all().all()),
            inventory[required].eq("").sum().to_dict(),
        ),
        check(
            "five_year_period_starts_exact",
            starts.equals(expected_starts),
            int((starts != expected_starts).sum()),
        ),
        check(
            "five_year_period_ends_exact",
            ends.equals(expected_ends),
            int((ends != expected_ends).sum()),
        ),
        check(
            "release_after_reference_period",
            bool(releases.gt(ends).all()),
            int((~releases.gt(ends)).sum()),
        ),
        check(
            "estimate_variable_exact",
            inventory["estimate_variable"].eq("B01003_001E").all(),
            inventory["estimate_variable"].unique().tolist(),
        ),
        check(
            "moe_variable_exact",
            inventory["moe_variable"].eq("B01003_001M").all(),
            inventory["moe_variable"].unique().tolist(),
        ),
        check(
            "population_universe_exact",
            inventory["population_universe"].eq("total_population").all(),
            inventory["population_universe"].unique().tolist(),
        ),
        check(
            "block_group_grain_exact",
            inventory["source_geography"].eq("census_block_group").all(),
            inventory["source_geography"].unique().tolist(),
        ),
        check(
            "metadata_entry_count",
            len(manifest["entries"]) == len(EXPECTED_YEARS) * 2,
            len(manifest["entries"]),
        ),
        check("metadata_checksums", not checksum_failures, checksum_failures),
        check("variable_metadata_semantics", not profile_failures, profile_failures),
        check(
            "api_geography_flags_match", not geography_mismatches, geography_mismatches
        ),
        check(
            "access_routes_match_api_geography", not route_mismatches, route_mismatches
        ),
        check(
            "api_key_requirement_recorded",
            inventory["api_key_requirement"]
            .eq("required_for_data_queries_as_of_2026-08-29")
            .all(),
            inventory["api_key_requirement"].unique().tolist(),
        ),
        check(
            "availability_status",
            inventory["availability_status"].eq("available").all(),
            inventory["availability_status"].value_counts().to_dict(),
        ),
        check(
            "1990s_gap_explicit",
            len(unavailable_1990s) == 1
            and unavailable_1990s.iloc[0]["availability_status"] == "no_comparable_acs",
            unavailable_1990s.to_dict("records"),
        ),
    ]


def profile_passes(profile: dict[str, object]) -> bool:
    estimate = profile["estimate"]
    moe = profile["margin_of_error"]
    return bool(
        estimate
        and moe
        and estimate["label"].startswith("Estimate")
        and moe["label"].startswith("Margin of Error")
        and estimate["predicateType"] == "int"
        and moe["predicateType"] == "int"
        and estimate["group"] == "B01003"
        and moe["group"] == "B01003"
    )


def route_matches(row: object) -> bool:
    if row.api_block_group_supported:
        return row.primary_access_route == "census_data_api_or_summary_file"
    return row.primary_access_route == "official_summary_file"


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(qa: dict[str, object], inventory: pd.DataFrame) -> str:
    first = inventory.iloc[0]
    latest = inventory.iloc[-1]
    return f"""# POC014 ACS five-year product inventory

Status: **{"PASS" if qa["passed"] else "FAIL"}**

- Available products: {qa["available_product_count"]}
- First product: {first["period_start"]} through {first["period_end"]}, released {first["release_date"]}
- Latest product: {latest["period_start"]} through {latest["period_end"]}, released {latest["release_date"]}
- Products whose API geography manifest exposes block groups: {qa["api_block_group_product_count"]}
- Products requiring the official Summary File route at block-group grain: {qa["summary_file_required_product_count"]}
- Estimate variable: `B01003_001E`
- Margin-of-error variable: `B01003_001M`
- Population universe: total population

All overlapping ACS five-year releases from 2005–2009 through 2020–2024 are
retained. The inventory does not preselect a training feature or manufacture a
1990s ACS equivalent. Release dates remain product availability dates for later
comparison with election cutoffs under `POC019`.

The public Census API variables and geography metadata are checksum-frozen for
each vintage. The 2009–2012 API geography manifests omit block groups, so those
four products use the official Summary File route. From 2013 onward, the API
manifest exposes block groups. As observed on 2026-08-29, Census requires an API
key for data queries; no credential is stored in this repository. This does not
block the inventory, but `POC015` must use a user-supplied key or Summary Files.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    run(args.root)


if __name__ == "__main__":
    main()
