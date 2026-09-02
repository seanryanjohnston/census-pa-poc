"""Validate the complete POC029 direct legislative product family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from census_pa_poc.validation import all_pass, write_json

EXPECTED_PARTITIONS = 78
EXPECTED_PRODUCTS = 20
REQUIRED_PARTITION_FIELDS = {
    "population_product_id",
    "source_geography_grain",
    "target_chamber",
    "target_plan_id",
    "target_plan_reference_vintage",
    "first_applicable_election",
    "last_applicable_election",
    "weighting_universe",
    "fallback_policy",
    "uncertainty",
    "crosswalk_logical_sha256",
    "uses_precinct_input",
    "nearest_assignment_count",
}


def run(root: Path) -> dict[str, object]:
    """Combine the accepted plan, decennial, and ACS stage evidence."""
    root = root.resolve()
    stage_dir = root / "artifacts/work/poc029"
    artifact_dir = root / "artifacts/poc029"
    plan = read_json(stage_dir / "plan_source_qa.json")
    decennial = read_json(stage_dir / "decennial_qa.json")
    acs = read_json(stage_dir / "acs_qa.json")
    profiles = decennial["profiles"] + acs["profiles"]
    keys = {
        (
            profile["population_product_id"],
            profile["target_chamber"],
            profile["target_plan_id"],
        )
        for profile in profiles
    }
    missing_declarations = declaration_failures(profiles)
    invalid_hashes = [
        partition_key(profile)
        for profile in profiles
        if not valid_sha256(profile.get("crosswalk_logical_sha256"))
        or not valid_sha256(profile.get("result_logical_sha256"))
    ]
    precinct_dependencies = [
        partition_key(profile)
        for profile in profiles
        if profile.get("uses_precinct_input") is not False
    ]
    nearest_assignments = [
        partition_key(profile)
        for profile in profiles
        if profile.get("nearest_assignment_count") != 0
    ]
    products = {profile["population_product_id"] for profile in profiles}
    checks = [
        check("plan_source_gate_passed", plan["passed"], plan["passed"]),
        check(
            "plan_source_replay_identical",
            plan["artifact_writes"]["normalized_plans"] == "reused_identical",
            plan["artifact_writes"]["normalized_plans"],
        ),
        check("decennial_stage_passed", decennial["passed"], decennial["passed"]),
        check("acs_stage_passed", acs["passed"], acs["passed"]),
        check(
            "result_replays_identical",
            decennial["artifact_writes"]["combined_results"] == "reused_identical"
            and acs["artifact_writes"]["combined_results"] == "reused_identical",
            {
                "decennial": decennial["artifact_writes"]["combined_results"],
                "acs": acs["artifact_writes"]["combined_results"],
            },
        ),
        check(
            "partition_count",
            len(profiles) == EXPECTED_PARTITIONS and len(keys) == EXPECTED_PARTITIONS,
            {"profiles": len(profiles), "unique_keys": len(keys)},
        ),
        check("product_count", len(products) == EXPECTED_PRODUCTS, len(products)),
        check(
            "both_chambers",
            {profile["target_chamber"] for profile in profiles} == {"house", "senate"},
            sorted({profile["target_chamber"] for profile in profiles}),
        ),
        check(
            "all_partition_declarations_present",
            not missing_declarations,
            missing_declarations,
        ),
        check("all_partition_hashes_valid", not invalid_hashes, invalid_hashes),
        check(
            "no_precinct_dependencies", not precinct_dependencies, precinct_dependencies
        ),
        check("no_nearest_assignments", not nearest_assignments, nearest_assignments),
        check(
            "stage_checks_passed",
            all(item["passed"] for item in decennial["checks"] + acs["checks"]),
            {
                "decennial_checks": len(decennial["checks"]),
                "acs_checks": len(acs["checks"]),
            },
        ),
    ]
    qa = {
        "task": "POC029",
        "stage": "final_acceptance",
        "plan_count": plan["plan_count"],
        "partition_count": len(profiles),
        "product_count": len(products),
        "decennial_partition_count": decennial["partition_count"],
        "acs_partition_count": acs["partition_count"],
        "chambers": ["house", "senate"],
        "plan_vintages": sorted(set(decennial["plan_vintages"] + acs["plan_vintages"])),
        "hashes": {
            "normalized_plans": plan["hashes"]["normalized_plans"],
            "decennial_results": decennial["hashes"]["combined_results"],
            "acs_results": acs["hashes"]["combined_results"],
        },
        "checks": checks,
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "final_acceptance_qa.json", qa)
    if not qa["passed"]:
        raise RuntimeError(
            "POC029 final acceptance failed; inspect final_acceptance_qa.json"
        )
    return qa


def declaration_failures(
    profiles: list[dict[str, object]],
) -> list[dict[str, object]]:
    failures = []
    for profile in profiles:
        missing = sorted(
            field
            for field in REQUIRED_PARTITION_FIELDS
            if field not in profile or profile[field] in {None, ""}
        )
        if missing:
            failures.append({"partition": partition_key(profile), "missing": missing})
    return failures


def partition_key(profile: dict[str, object]) -> str:
    return ":".join(
        [
            str(profile.get("population_product_id")),
            str(profile.get("target_chamber")),
            str(profile.get("target_plan_id")),
        ]
    )


def valid_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"POC029 final acceptance passed: {qa['passed']}")


if __name__ == "__main__":
    main()
