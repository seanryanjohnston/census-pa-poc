"""Generate reproducible POC023 coverage and fixed-precinct review visuals."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterable
from pathlib import Path

import geopandas as gpd
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import MultiPolygon, Polygon

from census_pa_poc.fixed_geography import SOURCES, load_lrc_precincts
from census_pa_poc.sources import sha256
from census_pa_poc.validation import all_pass, write_json

EXPECTED_PRODUCTS = 20
EXPECTED_ELECTIONS = 19
EXPECTED_PAIRINGS = 380
EXPECTED_AVAILABLE_PAIRINGS = 114
EXPECTED_PRECINCTS = 9_178
PLAN_INVARIANCE_TOLERANCE = 0.001

AVAILABILITY_PATH = Path("mappings/population_election_availability_v1.csv")
ELECTIONS_PATH = Path("mappings/election_cycles.csv")
POPULATION_PATH = Path(
    "data/processed/poc016/fixed_precinct_population_products_v1.parquet"
)
TARGET_PATH = Path(SOURCES["lrc_geography"]["relative_path"])

PRODUCTS = (
    "dec_1990",
    "dec_2000",
    "dec_2010",
    "dec_2020",
    *(f"acs5_{year}" for year in range(2009, 2025)),
)

DECENNIAL_SELECTION = ("dec_1990", "dec_2000", "dec_2010", "dec_2020")
ACS_SELECTION = ("acs5_2009", "acs5_2015", "acs5_2020", "acs5_2024")

PRODUCT_LABELS = {
    "dec_1990": "1990 Census",
    "dec_2000": "2000 Census",
    "dec_2010": "2010 Census",
    "dec_2020": "2020 Census",
    **{f"acs5_{year}": f"ACS {year - 4}\u2013{year}" for year in range(2009, 2025)},
}

PLAN_LABELS = {
    "pa_senate_1981_plan": "1981 plan",
    "pa_senate_1991_final": "1991 Final",
    "pa_senate_2001_final": "2001 Final",
    "pa_senate_2012_revised_final": "2012 Revised Final",
    "pa_senate_2021_final": "2021 Final",
}

POPULATION_THRESHOLDS = (0, 250, 500, 1_000, 1_500, 2_500, 5_000, math.inf)
POPULATION_COLORS = (
    "#f2f2f2",
    "#e6f4f1",
    "#bfe3dc",
    "#7fc8bd",
    "#3ba899",
    "#157f72",
    "#08594f",
)

INK = "#18232c"
MUTED_INK = "#52616b"
BACKGROUND = "#ffffff"
GRID = "#d6dde1"
AVAILABLE = "#147d70"
UNAVAILABLE = "#e9edef"
PLAN_COLORS = ("#6750a4", "#276c9b", "#278277", "#b76827", "#8b4a68")


def run(root: Path) -> dict[str, object]:
    """Generate POC023 PNGs and machine-readable QA from accepted inputs."""
    root = root.resolve()
    artifact_dir = root / "artifacts/poc023"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    availability = pd.read_csv(root / AVAILABILITY_PATH, dtype="string")
    elections = pd.read_csv(root / ELECTIONS_PATH, dtype="string")
    population = pd.read_parquet(root / POPULATION_PATH)
    display_population, maximum_plan_range = collapse_plan_partitions(population)
    precincts = load_lrc_precincts(root / TARGET_PATH)
    precincts = prepare_precinct_geometry(precincts)

    manifest = build_manifest(root)
    write_json(artifact_dir / "input_manifest.json", manifest)

    coverage_path = artifact_dir / "year_coverage.png"
    decennial_path = artifact_dir / "decennial_population_by_precinct.png"
    acs_path = artifact_dir / "acs_population_by_precinct.png"

    render_coverage(availability, elections, coverage_path)
    render_population_atlas(
        precincts,
        display_population,
        DECENNIAL_SELECTION,
        "Decennial population allocated to fixed 2021 LRC precincts",
        decennial_path,
    )
    render_population_atlas(
        precincts,
        display_population,
        ACS_SELECTION,
        "Selected ACS 5-year estimates allocated to fixed 2021 LRC precincts",
        acs_path,
    )

    checks = build_checks(
        availability,
        elections,
        display_population,
        precincts,
        maximum_plan_range,
        (coverage_path, decennial_path, acs_path),
    )
    qa = {
        "task": "POC023",
        "fixed_target_id": "pa_lrc_2021_release_1b_geography",
        "fixed_target_effective_vintage": "2021-10-05",
        "display_value_rule": (
            "Select the lexicographically first Senate-plan partition for each "
            "product after verifying fixed-precinct plan invariance."
        ),
        "maximum_precinct_plan_range": maximum_plan_range,
        "plan_invariance_tolerance": PLAN_INVARIANCE_TOLERANCE,
        "population_bins": list(POPULATION_THRESHOLDS[:-1]) + ["infinity"],
        "checks": checks,
        "outputs": {
            path.name: {
                "relative_path": path.relative_to(root).as_posix(),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in (coverage_path, decennial_path, acs_path)
        },
        "passed": all_pass(checks),
    }
    write_json(artifact_dir / "qa_results.json", qa)
    (artifact_dir / "report.md").write_text(render_report(qa))
    if not qa["passed"]:
        raise RuntimeError("POC023 QA failed; inspect artifacts/poc023/qa_results.json")
    return qa


def collapse_plan_partitions(
    population: pd.DataFrame,
) -> tuple[pd.DataFrame, float]:
    """Select one display row after proving fixed-precinct plan invariance."""
    required = {
        "population_product_id",
        "senate_plan_id",
        "target_precinct_geoid",
        "estimate",
        "margin_of_error",
    }
    missing = required.difference(population.columns)
    if missing:
        raise ValueError(f"population result missing columns: {sorted(missing)}")

    key = ["population_product_id", "target_precinct_geoid"]
    ranges = population.groupby(key, dropna=False)["estimate"].agg(
        lambda values: float(values.max() - values.min())
    )
    maximum_range = float(ranges.max())
    if maximum_range > PLAN_INVARIANCE_TOLERANCE:
        raise ValueError(f"fixed-precinct plan range {maximum_range} exceeds tolerance")

    display = (
        population.sort_values([*key, "senate_plan_id"], kind="stable")
        .drop_duplicates(key, keep="first")
        .reset_index(drop=True)
    )
    return display, maximum_range


def prepare_precinct_geometry(precincts: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Normalize target identifiers and project the accepted target for drawing."""
    result = precincts.rename(columns={"GEOID20": "target_precinct_geoid"}).copy()
    result["target_precinct_geoid"] = result["target_precinct_geoid"].astype("string")
    result["COUNTYFP20"] = result["COUNTYFP20"].astype("string")
    return result.to_crs("EPSG:5070")


