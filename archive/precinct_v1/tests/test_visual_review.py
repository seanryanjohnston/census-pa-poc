from __future__ import annotations

import pandas as pd
import pytest
from PIL import Image, ImageDraw

from census_pa_poc.visual_review import (
    collapse_plan_partitions,
    consecutive_groups,
    fit_font,
    population_bin,
)


def test_collapse_plan_partitions_checks_invariance_and_selects_stably() -> None:
    frame = pd.DataFrame(
        {
            "population_product_id": ["product", "product", "product"],
            "senate_plan_id": ["plan_b", "plan_a", "plan_a"],
            "target_precinct_geoid": ["p1", "p1", "p2"],
            "estimate": [100.0004, 100.0, 50.0],
            "margin_of_error": [10.0, 10.0, 5.0],
        }
    )

    result, maximum_range = collapse_plan_partitions(frame)

    assert maximum_range == pytest.approx(0.0004)
    assert result["senate_plan_id"].tolist() == ["plan_a", "plan_a"]
    assert result["estimate"].tolist() == [100.0, 50.0]


def test_collapse_plan_partitions_rejects_material_plan_variation() -> None:
    frame = pd.DataFrame(
        {
            "population_product_id": ["product", "product"],
            "senate_plan_id": ["plan_a", "plan_b"],
            "target_precinct_geoid": ["p1", "p1"],
            "estimate": [100.0, 100.01],
            "margin_of_error": [10.0, 10.0],
        }
    )

    with pytest.raises(ValueError, match="exceeds tolerance"):
        collapse_plan_partitions(frame)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0),
        (249.999, 0),
        (250, 1),
        (999.999, 2),
        (1_000, 3),
        (4_999.999, 5),
        (5_000, 6),
    ],
)
def test_population_bins_have_stable_inclusive_lower_bounds(
    value: float, expected: int
) -> None:
    assert population_bin(value) == expected


def test_population_bin_rejects_negative_estimate() -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        population_bin(-0.01)


def test_consecutive_groups_returns_half_open_runs() -> None:
    assert consecutive_groups(["a", "b", "b", "c"]) == [
        (0, 1, "a"),
        (1, 3, "b"),
        (3, 4, "c"),
    ]
    assert consecutive_groups([]) == []


def test_fit_font_keeps_title_within_requested_width() -> None:
    draw = ImageDraw.Draw(Image.new("RGB", (400, 100)))
    result = fit_font(draw, "A deliberately long map title", 240, 34, bold=True)

    bounds = draw.textbbox((0, 0), "A deliberately long map title", font=result)
    assert bounds[2] - bounds[0] <= 240
