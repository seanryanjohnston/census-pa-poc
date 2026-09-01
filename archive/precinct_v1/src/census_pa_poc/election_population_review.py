"""Build reusable election-year precinct and Senate population review outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from PIL import Image, ImageDraw

from census_pa_poc.fixed_geography import SOURCES, load_lrc_precincts
from census_pa_poc.sources import sha256
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)
from census_pa_poc.visual_review import (
    AVAILABLE,
    BACKGROUND,
    INK,
    MUTED_INK,
    PLAN_LABELS,
    POPULATION_COLORS,
    draw_geometry,
    draw_population_legend,
    fit_font,
    font,
    map_transform,
    population_bin,
    prepare_precinct_geometry,
)

EXPECTED_ELECTIONS = 19
EXPECTED_PRECINCTS = 9_178
EXPECTED_SENATE_DISTRICTS = 50
EXPECTED_PRECINCT_ROWS = EXPECTED_ELECTIONS * EXPECTED_PRECINCTS
EXPECTED_SENATE_ROWS = EXPECTED_ELECTIONS * EXPECTED_SENATE_DISTRICTS
CONSERVATION_TOLERANCE = 0.001

ELECTIONS_PATH = Path("mappings/election_cycles.csv")
AVAILABILITY_PATH = Path("mappings/population_election_availability_v1.csv")
PRECINCT_RESULTS_PATH = Path(
    "data/processed/poc016/fixed_precinct_population_products_v1.parquet"
)
SENATE_RESULTS_PATH = Path(
    "data/processed/poc016/senate_population_products_v1.parquet"
)
TARGET_PATH = Path(SOURCES["lrc_geography"]["relative_path"])

DISPLAY_SELECTION_RULE = "newest_reference_period_available_by_general_election_day_v1"
MISSING_FILL = "#f3c7c4"
MISSING_INK = "#a2352d"
BAR_FILL = "#178277"
BAR_TRACK = "#e7ecee"


def run(root: Path, election_years: list[int] | None = None) -> dict[str, object]:
    """Build complete election-grain tables and requested detail visuals."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc024"
    processed_dir = root / "data/processed/poc024"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    elections = load_elections(root / ELECTIONS_PATH)
    availability = pd.read_csv(root / AVAILABILITY_PATH, dtype="string")
    precinct_results = pd.read_parquet(root / PRECINCT_RESULTS_PATH)
    senate_results = pd.read_parquet(root / SENATE_RESULTS_PATH)
    precincts = prepare_precinct_geometry(load_lrc_precincts(root / TARGET_PATH))

    selection = select_display_products(elections, availability)
    election_precincts = build_election_precinct_population(
        selection, precinct_results, precincts["target_precinct_geoid"]
    )
    election_senate = build_election_senate_population(selection, senate_results)

    writes = {
        "display_selection": write_immutable_parquet(
            selection,
            processed_dir / "election_population_display_selection_v1.parquet",
            ["election_date"],
        ),
        "precinct_population": write_immutable_parquet(
            election_precincts,
            processed_dir / "election_fixed_precinct_population_v1.parquet",
            ["election_date", "target_precinct_geoid"],
        ),
        "senate_population": write_immutable_parquet(
            election_senate,
            processed_dir / "election_senate_population_v1.parquet",
            ["election_date", "senate_district"],
        ),
    }

    coverage_path = artifact_dir / "election_population_coverage.png"
    render_coverage(selection, election_precincts, election_senate, coverage_path)

    requested_years = normalize_requested_years(election_years, selection)
    detail_paths: list[Path] = []
    for year in requested_years:
        detail_path = artifact_dir / f"election_{year}_population.png"
        render_election_detail(
            year,
            selection,
            precincts,
            election_precincts,
            election_senate,
            detail_path,
        )
        detail_paths.append(detail_path)

    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)
    checks = build_checks(
        selection,
        election_precincts,
        election_senate,
        precincts,
        coverage_path,
        detail_paths,
    )
    qa = {
        "task": "POC024",
        "display_selection_rule": DISPLAY_SELECTION_RULE,
        "selection_is_model_feature_decision": False,
        "fixed_target_id": "pa_lrc_2021_release_1b_geography",
        "expected_precincts_per_election": EXPECTED_PRECINCTS,
        "expected_senate_districts_per_election": EXPECTED_SENATE_DISTRICTS,
        "requested_detail_years": requested_years,
        "missingness": missingness_summary(election_precincts, election_senate),
        "checks": checks,
        "artifact_writes": writes,
        "hashes": {
            "display_selection": logical_frame_hash(selection, ["election_date"]),
            "precinct_population": logical_frame_hash(
                election_precincts, ["election_date", "target_precinct_geoid"]
            ),
            "senate_population": logical_frame_hash(
                election_senate, ["election_date", "senate_district"]
            ),
        },
        "visual_outputs": visual_output_records(root, [coverage_path, *detail_paths]),
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(render_report(qa, selection))
    if not qa["passed"]:
        raise RuntimeError("POC024 QA failed; inspect artifacts/poc024/qa_results.json")
    return qa


def load_elections(path: Path) -> pd.DataFrame:
    """Load the complete election registry with stable year identity."""
    elections = pd.read_csv(path, dtype="string")
    elections["election_year"] = (
        elections["election_date"].str.slice(0, 4).astype("int64")
    )
    return elections.sort_values("election_date", kind="stable").reset_index(drop=True)


def select_display_products(
    elections: pd.DataFrame, availability: pd.DataFrame
) -> pd.DataFrame:
    """Select the newest reference period available at each election cutoff."""
    eligible = availability[availability["candidate_for_poc016"].eq("true")].copy()
    eligible = eligible.sort_values(
        [
            "election_date",
            "reference_end",
            "release_date_latest",
            "product_id",
        ],
        kind="stable",
    )
    selected = eligible.groupby("election_id", as_index=False).tail(1)
    selected = selected[
        [
            "election_id",
            "product_id",
            "product_family",
            "reference_start",
            "reference_end",
            "release_date_published",
        ]
    ].rename(columns={"product_id": "population_product_id"})
    result = elections.merge(
        selected, on="election_id", how="left", validate="one_to_one"
    )
    result["display_selection_rule"] = DISPLAY_SELECTION_RULE
    result["display_selection_status"] = (
        result["population_product_id"]
        .notna()
        .map(
            {
                True: "selected_available_product",
                False: "no_product_available_by_cutoff",
            }
        )
    )
    result["missing_reason"] = (
        result["population_product_id"]
        .isna()
        .map(
            {
                True: "no_cataloged_population_product_available_by_election_day",
                False: pd.NA,
            }
        )
    )
    return result[
        [
            "election_id",
            "election_year",
            "election_date",
            "cycle_role",
            "precinct_snapshot_id",
            "senate_plan_id",
            "population_product_id",
            "product_family",
            "reference_start",
            "reference_end",
            "release_date_published",
            "display_selection_rule",
            "display_selection_status",
            "missing_reason",
        ]
    ]


def build_election_precinct_population(
    selection: pd.DataFrame,
    population: pd.DataFrame,
    target_ids: pd.Series,
) -> pd.DataFrame:
    """Materialize every election × expected fixed-precinct combination."""
    expected_ids = pd.DataFrame(
        {"target_precinct_geoid": target_ids.astype("string").sort_values()}
    )
    frames = [
        build_precinct_election_rows(row, expected_ids, population)
        for row in selection.to_dict("records")
    ]
    result = pd.concat(frames, ignore_index=True)
    result["estimate"] = result["estimate"].astype("Float64")
    result["margin_of_error"] = result["margin_of_error"].astype("Float64")
    result["target_precinct_geoid"] = result["target_precinct_geoid"].astype("string")
    result["population_product_id"] = result["population_product_id"].astype("string")
    return result


def build_precinct_election_rows(
    election: dict[str, object],
    expected_ids: pd.DataFrame,
    population: pd.DataFrame,
) -> pd.DataFrame:
    """Build one complete precinct partition, including typed missing rows."""
    product_id = election["population_product_id"]
    base = expected_ids.copy()
    if pd.isna(product_id):
        values = base.assign(estimate=pd.NA, margin_of_error=pd.NA)
    else:
        partition = population[
            population["population_product_id"].eq(product_id)
            & population["senate_plan_id"].eq(election["senate_plan_id"])
        ][["target_precinct_geoid", "estimate", "margin_of_error"]]
        values = base.merge(
            partition,
            on="target_precinct_geoid",
            how="left",
            validate="one_to_one",
        )
    return add_election_metadata(values, election, "fixed_precinct")


def build_election_senate_population(
    selection: pd.DataFrame, population: pd.DataFrame
) -> pd.DataFrame:
    """Materialize every election × expected Senate-district combination."""
    expected = pd.DataFrame(
        {
            "senate_district": pd.Series(
                range(1, EXPECTED_SENATE_DISTRICTS + 1), dtype="Int64"
            )
        }
    )
    frames = [
        build_senate_election_rows(row, expected, population)
        for row in selection.to_dict("records")
    ]
    result = pd.concat(frames, ignore_index=True)
    result["senate_district"] = result["senate_district"].astype("Int64")
    result["estimate"] = result["estimate"].astype("Float64")
    result["margin_of_error"] = result["margin_of_error"].astype("Float64")
    result["population_product_id"] = result["population_product_id"].astype("string")
    return result


def build_senate_election_rows(
    election: dict[str, object],
    expected: pd.DataFrame,
    population: pd.DataFrame,
) -> pd.DataFrame:
    """Build one complete district partition, including typed missing rows."""
    product_id = election["population_product_id"]
    base = expected.copy()
    if pd.isna(product_id):
        values = base.assign(estimate=pd.NA, margin_of_error=pd.NA)
    else:
        partition = population[
            population["population_product_id"].eq(product_id)
            & population["senate_plan_id"].eq(election["senate_plan_id"])
        ][["senate_district", "estimate", "margin_of_error"]]
        values = base.merge(
            partition,
            on="senate_district",
            how="left",
            validate="one_to_one",
        )
    return add_election_metadata(values, election, "state_senate_district")


def add_election_metadata(
    values: pd.DataFrame, election: dict[str, object], geography_level: str
) -> pd.DataFrame:
    """Attach the selected product, fixed target, plan, and typed status."""
    result = values.copy()
    for column in (
        "election_id",
        "election_year",
        "election_date",
        "precinct_snapshot_id",
        "senate_plan_id",
        "population_product_id",
        "display_selection_rule",
    ):
        result[column] = election[column]
    result["geography_level"] = geography_level
    missing = result["estimate"].isna()
    result["data_status"] = missing.map({True: "missing", False: "available"}).astype(
        "string"
    )
    result["missing_reason"] = pd.Series(pd.NA, index=result.index, dtype="string")
    if pd.isna(election["population_product_id"]):
        result.loc[missing, "missing_reason"] = election["missing_reason"]
    else:
        result.loc[missing, "missing_reason"] = "selected_result_row_missing"
    return result


def normalize_requested_years(
    years: list[int] | None, selection: pd.DataFrame
) -> list[int]:
    """Validate requested years; default to every registered election."""
    available = selection["election_year"].astype(int).tolist()
    if not years:
        return available
    requested = list(dict.fromkeys(years))
    invalid = sorted(set(requested).difference(available))
    if invalid:
        raise ValueError(f"election years are not registered: {invalid}")
    return requested


def missingness_summary(
    precincts: pd.DataFrame, senate: pd.DataFrame
) -> list[dict[str, object]]:
    """Summarize visible missingness at both requested geography levels."""
    precinct_counts = precincts.groupby("election_year")["estimate"].agg(
        present=lambda values: int(values.notna().sum()),
        missing=lambda values: int(values.isna().sum()),
    )
    senate_counts = senate.groupby("election_year")["estimate"].agg(
        present=lambda values: int(values.notna().sum()),
        missing=lambda values: int(values.isna().sum()),
    )
    summary = precinct_counts.join(
        senate_counts, lsuffix="_precinct", rsuffix="_senate"
    )
    return summary.reset_index().to_dict("records")


def build_checks(
    selection: pd.DataFrame,
    precinct_population: pd.DataFrame,
    senate_population: pd.DataFrame,
    precincts: gpd.GeoDataFrame,
    coverage_path: Path,
    detail_paths: list[Path],
) -> list[dict[str, object]]:
    """Validate complete grains, typed missingness, and rollup conservation."""
    precinct_counts = precinct_population.groupby("election_year").size()
    senate_counts = senate_population.groupby("election_year").size()
    selected = selection[selection["population_product_id"].notna()]
    selected_years = set(selected["election_year"].astype(int))
    missing_precinct_years = set(
        precinct_population.loc[
            precinct_population["estimate"].isna(), "election_year"
        ].astype(int)
    )
    missing_senate_years = set(
        senate_population.loc[
            senate_population["estimate"].isna(), "election_year"
        ].astype(int)
    )
    precinct_totals = precinct_population.groupby("election_year")["estimate"].sum(
        min_count=1
    )
    senate_totals = senate_population.groupby("election_year")["estimate"].sum(
        min_count=1
    )
    total_deltas = (precinct_totals - senate_totals).abs().dropna()
    return [
        check(
            "display_selection_complete",
            len(selection) == EXPECTED_ELECTIONS
            and selection["election_id"].nunique() == EXPECTED_ELECTIONS,
            len(selection),
        ),
        check(
            "only_1990_has_no_available_product",
            set(
                selection.loc[
                    selection["population_product_id"].isna(), "election_year"
                ]
            )
            == {1990},
            selection.loc[
                selection["population_product_id"].isna(), "election_year"
            ].tolist(),
        ),
        check(
            "precinct_grain_complete",
            len(precinct_population) == EXPECTED_PRECINCT_ROWS
            and bool(precinct_counts.eq(EXPECTED_PRECINCTS).all()),
            {
                "rows": len(precinct_population),
                "minimum_per_election": int(precinct_counts.min()),
                "maximum_per_election": int(precinct_counts.max()),
            },
        ),
        check(
            "senate_grain_complete",
            len(senate_population) == EXPECTED_SENATE_ROWS
            and bool(senate_counts.eq(EXPECTED_SENATE_DISTRICTS).all()),
            {
                "rows": len(senate_population),
                "minimum_per_election": int(senate_counts.min()),
                "maximum_per_election": int(senate_counts.max()),
            },
        ),
        check(
            "precinct_geometry_identity_complete",
            set(precinct_population["target_precinct_geoid"])
            == set(precincts["target_precinct_geoid"]),
            {
                "population_ids": int(
                    precinct_population["target_precinct_geoid"].nunique()
                ),
                "geometry_ids": int(precincts["target_precinct_geoid"].nunique()),
            },
        ),
        check(
            "all_missing_rows_are_typed",
            bool(
                precinct_population.loc[
                    precinct_population["estimate"].isna(), "missing_reason"
                ]
                .notna()
                .all()
                and senate_population.loc[
                    senate_population["estimate"].isna(), "missing_reason"
                ]
                .notna()
                .all()
            ),
            {
                "precinct_missing": int(precinct_population["estimate"].isna().sum()),
                "senate_missing": int(senate_population["estimate"].isna().sum()),
            },
        ),
        check(
            "selected_products_have_no_missing_rows",
            not bool(selected_years.intersection(missing_precinct_years))
            and not bool(selected_years.intersection(missing_senate_years)),
            {
                "precinct_years": sorted(missing_precinct_years),
                "senate_years": sorted(missing_senate_years),
            },
        ),
        check(
            "precinct_and_senate_totals_conserve",
            bool(total_deltas.le(CONSERVATION_TOLERANCE).all()),
            {
                "maximum_absolute_delta": float(total_deltas.max()),
                "tolerance": CONSERVATION_TOLERANCE,
            },
        ),
        check(
            "visual_outputs_complete",
            coverage_path.exists()
            and coverage_path.stat().st_size > 0
            and len(detail_paths) > 0
            and all(path.exists() and path.stat().st_size > 0 for path in detail_paths),
            {
                "coverage_bytes": coverage_path.stat().st_size
                if coverage_path.exists()
                else 0,
                "detail_images": len(detail_paths),
            },
        ),
    ]


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_coverage(
    selection: pd.DataFrame,
    precinct_population: pd.DataFrame,
    senate_population: pd.DataFrame,
    output_path: Path,
) -> None:
    """Render one readable row per election with explicit coverage counts."""
    width, height = 1920, 1060
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    title_font = font(34, bold=True)
    header_font = font(19, bold=True)
    label_font = font(18)
    small_font = font(16)
    draw.text((48, 28), "Election-year population coverage", fill=INK, font=title_font)
    draw.text(
        (48, 72),
        "Display-only default: newest reference period available by election day. Missing expected rows remain visible.",
        fill=MUTED_INK,
        font=font(20),
    )

    columns = (48, 150, 430, 780, 1180, 1540)
    headers = (
        "Election",
        "Selected product",
        "Applicable Senate plan",
        "Fixed precinct coverage",
        "Senate district coverage",
        "Status",
    )
    for x, label in zip(columns, headers, strict=True):
        draw.text((x, 128), label, fill=INK, font=header_font)

    p_counts = precinct_population.groupby("election_year")["estimate"].agg(
        present=lambda values: int(values.notna().sum()),
        missing=lambda values: int(values.isna().sum()),
    )
    s_counts = senate_population.groupby("election_year")["estimate"].agg(
        present=lambda values: int(values.notna().sum()),
        missing=lambda values: int(values.isna().sum()),
    )
    row_top, row_height = 174, 44
    for index, row in enumerate(selection.to_dict("records")):
        top = row_top + index * row_height
        year = int(row["election_year"])
        if index % 2:
            draw.rectangle(
                (40, top - 4, width - 40, top + row_height - 5), fill="#f7f9fa"
            )
        draw.text((columns[0], top + 5), str(year), fill=INK, font=label_font)
        product_label = display_product_label(row)
        draw.text((columns[1], top + 5), product_label, fill=INK, font=label_font)
        draw.text(
            (columns[2], top + 5),
            PLAN_LABELS[str(row["senate_plan_id"])],
            fill=INK,
            font=label_font,
        )
        draw_coverage_bar(
            draw,
            columns[3],
            top + 4,
            330,
            int(p_counts.loc[year, "present"]),
            EXPECTED_PRECINCTS,
            label_font,
        )
        draw_coverage_bar(
            draw,
            columns[4],
            top + 4,
            300,
            int(s_counts.loc[year, "present"]),
            EXPECTED_SENATE_DISTRICTS,
            label_font,
        )
        missing = int(p_counts.loc[year, "missing"] + s_counts.loc[year, "missing"])
        status = "complete" if missing == 0 else "missing shown"
        draw.text(
            (columns[5], top + 5),
            status,
            fill=AVAILABLE if missing == 0 else MISSING_INK,
            font=small_font,
        )

    draw.rectangle((48, 1020, 72, 1042), fill=AVAILABLE)
    draw.text((84, 1018), "available", fill=INK, font=small_font)
    draw.rectangle((220, 1020, 244, 1042), fill=MISSING_FILL)
    draw.line((222, 1022, 242, 1040), fill=MISSING_INK, width=2)
    draw.text((256, 1018), "missing expected geography", fill=INK, font=small_font)
    image.save(output_path, optimize=True)


def draw_coverage_bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    present: int,
    expected: int,
    label_font,
) -> None:
    """Draw a quantitative coverage bar and exact present/expected count."""
    bar_width = 205
    draw.rectangle((x, y + 6, x + bar_width, y + 24), fill=BAR_TRACK)
    if present:
        draw.rectangle(
            (x, y + 6, x + round(bar_width * present / expected), y + 24),
            fill=AVAILABLE,
        )
    if present < expected:
        missing_start = x + round(bar_width * present / expected)
        draw.rectangle((missing_start, y + 6, x + bar_width, y + 24), fill=MISSING_FILL)
        draw.line(
            (missing_start, y + 6, x + bar_width, y + 24), fill=MISSING_INK, width=2
        )
    draw.text((x + 218, y + 3), f"{present:,}/{expected:,}", fill=INK, font=label_font)