def build_manifest(root: Path) -> dict[str, object]:
    """Preserve exact local inputs and their accepted provenance chains."""
    target_manifest_path = root / "artifacts/poc021/input_manifest.json"
    pairing_manifest_path = root / "artifacts/poc016/input_manifest.json"
    availability_manifest_path = root / "artifacts/poc019/input_manifest.json"
    target_manifest = json.loads(target_manifest_path.read_text())
    target_record = next(
        record
        for record in target_manifest["sources"]
        if record["source_id"] == "pa_lrc_2021_release_1b_geography"
    )
    return {
        "task": "POC023",
        "target_geography": {
            **target_record,
            "provenance_manifest_path": target_manifest_path.relative_to(
                root
            ).as_posix(),
            "provenance_manifest_sha256": sha256(target_manifest_path),
        },
        "population_results": {
            "producer": "census-pa-poc POC016",
            "product": "accepted fixed-precinct population product partitions v1",
            "relative_path": POPULATION_PATH.as_posix(),
            "sha256": sha256(root / POPULATION_PATH),
            "reference_vintage": "1990 Census through 2020-2024 ACS",
            "effective_vintage": "2021-10-05 fixed precinct target",
            "geographic_universe": "9,178 fixed 2021 LRC Pennsylvania precincts",
            "metric": "standard total population estimate and ACS 90% MOE",
            "provenance_manifest_path": pairing_manifest_path.relative_to(
                root
            ).as_posix(),
            "provenance_manifest_sha256": sha256(pairing_manifest_path),
        },
        "availability_mapping": {
            "producer": "census-pa-poc POC019",
            "product": "population/election availability matrix v1",
            "relative_path": AVAILABILITY_PATH.as_posix(),
            "sha256": sha256(root / AVAILABILITY_PATH),
            "reference_vintage": "1990-2026 elections and 20 population products",
            "geographic_universe": "Pennsylvania even-year general elections",
            "cutoff": "general election day",
            "provenance_manifest_path": (
                availability_manifest_path.relative_to(root).as_posix()
            ),
            "provenance_manifest_sha256": sha256(availability_manifest_path),
        },
        "election_registry": {
            "producer": "census-pa-poc POC017",
            "product": "Pennsylvania even-year general-election registry",
            "relative_path": ELECTIONS_PATH.as_posix(),
            "sha256": sha256(root / ELECTIONS_PATH),
            "reference_vintage": "1990-2026",
            "geographic_universe": "19 Pennsylvania general-election cycles",
        },
    }


