"""Validate the POC030 precinct archive and active direct-only surface."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from census_pa_poc.data_explorer import load_explorer_tables
from census_pa_poc.sources import sha256
from census_pa_poc.validation import all_pass, write_json

MANIFEST_PATH = "mappings/poc030_archive_manifest_v1.csv"
ACTIVE_SELECTOR_MAPPINGS = [
    "mappings/legislative_plans_v1.csv",
    "mappings/legislative_population_partitions_v1.csv",
    "mappings/legislative_metrics_v1.csv",
    "mappings/population_periods.csv",
    "mappings/crosswalk_methods.csv",
]


def run(root: Path) -> dict[str, object]:
    """Run repository-level archive and direct-surface checks."""
    root = root.resolve()
    manifest_path = root / MANIFEST_PATH
    manifest = pd.read_csv(manifest_path, dtype="string", keep_default_na=False)
    missing_archived = archive_path_failures(root, manifest)
    stale_originals = stale_original_failures(root, manifest)
    missing_retained = retained_path_failures(root, manifest)
    mapping_precinct_hits = selector_mapping_precinct_hits(root)
    explorer = load_explorer_tables(root)
    total_results = explorer.results[
        explorer.results["metric_id"].eq("total_population")
    ]
    result_keys = total_results[
        ["population_product_id", "target_chamber", "target_plan_id"]
    ].drop_duplicates()
    checks = [
        check("archive_manifest_rows", len(manifest) >= 70, len(manifest)),
        check("all_archived_paths_exist", not missing_archived, missing_archived),
        check("archived_originals_inactive", not stale_originals, stale_originals),
        check("retained_shared_paths_exist", not missing_retained, missing_retained),
        check(
            "active_selector_mappings_have_no_precinct_fields",
            not mapping_precinct_hits,
            mapping_precinct_hits,
        ),
        check("direct_partition_count", len(result_keys) == 78, len(result_keys)),
        check(
            "direct_product_count",
            total_results["population_product_id"].nunique() == 20,
            int(total_results["population_product_id"].nunique()),
        ),
        check(
            "both_direct_chambers",
            set(explorer.results["target_chamber"]) == {"house", "senate"},
            sorted(explorer.results["target_chamber"].unique().tolist()),
        ),
        check(
            "explorer_has_no_precinct_columns",
            not any("precinct" in column.lower() for column in explorer.results),
            list(explorer.results.columns),
        ),
    ]
    qa = {
        "task": "POC030",
        "stage": "archive_and_active_surface_acceptance",
        "manifest_path": MANIFEST_PATH,
        "manifest_sha256": sha256(manifest_path),
        "manifest_rows": len(manifest),
        "archived_rows": int(
            manifest["disposition"].str.startswith("archived").sum()
        ),
        "retained_shared_rows": int(
            manifest["disposition"].eq("retained_shared").sum()
        ),
        "direct_partition_count": len(result_keys),
        "checks": checks,
        "passed": all_pass(checks),
    }
    artifact_dir = root / "artifacts/poc030"
    write_json(artifact_dir / "archive_qa.json", qa)
    (artifact_dir / "archive_report.md").write_text(render_report(qa))
    if not qa["passed"]:
        raise RuntimeError("POC030 archive validation failed; inspect archive_qa.json")
    return qa


def archive_path_failures(root: Path, manifest: pd.DataFrame) -> list[str]:
    archived = manifest[
        manifest["disposition"].isin(
            ["archived", "archived_group", "replaced_and_archived"]
        )
    ]
    return [
        path
        for path in archived["archive_path"]
        if not path or not (root / path).exists()
    ]


def stale_original_failures(root: Path, manifest: pd.DataFrame) -> list[str]:
    archived = manifest[manifest["disposition"].eq("archived")]
    return [path for path in archived["original_path"] if (root / path).exists()]


def retained_path_failures(root: Path, manifest: pd.DataFrame) -> list[str]:
    retained = manifest[
        manifest["disposition"].isin(["retained_shared", "retained_direct"])
    ]
    return [path for path in retained["original_path"] if not (root / path).exists()]


def selector_mapping_precinct_hits(root: Path) -> list[str]:
    hits = []
    for relative_path in ACTIVE_SELECTOR_MAPPINGS:
        frame = pd.read_csv(root / relative_path, dtype="string", keep_default_na=False)
        precinct_columns = [
            column for column in frame.columns if "precinct" in column.lower()
        ]
        precinct_values = frame.apply(
            lambda column: column.str.contains("precinct", case=False).any()
        )
        if precinct_columns or precinct_values.any():
            hits.append(relative_path)
    return hits


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_report(qa: dict[str, object]) -> str:
    return f"""# POC030 archive acceptance

Status: **{"PASS" if qa["passed"] else "FAIL"}**

- Manifest rows: {qa["manifest_rows"]}
- Archived rows: {qa["archived_rows"]}
- Retained shared rows: {qa["retained_shared_rows"]}
- Active direct partitions: {qa["direct_partition_count"]}
- Manifest SHA-256: `{qa["manifest_sha256"]}`

Precinct-only code, mappings, documentation, proof artifacts, and generated
data are preserved under `archive/precinct_v1/`. Active selector mappings and
the explorer use only direct House/Senate products. Shared source parsers and
provenance manifests required by direct replay remain active and are declared
in the manifest.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC030 archive validation passed: {qa['passed']}")


if __name__ == "__main__":
    main()