def render_election_detail(
    year: int,
    selection: pd.DataFrame,
    precincts: gpd.GeoDataFrame,
    precinct_population: pd.DataFrame,
    senate_population: pd.DataFrame,
    output_path: Path,
) -> None:
    """Render one election's precinct map and applicable-plan district rollup."""
    selected = selection.loc[selection["election_year"].eq(year)].iloc[0]
    precinct_values = precinct_population[precinct_population["election_year"].eq(year)]
    senate_values = senate_population[senate_population["election_year"].eq(year)]
    joined = precincts.merge(
        precinct_values[
            ["target_precinct_geoid", "estimate", "data_status", "missing_reason"]
        ],
        on="target_precinct_geoid",
        how="left",
        validate="one_to_one",
    )

    width, height = 1920, 1120
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    title = f"{year} election population \u2014 {display_product_label(selected)}"
    draw.text(
        (48, 28),
        title,
        fill=INK,
        font=fit_font(draw, title, width - 96, 34, bold=True),
    )
    draw.text(
        (48, 72),
        (
            "Fixed 2021 LRC precinct target \u2022 "
            f"{PLAN_LABELS[str(selected['senate_plan_id'])]} \u2022 "
            "display default only"
        ),
        fill=MUTED_INK,
        font=font(20),
    )

    present_precincts = int(joined["estimate"].notna().sum())
    present_districts = int(senate_values["estimate"].notna().sum())
    state_total = joined["estimate"].sum(min_count=1)
    total_label = "missing" if pd.isna(state_total) else f"{float(state_total):,.0f}"
    draw.text(
        (48, 110),
        (
            f"State total: {total_label}  \u2022  precincts {present_precincts:,}/"
            f"{EXPECTED_PRECINCTS:,}  \u2022  Senate districts "
            f"{present_districts}/{EXPECTED_SENATE_DISTRICTS}"
        ),
        fill=INK if present_precincts else MISSING_INK,
        font=font(19, bold=True),
    )

    map_bounds = (48, 190, 1160, 980)
    min_x, min_y, max_x, max_y = precincts.total_bounds
    transform = map_transform((min_x, min_y, max_x, max_y), map_bounds, padding=18)
    for row in joined.itertuples(index=False):
        fill = (
            MISSING_FILL
            if pd.isna(row.estimate)
            else POPULATION_COLORS[population_bin(float(row.estimate))]
        )
        draw_geometry(draw, row.geometry, transform, fill=fill)
    state_geometry = precincts.geometry.union_all()
    county_geometry = precincts.dissolve(by="COUNTYFP20").geometry.tolist()
    for geometry in county_geometry:
        draw_geometry(draw, geometry, transform, fill=None, outline="#7d8a91", width=1)
    draw_geometry(draw, state_geometry, transform, fill=None, outline=INK, width=3)
    if present_precincts < EXPECTED_PRECINCTS:
        draw_missing_map_marker(draw, map_bounds, present_precincts)

    draw.text(
        (1210, 174),
        "Population by State Senate district",
        fill=INK,
        font=font(23, bold=True),
    )
    draw.text(
        (1210, 210),
        PLAN_LABELS[str(selected["senate_plan_id"])],
        fill=MUTED_INK,
        font=font(18),
    )
    draw_senate_bars(draw, senate_values, (1210, 250, 1870, 980))

    draw_population_legend(draw, (540, 1056), font(16))
    draw.rectangle((330, 1056, 358, 1080), fill=MISSING_FILL)
    draw.line((332, 1058, 356, 1078), fill=MISSING_INK, width=2)
    draw.text((370, 1054), "missing", fill=INK, font=font(16))
    image.save(output_path, optimize=True)