def build_checks(
    availability: pd.DataFrame,
    elections: pd.DataFrame,
    population: pd.DataFrame,
    precincts: gpd.GeoDataFrame,
    maximum_plan_range: float,
    output_paths: Iterable[Path],
) -> list[dict[str, object]]:
    """Return focused coverage, identity, and rendered-output checks."""
    product_counts = population.groupby("population_product_id")[
        "target_precinct_geoid"
    ].nunique()
    availability_shape = (
        availability["product_id"].nunique(),
        availability["election_id"].nunique(),
        len(availability),
    )
    geometry_ids = set(precincts["target_precinct_geoid"])
    population_ids = set(population["target_precinct_geoid"])
    return [
        check(
            "coverage_matrix_shape",
            availability_shape
            == (EXPECTED_PRODUCTS, EXPECTED_ELECTIONS, EXPECTED_PAIRINGS),
            {
                "products": availability_shape[0],
                "elections": availability_shape[1],
                "pairings": availability_shape[2],
            },
        ),
        check(
            "available_pairings",
            int(availability["candidate_for_poc016"].eq("true").sum())
            == EXPECTED_AVAILABLE_PAIRINGS,
            int(availability["candidate_for_poc016"].eq("true").sum()),
        ),
        check(
            "election_registry_complete",
            len(elections) == EXPECTED_ELECTIONS
            and elections["election_id"].nunique() == EXPECTED_ELECTIONS,
            len(elections),
        ),
        check(
            "fixed_target_not_relabeled",
            set(availability["fixed_precinct_snapshot_id"])
            == {"pa_lrc_2021_release_1b_geography"},
            sorted(set(availability["fixed_precinct_snapshot_id"])),
        ),
        check(
            "all_population_products_cover_every_precinct",
            set(product_counts.index) == set(PRODUCTS)
            and bool(product_counts.eq(EXPECTED_PRECINCTS).all()),
            {
                "products": len(product_counts),
                "minimum_precincts": int(product_counts.min()),
                "maximum_precincts": int(product_counts.max()),
            },
        ),
        check(
            "population_geometry_identity",
            geometry_ids == population_ids and len(geometry_ids) == EXPECTED_PRECINCTS,
            {
                "geometry_ids": len(geometry_ids),
                "population_ids": len(population_ids),
                "geometry_only": len(geometry_ids - population_ids),
                "population_only": len(population_ids - geometry_ids),
            },
        ),
        check(
            "precinct_plan_invariance",
            maximum_plan_range <= PLAN_INVARIANCE_TOLERANCE,
            maximum_plan_range,
        ),
        check(
            "visual_outputs_nonempty",
            all(path.exists() and path.stat().st_size > 0 for path in output_paths),
            {
                path.name: path.stat().st_size if path.exists() else 0
                for path in output_paths
            },
        ),
    ]


