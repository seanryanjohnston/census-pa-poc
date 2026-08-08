"""Machine-readable validation helpers for crosswalk and result artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


def logical_frame_hash(frame: pd.DataFrame, sort_by: list[str]) -> str:
    """Hash stable CSV bytes for a logically sorted table."""
    normalized = frame.sort_values(sort_by, kind="stable").reset_index(drop=True)
    content = normalized.to_csv(index=False, lineterminator="\n").encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def validate_crosswalk(
    frame: pd.DataFrame,
    expected_source_count: int,
    expected_target_ids: set[str],
    expected_allocation_row_count: int | None = None,
) -> list[dict[str, object]]:
    """Return stable crosswalk checks rather than raising at the first failure."""
    expected_rows = expected_allocation_row_count or expected_source_count
    assigned = frame[frame["assignment_status"] == "assigned"]
    weight_sums = assigned.groupby("source_block_geoid")["weight"].sum()
    supported_targets = set(assigned["target_precinct_geoid"].dropna())
    return [
        _check("allocation_row_count", len(frame) == expected_rows, len(frame)),
        _check(
            "unique_source_keys",
            frame["source_block_geoid"].nunique() == expected_source_count,
            int(frame["source_block_geoid"].nunique()),
        ),
        _check(
            "all_sources_assigned",
            assigned["source_block_geoid"].nunique() == expected_source_count,
            int(assigned["source_block_geoid"].nunique()),
        ),
        _check(
            "weights_in_range",
            bool(frame["weight"].between(0, 1, inclusive="both").all()),
            int((~frame["weight"].between(0, 1, inclusive="both")).sum()),
        ),
        _check(
            "weights_sum_to_one",
            bool(weight_sums.eq(1.0).all())
            and len(weight_sums) == expected_source_count,
            int((~weight_sums.eq(1.0)).sum()),
        ),
        _check(
            "all_targets_supported",
            supported_targets == expected_target_ids,
            {
                "supported": len(supported_targets),
                "expected": len(expected_target_ids),
                "missing": sorted(expected_target_ids - supported_targets),
                "unexpected": sorted(supported_targets - expected_target_ids),
            },
        ),
    ]


def all_pass(checks: list[dict[str, object]]) -> bool:
    return all(bool(check["passed"]) for check in checks)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_immutable_parquet(frame: pd.DataFrame, path: Path, sort_by: list[str]) -> str:
    """Create a versioned table once, or prove an existing table is identical."""
    expected_hash = logical_frame_hash(frame, sort_by)
    if path.exists():
        observed_hash = logical_frame_hash(pd.read_parquet(path), sort_by)
        if observed_hash != expected_hash:
            raise RuntimeError(
                f"Refusing to overwrite changed versioned artifact: {path}"
            )
        return "reused_identical"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return "created"


def _check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}