def draw_missing_map_marker(
    draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], present: int
) -> None:
    """Add a non-color-only missing marker over an incomplete precinct map."""
    left, top, right, bottom = bounds
    if present == 0:
        draw.line(
            (left + 80, top + 60, right - 80, bottom - 60), fill=MISSING_INK, width=9
        )
        draw.line(
            (right - 80, top + 60, left + 80, bottom - 60), fill=MISSING_INK, width=9
        )
        label = "No population product available by this election cutoff"
        label_font = fit_font(draw, label, right - left - 220, 28, bold=True)
        label_bounds = draw.textbbox((0, 0), label, font=label_font)
        x = left + (right - left - (label_bounds[2] - label_bounds[0])) / 2
        y = top + (bottom - top) / 2 - 20
        draw.rectangle(
            (x - 16, y - 10, x + label_bounds[2] + 16, y + 42), fill=BACKGROUND
        )
        draw.text((x, y), label, fill=MISSING_INK, font=label_font)


def draw_senate_bars(
    draw: ImageDraw.ImageDraw,
    senate_values: pd.DataFrame,
    bounds: tuple[int, int, int, int],
) -> None:
    """Draw all 50 expected district values in two compact columns."""
    left, top, right, _bottom = bounds
    values = senate_values.sort_values("senate_district", kind="stable")
    maximum = values["estimate"].max(skipna=True)
    maximum = float(maximum) if not pd.isna(maximum) else 1.0
    column_width = (right - left - 30) // 2
    row_height = 28
    label_font = font(14)
    value_font = font(13)
    for index, row in enumerate(values.itertuples(index=False)):
        column = index // 25
        row_index = index % 25
        x = left + column * (column_width + 30)
        y = top + row_index * row_height
        draw.text(
            (x, y + 2), f"{int(row.senate_district):02d}", fill=INK, font=label_font
        )
        bar_x = x + 32
        bar_width = 190
        draw.rectangle((bar_x, y + 5, bar_x + bar_width, y + 20), fill=BAR_TRACK)
        if pd.isna(row.estimate):
            draw.rectangle((bar_x, y + 5, bar_x + bar_width, y + 20), fill=MISSING_FILL)
            draw.line(
                (bar_x, y + 5, bar_x + bar_width, y + 20), fill=MISSING_INK, width=2
            )
            value = "missing"
            value_fill = MISSING_INK
        else:
            filled = round(bar_width * float(row.estimate) / maximum)
            draw.rectangle((bar_x, y + 5, bar_x + filled, y + 20), fill=BAR_FILL)
            value = f"{float(row.estimate):,.0f}"
            value_fill = INK
        draw.text(
            (bar_x + bar_width + 8, y + 1), value, fill=value_fill, font=value_font
        )