def check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def render_coverage(
    availability: pd.DataFrame, elections: pd.DataFrame, output_path: Path
) -> None:
    """Draw the 20-product by 19-election cutoff matrix with Senate-plan bands."""
    width, height = 1920, 1120
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    title_font = font(34, bold=True)
    subtitle_font = font(22)
    label_font = font(21)
    small_font = font(17)
    tiny_font = font(15)

    x0, cell_width = 430, 72
    fixed_y, plan_y = 106, 166
    matrix_y, cell_height = 290, 34
    draw.text(
        (48, 30),
        "Population-product coverage by Pennsylvania election cutoff",
        fill=INK,
        font=title_font,
    )
    draw.text(
        (48, 72),
        "All columns use the fixed 2021 LRC precinct target; Senate plans vary by election.",
        fill=MUTED_INK,
        font=subtitle_font,
    )

    election_rows = elections.sort_values("election_date", kind="stable").reset_index(
        drop=True
    )
    years = election_rows["election_date"].str.slice(0, 4).tolist()
    draw.text((48, fixed_y + 9), "Fixed precinct target", fill=INK, font=label_font)
    draw.rectangle(
        (x0, fixed_y, x0 + cell_width * len(years) - 4, fixed_y + 42),
        fill="#dceaf5",
    )
    centered_text(
        draw,
        (x0, fixed_y, x0 + cell_width * len(years) - 4, fixed_y + 42),
        "2021 LRC Data Set 1 precincts (9,178) \u2014 fixed across all cycles",
        font=small_font,
        fill=INK,
    )

    draw.text((48, plan_y + 9), "Applicable Senate plan", fill=INK, font=label_font)
    plan_groups = consecutive_groups(election_rows["senate_plan_id"].tolist())
    for color, (start, end, plan_id) in zip(PLAN_COLORS, plan_groups, strict=True):
        bounds = (
            x0 + start * cell_width,
            plan_y,
            x0 + end * cell_width - 4,
            plan_y + 42,
        )
        draw.rectangle(bounds, fill=color)
        centered_text(
            draw, bounds, PLAN_LABELS[plan_id], font=tiny_font, fill=BACKGROUND
        )

    for index, year in enumerate(years):
        left = x0 + index * cell_width
        centered_text(
            draw,
            (left, 226, left + cell_width - 4, 270),
            year,
            font=small_font,
            fill=INK,
        )

    matrix = availability.set_index(["product_id", "election_id"])
    election_ids = election_rows["election_id"].tolist()
    for row_index, product_id in enumerate(PRODUCTS):
        top = matrix_y + row_index * cell_height
        draw.text((48, top + 5), PRODUCT_LABELS[product_id], fill=INK, font=small_font)
        for column_index, election_id in enumerate(election_ids):
            left = x0 + column_index * cell_width
            available = matrix.loc[(product_id, election_id), "candidate_for_poc016"]
            is_available = available == "true"
            draw.rectangle(
                (left, top, left + cell_width - 4, top + cell_height - 4),
                fill=AVAILABLE if is_available else UNAVAILABLE,
            )
            if is_available:
                draw.line(
                    (
                        left + cell_width // 2 - 8,
                        top + 16,
                        left + cell_width // 2 - 2,
                        top + 22,
                        left + cell_width // 2 + 10,
                        top + 9,
                    ),
                    fill=BACKGROUND,
                    width=3,
                    joint="curve",
                )
            else:
                draw.line(
                    (
                        left + 23,
                        top + 9,
                        left + cell_width - 27,
                        top + cell_height - 13,
                    ),
                    fill="#9ca8ae",
                    width=2,
                )

    counts = (
        availability[availability["candidate_for_poc016"].eq("true")]
        .groupby("election_id")["product_id"]
        .nunique()
        .reindex(election_ids, fill_value=0)
    )
    count_y = matrix_y + len(PRODUCTS) * cell_height + 18
    draw.text((48, count_y + 7), "Products available", fill=INK, font=label_font)
    for index, count in enumerate(counts):
        left = x0 + index * cell_width
        centered_text(
            draw,
            (left, count_y, left + cell_width - 4, count_y + 42),
            str(int(count)),
            font=label_font,
            fill=INK,
        )

    legend_y = 1035
    draw.rectangle((48, legend_y, 76, legend_y + 24), fill=AVAILABLE)
    draw.text(
        (88, legend_y), "available by general-election day", fill=INK, font=small_font
    )
    draw.rectangle((462, legend_y, 490, legend_y + 24), fill=UNAVAILABLE)
    draw.line((468, legend_y + 5, 484, legend_y + 19), fill="#9ca8ae", width=2)
    draw.text((502, legend_y), "released after cutoff", fill=INK, font=small_font)
    draw.text(
        (842, legend_y),
        "1990 intentionally has no cataloged product available by its cutoff.",
        fill=MUTED_INK,
        font=small_font,
    )
    image.save(output_path, optimize=True)


