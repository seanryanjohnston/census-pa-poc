from __future__ import annotations

import pandas as pd
import pytest

from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    validate_crosswalk,
    write_immutable_parquet,
)


def test_logical_hash_ignores_row_order() -> None:
    first = pd.DataFrame({"id": ["b", "a"], "value": [2, 1]})
    second = first.iloc[::-1].reset_index(drop=True)

    assert logical_frame_hash(first, ["id"]) == logical_frame_hash(second, ["id"])


def test_versioned_parquet_reuses_identical_and_rejects_change(tmp_path) -> None:
    path = tmp_path / "crosswalk_v1.parquet"
    original = pd.DataFrame({"id": ["a"], "weight": [1.0]})

    assert write_immutable_parquet(original, path, ["id"]) == "created"
    assert write_immutable_parquet(original, path, ["id"]) == "reused_identical"

    changed = pd.DataFrame({"id": ["a"], "weight": [0.5]})
    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        write_immutable_parquet(changed, path, ["id"])


def test_crosswalk_validation_accepts_multiple_allocations_per_source() -> None:
    frame = pd.DataFrame(
        {
            "source_block_geoid": ["a", "a", "b"],
            "target_precinct_geoid": ["x", "y", "y"],
            "weight": [0.25, 0.75, 1.0],
            "assignment_status": ["assigned", "assigned", "assigned"],
        }
    )

    checks = validate_crosswalk(frame, 2, {"x", "y"}, 3)

    assert all_pass(checks)


def test_crosswalk_validation_allows_numerical_weight_sum_noise() -> None:
    frame = pd.DataFrame(
        {
            "source_block_geoid": ["a", "a"],
            "target_precinct_geoid": ["x", "y"],
            "weight": [0.5, 0.5000000000005],
            "assignment_status": ["assigned", "assigned"],
        }
    )

    checks = validate_crosswalk(frame, 1, {"x", "y"}, 2)

    assert all_pass(checks)