def display_product_label(row: pd.Series | dict[str, object]) -> str:
    """Return a concise explicit product label for a selection row."""
    product_id = row["population_product_id"]
    if pd.isna(product_id):
        return "No product available"
    if str(product_id).startswith("acs5_"):
        end = int(str(product_id).split("_")[1])
        return f"ACS {end - 4}\u2013{end}"
    return f"{str(product_id).split('_')[1]} Census"


def build_manifest(root: Path) -> dict[str, object]:
    """Record exact accepted input files and provenance-manifest links."""
    paths = {
        "election_registry": ELECTIONS_PATH,
        "availability_mapping": AVAILABILITY_PATH,
        "fixed_precinct_results": PRECINCT_RESULTS_PATH,
        "senate_results": SENATE_RESULTS_PATH,
        "target_geography": TARGET_PATH,
    }
    provenance = {
        "availability_mapping": Path("artifacts/poc019/input_manifest.json"),
        "fixed_precinct_results": Path("artifacts/poc016/input_manifest.json"),
        "senate_results": Path("artifacts/poc016/input_manifest.json"),
        "target_geography": Path("artifacts/poc021/input_manifest.json"),
    }
    return {
        "task": "POC024",
        "display_selection_rule": DISPLAY_SELECTION_RULE,
        "inputs": {
            name: {
                "relative_path": path.as_posix(),
                "sha256": sha256(root / path),
                "size_bytes": (root / path).stat().st_size,
                "provenance_manifest_path": provenance[name].as_posix()
                if name in provenance
                else None,
                "provenance_manifest_sha256": sha256(root / provenance[name])
                if name in provenance
                else None,
            }
            for name, path in paths.items()
        },
    }