def render_population_atlas(
    precincts: gpd.GeoDataFrame,
    population: pd.DataFrame,
    product_ids: tuple[str, ...],
    title: str,
    output_path: Path,
) -> None:
    """Draw four same-bin statewide fixed-precinct population maps."""
    width, height = 1920, 1200
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    title_font = fit_font(draw, title, maximum_width=width - 96, size=34, bold=True)
    subtitle_font = font(20)
    panel_font = font(25, bold=True)
    small_font = font(17)
    draw.text((48, 30), title, fill=INK, font=title_font)
    draw.text(
        (48, 74),
        "Same population bins in every panel; values are estimates on a constant, counterfactual precinct geography.",
        fill=MUTED_INK,
        font=subtitle_font,
    )

    panels = (
        (48, 130, 924, 585),
        (996, 130, 1872, 585),
        (48, 650, 924, 1105),
        (996, 650, 1872, 1105),
    )
    county_geometries = precincts.dissolve(by="COUNTYFP20").geometry.tolist()
    state_geometry = precincts.geometry.union_all()
    min_x, min_y, max_x, max_y = precincts.total_bounds

    for product_id, panel in zip(product_ids, panels, strict=True):
        values = population.loc[
            population["population_product_id"].eq(product_id),
            ["target_precinct_geoid", "estimate"],
        ]
        joined = precincts.merge(values, on="target_precinct_geoid", how="left")
        if joined["estimate"].isna().any():
            raise ValueError(f"{product_id} is missing precinct estimates")
        total = float(joined["estimate"].sum())
        draw.text(
            (panel[0], panel[1]), PRODUCT_LABELS[product_id], fill=INK, font=panel_font
        )
        draw.text(
            (panel[0], panel[1] + 34),
            f"State total: {total:,.0f}",
            fill=MUTED_INK,
            font=small_font,
        )
        map_bounds = (panel[0], panel[1] + 70, panel[2], panel[3])
        transform = map_transform((min_x, min_y, max_x, max_y), map_bounds, padding=12)
        for geometry, estimate in zip(joined.geometry, joined["estimate"], strict=True):
            draw_geometry(
                draw,
                geometry,
                transform,
                fill=POPULATION_COLORS[population_bin(float(estimate))],
            )
        for geometry in county_geometries:
            draw_geometry(
                draw, geometry, transform, fill=None, outline="#7d8a91", width=1
            )
        draw_geometry(draw, state_geometry, transform, fill=None, outline=INK, width=3)

    draw_population_legend(draw, (540, 1142), small_font)
    image.save(output_path, optimize=True)


def consecutive_groups(values: list[str]) -> list[tuple[int, int, str]]:
    """Return half-open runs of equal values."""
    if not values:
        return []
    groups: list[tuple[int, int, str]] = []
    start = 0
    current = values[0]
    for index, value in enumerate(values[1:], start=1):
        if value == current:
            continue
        groups.append((start, index, current))
        start = index
        current = value
    groups.append((start, len(values), current))
    return groups


def population_bin(value: float) -> int:
    """Return the stable display bin for a nonnegative population estimate."""
    if value < 0:
        raise ValueError("population estimates must be nonnegative")
    for index, upper in enumerate(POPULATION_THRESHOLDS[1:]):
        if value < upper:
            return index
    return len(POPULATION_COLORS) - 1


def map_transform(
    source_bounds: tuple[float, float, float, float],
    target_bounds: tuple[int, int, int, int],
    padding: int,
):
    """Return a projected-coordinate to image-coordinate transformation."""
    min_x, min_y, max_x, max_y = source_bounds
    left, top, right, bottom = target_bounds
    available_width = right - left - 2 * padding
    available_height = bottom - top - 2 * padding
    scale = min(available_width / (max_x - min_x), available_height / (max_y - min_y))
    drawn_width = (max_x - min_x) * scale
    drawn_height = (max_y - min_y) * scale
    x_offset = left + (right - left - drawn_width) / 2
    y_offset = top + (bottom - top - drawn_height) / 2

    def transform(x: float, y: float) -> tuple[int, int]:
        return (
            round(x_offset + (x - min_x) * scale),
            round(y_offset + (max_y - y) * scale),
        )

    return transform


