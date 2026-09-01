"""Build and validate the POC019 population-product/election availability map."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from census_pa_poc.sources import sha256
from census_pa_poc.validation import all_pass, logical_frame_hash, write_json

OUTPUT_COLUMNS = [
    "pairing_id",
    "election_id",
    "election_date",
    "cycle_role",
    "cutoff_policy",
    "cutoff_date",
    "fixed_precinct_snapshot_id",
    "senate_plan_id",
    "product_id",
    "product_family",
    "reference_start",
    "reference_end",
    "release_date_published",
    "release_date_precision",
    "release_date_earliest",
    "release_date_latest",
    "metric",
    "source_geography_id",
    "population_universe",
    "product_processing_status",
    "allocation_readiness",
    "accepted_method_id",
    "reference_period_complete_by_cutoff",
    "availability_by_cutoff",
    "exact_release_days_before_cutoff",
    "candidate_for_poc016",
    "availability_notes",
]

INPUTS = {
    "election_cycles": {
        "relative_path": "mappings/election_cycles.csv",
        "sha256": "8d33613de9358d0cdc80687db05e5dbc14798be4d2e9a23e87be157b12a6667e",
        "role": "19 even-year Pennsylvania general elections and period Senate plans",
    },
    "population_periods": {
        "relative_path": "mappings/population_periods.csv",
        "sha256": "17212780851d85f5626b19761db7d6fe2ce0899a76ad119da04da893aaf883e2",
        "role": "four decennial product identities and release precision",
    },
    "acs5_products": {
        "relative_path": "mappings/acs5_products.csv",
        "sha256": "47f3a18014161a4fa435ca57ac534fa0a4ecd43bf6b92b230e2545940441ef4a",
        "role": "16 ACS five-year product periods and exact release dates",
    },
}

DECENNIAL_METHODS = {
    "dec_1990": "relationship_tiger_face_area_1990_v1",
    "dec_2000": "relationship_atomic_area_2000_v1",
    "dec_2010": "relationship_atomic_area_2010_v1",
    "dec_2020": "lrc_published_split_v1",
}


def run(root: Path) -> dict[str, object]:
    """Create the complete product-by-election matrix and QA artifacts."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc019"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    require_manifest_hashes(manifest)

    elections = load_elections(root / INPUTS["election_cycles"]["relative_path"])
    products = load_products(
        root / INPUTS["population_periods"]["relative_path"],
        root / INPUTS["acs5_products"]["relative_path"],
    )
    pairings = build_pairings(elections, products)
    output_path = root / "mappings/population_election_availability_v1.csv"
    write_status = write_immutable_csv(pairings, output_path)

    checks = build_checks(elections, products, pairings)
    available_counts = (
        pairings[pairings["availability_by_cutoff"].eq("available")]
        .groupby("election_id")
        .size()
        .reindex(elections["election_id"], fill_value=0)
        .astype(int)
        .to_dict()
    )
    qa = {
        "task": "POC019",
        "cutoff_policy": "general_election_day",
        "product_count": len(products),
        "election_count": len(elections),
        "pairing_count": len(pairings),
        "available_pairing_count": int(
            pairings["availability_by_cutoff"].eq("available").sum()
        ),
        "not_available_pairing_count": int(
            pairings["availability_by_cutoff"].eq("not_available").sum()
        ),
        "indeterminate_pairing_count": int(
            pairings["availability_by_cutoff"].eq("indeterminate").sum()
        ),
        "available_product_counts_by_election": available_counts,
        "output_write": write_status,
        "output_logical_sha256": logical_frame_hash(
            pairings, ["election_date", "product_id"]
        ),
        "checks": checks,
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(render_report(qa, products))
    if not qa["passed"]:
        raise RuntimeError("POC019 QA failed; inspect artifacts/poc019/qa_results.json")
    return qa


def load_elections(path: Path) -> pd.DataFrame:
    result = pd.read_csv(path, dtype="string", keep_default_na=False)
    return result.sort_values("election_date").reset_index(drop=True)


def load_products(periods_path: Path, acs_path: Path) -> pd.DataFrame:
    periods = pd.read_csv(periods_path, dtype="string", keep_default_na=False)
    decennial = periods[periods["series_id"].isin(DECENNIAL_METHODS)].copy()
    decennial = decennial.rename(
        columns={
            "series_id": "product_id",
            "reference_start": "reference_start",
            "reference_end": "reference_end",
            "release_date": "release_date_published",
            "source_geography": "source_geography_id",
            "processing_status": "product_processing_status",
        }
    )
    decennial["population_universe"] = "standard_total_population"
    decennial["allocation_readiness"] = "statewide_result_proven"
    decennial["accepted_method_id"] = decennial["product_id"].map(DECENNIAL_METHODS)
    decennial = add_release_bounds(decennial)

    acs = pd.read_csv(acs_path, dtype="string", keep_default_na=False).rename(
        columns={
            "period_start": "reference_start",
            "period_end": "reference_end",
            "release_date": "release_date_published",
            "processing_status": "product_processing_status",
        }
    )
    acs["metric"] = acs["estimate_variable"] + "/" + acs["moe_variable"]
    representative = acs["product_id"].eq("acs5_2015")
    acs["allocation_readiness"] = "inventory_only_requires_poc016_support_selection"
    acs.loc[representative, "allocation_readiness"] = (
        "representative_statewide_method_proven"
    )
    acs["accepted_method_id"] = ""
    acs.loc[representative, "accepted_method_id"] = (
        "census2010_population_atomic_acs5_2015_v1"
    )
    acs = add_release_bounds(acs)

    columns = [
        "product_id",
        "product_family",
        "reference_start",
        "reference_end",
        "release_date_published",
        "release_date_precision",
        "release_date_earliest",
        "release_date_latest",
        "metric",
        "source_geography_id",
        "population_universe",
        "product_processing_status",
        "allocation_readiness",
        "accepted_method_id",
    ]
    return (
        pd.concat([decennial[columns], acs[columns]], ignore_index=True)
        .sort_values(["release_date_earliest", "product_id"], kind="stable")
        .reset_index(drop=True)
    )


def add_release_bounds(products: pd.DataFrame) -> pd.DataFrame:
    result = products.copy()
    bounds = result["release_date_published"].map(release_bounds)
    result["release_date_precision"] = bounds.map(lambda value: value[0])
    result["release_date_earliest"] = bounds.map(lambda value: value[1])
    result["release_date_latest"] = bounds.map(lambda value: value[2])
    return result


def release_bounds(value: str) -> tuple[str, str, str]:
    if len(value) == 10:
        timestamp = pd.Timestamp(value)
        exact = timestamp.strftime("%Y-%m-%d")
        return "exact_day", exact, exact
    if len(value) == 4 and value.isdigit():
        return "year_only", f"{value}-01-01", f"{value}-12-31"
    raise ValueError(f"Unsupported release date precision: {value}")


def build_pairings(elections: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    cycles = elections.assign(_join_key=1)
    sources = products.assign(_join_key=1)
    paired = cycles.merge(sources, on="_join_key", validate="many_to_many").drop(
        columns="_join_key"
    )
    paired["pairing_id"] = paired["election_id"] + "__" + paired["product_id"]
    paired["cutoff_policy"] = "general_election_day"
    paired["cutoff_date"] = paired["election_date"]
    paired["fixed_precinct_snapshot_id"] = paired["precinct_snapshot_id"]

    cutoff = pd.to_datetime(paired["cutoff_date"])
    reference_end = pd.to_datetime(paired["reference_end"])
    release_earliest = pd.to_datetime(paired["release_date_earliest"])
    release_latest = pd.to_datetime(paired["release_date_latest"])
    paired["reference_period_complete_by_cutoff"] = np_where(
        reference_end.le(cutoff), "true", "false"
    )
    paired["availability_by_cutoff"] = [
        classify_availability(earliest, latest, election)
        for earliest, latest, election in zip(
            release_earliest, release_latest, cutoff, strict=True
        )
    ]
    exact = paired["release_date_precision"].eq("exact_day")
    paired["exact_release_days_before_cutoff"] = pd.Series(
        pd.NA, index=paired.index, dtype="Int64"
    )
    paired.loc[exact, "exact_release_days_before_cutoff"] = (
        cutoff[exact] - release_earliest[exact]
    ).dt.days.astype("Int64")
    paired["candidate_for_poc016"] = np_where(
        paired["availability_by_cutoff"].eq("available"), "true", "false"
    )
    paired["availability_notes"] = ""
    year_only = paired["release_date_precision"].eq("year_only")
    paired.loc[year_only, "availability_notes"] = (
        "exact Pennsylvania release day unresolved; year bounds still classify this cutoff"
    )
    return (
        paired[OUTPUT_COLUMNS]
        .sort_values(["election_date", "product_id"], kind="stable")
        .reset_index(drop=True)
    )


def np_where(condition: pd.Series, yes: str, no: str) -> pd.Series:
    return condition.map({True: yes, False: no}).astype("string")


def classify_availability(
    release_earliest: pd.Timestamp,
    release_latest: pd.Timestamp,
    cutoff: pd.Timestamp,
) -> str:
    if release_latest <= cutoff:
        return "available"
    if release_earliest > cutoff:
        return "not_available"
    return "indeterminate"


def build_checks(
    elections: pd.DataFrame,
    products: pd.DataFrame,
    pairings: pd.DataFrame,
) -> list[dict[str, object]]:
    expected_counts = {
        "pa_general_1990": 0,
        "pa_general_1992": 1,
        "pa_general_1994": 1,
        "pa_general_1996": 1,
        "pa_general_1998": 1,
        "pa_general_2000": 1,
        "pa_general_2002": 2,
        "pa_general_2004": 2,
        "pa_general_2006": 2,
        "pa_general_2008": 2,
        "pa_general_2010": 2,
        "pa_general_2012": 5,
        "pa_general_2014": 7,
        "pa_general_2016": 9,
        "pa_general_2018": 11,
        "pa_general_2020": 13,
        "pa_general_2022": 16,
        "pa_general_2024": 18,
        "pa_general_2026": 20,
    }
    observed_counts = (
        pairings[pairings["availability_by_cutoff"].eq("available")]
        .groupby("election_id")
        .size()
        .reindex(elections["election_id"], fill_value=0)
        .astype(int)
        .to_dict()
    )
    by_product = pairings.sort_values("election_date").groupby("product_id")[
        "availability_by_cutoff"
    ]
    monotonic_failures = [
        product_id
        for product_id, values in by_product
        if not availability_is_monotonic(values.tolist())
    ]
    release_1990 = products[products["product_id"].eq("dec_1990")].iloc[0]
    pairing_1990 = pairings[pairings["product_id"].eq("dec_1990")].set_index(
        "election_id"
    )
    required = [
        "reference_start",
        "reference_end",
        "release_date_published",
        "election_date",
        "fixed_precinct_snapshot_id",
        "senate_plan_id",
        "availability_by_cutoff",
    ]
    return [
        check("election_count", len(elections) == 19, len(elections)),
        check("product_count", len(products) == 20, len(products)),
        check("pairing_count", len(pairings) == 380, len(pairings)),
        check(
            "pairing_ids_unique",
            pairings["pairing_id"].is_unique,
            int(pairings["pairing_id"].nunique()),
        ),
        check(
            "every_product_crossed_with_every_election",
            bool(pairings.groupby("election_id")["product_id"].nunique().eq(20).all())
            and bool(
                pairings.groupby("product_id")["election_id"].nunique().eq(19).all()
            ),
            {
                "minimum_products_per_election": int(
                    pairings.groupby("election_id")["product_id"].nunique().min()
                ),
                "minimum_elections_per_product": int(
                    pairings.groupby("product_id")["election_id"].nunique().min()
                ),
            },
        ),
        check(
            "required_fields_complete",
            bool(pairings[required].ne("").all().all()),
            pairings[required].eq("").sum().to_dict(),
        ),
        check(
            "fixed_target_constant",
            pairings["fixed_precinct_snapshot_id"]
            .eq("pa_lrc_2021_release_1b_geography")
            .all(),
            pairings["fixed_precinct_snapshot_id"].unique().tolist(),
        ),
        check(
            "all_cycle_senate_plans_retained",
            pairings.groupby("election_id")["senate_plan_id"].nunique().eq(1).all(),
            int(pairings["senate_plan_id"].nunique()),
        ),
        check(
            "availability_counts_by_election",
            observed_counts == expected_counts,
            observed_counts,
        ),
        check(
            "availability_monotonic_by_product",
            not monotonic_failures,
            monotonic_failures,
        ),
        check(
            "no_indeterminate_pairings",
            not pairings["availability_by_cutoff"].eq("indeterminate").any(),
            int(pairings["availability_by_cutoff"].eq("indeterminate").sum()),
        ),
        check(
            "1990_release_precision_preserved",
            release_1990["release_date_precision"] == "year_only"
            and release_1990["release_date_earliest"] == "1991-01-01"
            and release_1990["release_date_latest"] == "1991-12-31",
            release_1990[
                [
                    "release_date_published",
                    "release_date_precision",
                    "release_date_earliest",
                    "release_date_latest",
                ]
            ].to_dict(),
        ),
        check(
            "1990_release_bounds_classify_all_cycles",
            pairing_1990.loc["pa_general_1990", "availability_by_cutoff"]
            == "not_available"
            and pairing_1990.drop(index="pa_general_1990")["availability_by_cutoff"]
            .eq("available")
            .all(),
            pairing_1990["availability_by_cutoff"].value_counts().to_dict(),
        ),
        check(
            "poc016_candidates_equal_available_pairings",
            pairings["candidate_for_poc016"]
            .eq(
                np_where(
                    pairings["availability_by_cutoff"].eq("available"),
                    "true",
                    "false",
                )
            )
            .all(),
            pairings["candidate_for_poc016"].value_counts().to_dict(),
        ),
    ]


def availability_is_monotonic(values: list[str]) -> bool:
    ranks = {"not_available": 0, "indeterminate": 1, "available": 2}
    numeric = [ranks[value] for value in values]
    return numeric == sorted(numeric)


def write_immutable_csv(frame: pd.DataFrame, path: Path) -> str:
    expected_hash = logical_frame_hash(frame, ["election_date", "product_id"])
    if path.exists():
        observed = pd.read_csv(path, dtype="string", keep_default_na=False)
        observed_hash = logical_frame_hash(observed, ["election_date", "product_id"])
        if observed_hash != expected_hash:
            raise RuntimeError(
                f"Refusing to overwrite changed versioned mapping: {path}"
            )
        return "reused_identical"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n")
    return "created"


def build_manifest(root: Path) -> dict[str, object]:
    entries = []
    for source_id, source in INPUTS.items():
        path = root / source["relative_path"]
        entries.append(
            {
                "source_id": source_id,
                **source,
                "retrieval_timestamp": datetime.fromtimestamp(
                    path.stat().st_mtime, UTC
                ).isoformat(),
                "size_bytes": path.stat().st_size,
                "observed_sha256": sha256(path),
            }
        )
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


def render_report(qa: dict[str, object], products: pd.DataFrame) -> str:
    counts = qa["available_product_counts_by_election"]
    return f"""# POC019 population-product/election availability map

Status: **{"PASS" if qa["passed"] else "FAIL"}**

- Population products: {qa["product_count"]}
- General elections: {qa["election_count"]}
- Candidate pairings: {qa["pairing_count"]}
- Available-by-election-day pairings: {qa["available_pairing_count"]}
- Released-after-election pairings: {qa["not_available_pairing_count"]}
- Indeterminate pairings: {qa["indeterminate_pairing_count"]}
- Products available for 1990: {counts["pa_general_1990"]}
- Products available for 2012: {counts["pa_general_2012"]}
- Products available for 2026: {counts["pa_general_2026"]}
- Output logical SHA-256: `{qa["output_logical_sha256"]}`

The matrix crosses all four decennial products and all 16 inventoried ACS
five-year products with all 19 even-year general elections. General-election day
is the information cutoff. Every row retains the product reference period,
published release precision and bounds, election date, fixed target, period
Senate plan, allocation readiness, and availability classification.

The 1990 STF 1B release remains year-only (`1991`). Its conservative bounds are
1991-01-01 through 1991-12-31, which still classify every POC cycle: unavailable
for November 1990 and available from November 1992 onward. No release day is
invented. Availability creates candidates for POC016; it does not select model
features or imply that every inventoried ACS product already has a vintage-safe
support surface.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC019 {'passed' if qa['passed'] else 'failed'}")


if __name__ == "__main__":
    main()