def visual_output_records(root: Path, paths: list[Path]) -> dict[str, object]:
    return {
        path.name: {
            "relative_path": path.relative_to(root).as_posix(),
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in paths
    }


def render_report(qa: dict[str, object], selection: pd.DataFrame) -> str:
    """Render the concise accepted local report."""
    selected = [
        f"- {int(row.election_year)}: {display_product_label(row._asdict())}; "
        f"{PLAN_LABELS[str(row.senate_plan_id)]}"
        for row in selection.itertuples(index=False)
    ]
    checks = [
        f"- `{'PASS' if item['passed'] else 'FAIL'}` `{item['check_id']}`: "
        f"`{item['observed']}`"
        for item in qa["checks"]
    ]
    return "\n".join(
        [
            "# POC024 election-year population review",
            "",
            (
                "The display-only rule selects the newest population reference "
                "period available by each general-election day. It is not a "
                "forecast-feature selection decision. Every election materializes "
                "all 9,178 fixed precinct rows and all 50 applicable-plan Senate "
                "district rows."
            ),
            "",
            (
                "Missing values are retained with typed reasons. The accepted "
                "inputs have complete precinct and Senate values from 1992 through "
                "2026; all 1990 values are visibly missing because no cataloged "
                "product was available by that cutoff."
            ),
            "",
            "## Display selections",
            "",
            *selected,
            "",
            "## Checks",
            "",
            *checks,
            "",
            "## Reproduce",
            "",
            "```bash",
            ".venv/bin/python -m census_pa_poc.election_population_review --root .",
            "```",
            "",
            (
                "Use one or more `--election-year YEAR` options to regenerate "
                "selected detail charts instead of all 19."
            ),
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--election-year", type=int, action="append")
    args = parser.parse_args()
    qa = run(args.root, args.election_year)
    print(json.dumps(qa, indent=2))


if __name__ == "__main__":
    main()