def draw_geometry(
    draw: ImageDraw.ImageDraw,
    geometry: Polygon | MultiPolygon,
    transform,
    fill: str | None,
    outline: str | None = None,
    width: int = 1,
) -> None:
    """Draw Polygon and MultiPolygon geometry without inventing boundaries."""
    if geometry is None or geometry.is_empty:
        return
    polygons = geometry.geoms if isinstance(geometry, MultiPolygon) else (geometry,)
    for polygon in polygons:
        exterior = [transform(x, y) for x, y in polygon.exterior.coords]
        draw.polygon(exterior, fill=fill, outline=outline, width=width)
        if fill is not None:
            for ring in polygon.interiors:
                draw.polygon([transform(x, y) for x, y in ring.coords], fill=BACKGROUND)


def draw_population_legend(
    draw: ImageDraw.ImageDraw,
    origin: tuple[int, int],
    label_font: ImageFont.FreeTypeFont,
) -> None:
    """Draw the shared population-bin legend."""
    labels = (
        "0\u2013249",
        "250\u2013499",
        "500\u2013999",
        "1,000\u20131,499",
        "1,500\u20132,499",
        "2,500\u20134,999",
        "5,000+",
    )
    x, y = origin
    draw.text((48, y), "Estimated people per fixed precinct", fill=INK, font=label_font)
    for color, label in zip(POPULATION_COLORS, labels, strict=True):
        draw.rectangle((x, y, x + 28, y + 24), fill=color)
        draw.text((x + 38, y), label, fill=INK, font=label_font)
        x += 178


def centered_text(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    value: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
) -> None:
    """Draw one text label centered inside a rectangle."""
    left, top, right, bottom = bounds
    text_bounds = draw.textbbox((0, 0), value, font=font)
    text_width = text_bounds[2] - text_bounds[0]
    text_height = text_bounds[3] - text_bounds[1]
    draw.text(
        (
            left + (right - left - text_width) / 2,
            top + (bottom - top - text_height) / 2 - text_bounds[1],
        ),
        value,
        fill=fill,
        font=font,
    )


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Load a portable sans-serif font, with Pillow's default as fallback."""
    names = (
        (
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        )
        if bold
        else (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )
    )
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size=size)
    return ImageFont.load_default(size=size)


def fit_font(
    draw: ImageDraw.ImageDraw,
    value: str,
    maximum_width: int,
    size: int,
    bold: bool = False,
) -> ImageFont.ImageFont:
    """Choose the largest supported font size that keeps one title on canvas."""
    for candidate_size in range(size, 9, -1):
        candidate = font(candidate_size, bold=bold)
        bounds = draw.textbbox((0, 0), value, font=candidate)
        if bounds[2] - bounds[0] <= maximum_width:
            return candidate
    return font(10, bold=bold)


def render_report(qa: dict[str, object]) -> str:
    checks = qa["checks"]
    outputs = qa["outputs"]
    return "\n".join(
        [
            "# POC023 visual review",
            "",
            (
                "The generated coverage matrix represents all 20 population products "
                "against all 19 even-year general elections. The two population "
                "atlases map four decennial and four representative ACS periods on "
                "the fixed 2021 LRC precinct target."
            ),
            "",
            (
                "These are constant-geography/counterfactual maps, not historical or "
                "actual-2026 precinct boundary reconstructions. The population "
                "colors use identical bins in every panel. POC016 Senate-plan "
                "partitions were verified invariant within the accepted tolerance "
                "before a deterministic display partition was selected."
            ),
            "",
            (
                "Maximum fixed-precinct range across Senate partitions: "
                f"`{qa['maximum_precinct_plan_range']}` person."
            ),
            "",
            "## Checks",
            "",
            *[
                f"- `{'PASS' if item['passed'] else 'FAIL'}` "
                f"`{item['check_id']}`: `{item['observed']}`"
                for item in checks
            ],
            "",
            "## Outputs",
            "",
            *[
                f"- `{name}`: SHA-256 `{details['sha256']}` "
                f"({details['size_bytes']:,} bytes)"
                for name, details in outputs.items()
            ],
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(json.dumps(qa, indent=2))


if __name__ == "__main__":
    main()
