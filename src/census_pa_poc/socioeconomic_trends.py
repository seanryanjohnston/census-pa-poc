"""Build fixed-current-plan ACS socioeconomic trend diagnostics."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import requests

from census_pa_poc.direct_legislative_acs import regime_for_year
from census_pa_poc.sources import load_acs5_block_group_population, sha256
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

DEFINITIONS_PATH = "mappings/socioeconomic_metric_definitions_v1.csv"
PRODUCTS_PATH = "mappings/acs5_products.csv"
PARTITIONS_PATH = "mappings/legislative_population_partitions_v1.csv"
PLANS_PATH = "mappings/legislative_plans_v1.csv"
RAW_ROOT = "data/raw/acs5_socioeconomic_pa"
CROSSWALK_ROOT = "data/processed/direct_legislative/poc029/acs_crosswalks"
OUTPUT_ROOT = "data/processed/direct_legislative/poc036"
ARTIFACT_ROOT = "artifacts/work/poc036"
YEARS = tuple(range(2009, 2025))
CANONICAL_FAMILIES = {
    "education_attainment",
    "employment_status",
    "poverty_ratio",
}
SAMPLE_DISTRICTS = {
    "house": (68, 87, 194),
    "senate": (3, 25, 31),
}
CURRENT_PLANS = {
    "house": "pa_house_2021_final",
    "senate": "pa_senate_2021_final",
}
EXPECTED_DISTRICTS = {"house": 203, "senate": 50}
UNCERTAINTY_NOTE = (
    "Category MOEs sum mutually exclusive source cells by RSS; district MOEs "
    "then apply allocation weights and RSS. Covariance and allocation-weight "
    "uncertainty are unavailable. Derived shares have no reported MOE."
)
TREND_NOTE = (
    "Adjacent ACS five-year estimates overlap by four years and are not "
    "independent annual observations."
)
B15003_REFERENCE_EXPRESSION = (
    "below_high_school=B15003_002E+B15003_003E+B15003_004E+B15003_005E+"
    "B15003_006E+B15003_007E+B15003_008E+B15003_009E+B15003_010E+"
    "B15003_011E+B15003_012E+B15003_013E+B15003_014E+B15003_015E+"
    "B15003_016E;high_school=B15003_017E+B15003_018E;"
    "some_college_associate=B15003_019E+B15003_020E+B15003_021E;"
    "bachelors_plus=B15003_022E+B15003_023E+B15003_024E+B15003_025E"
)
B23025_REFERENCE_EXPRESSION = (
    "employed=B23025_004E;unemployed=B23025_005E;"
    "armed_forces=B23025_006E;not_in_labor_force=B23025_007E;"
    "population_16_plus=B23025_001E"
)


def parse_expressions(value: str) -> dict[str, tuple[str, ...]]:
    """Parse the inventory's semicolon-delimited additive expressions."""
    expressions: dict[str, tuple[str, ...]] = {}
    for expression in value.split(";"):
        output, source = expression.split("=", maxsplit=1)
        expressions[output] = tuple(source.split("+"))
    return expressions


def canonical_definitions(root: Path) -> dict[str, list[dict[str, object]]]:
    """Return the continuous POC036 definitions from the canonical inventory."""
    definitions = pd.read_csv(
        root / DEFINITIONS_PATH, dtype="string", keep_default_na=False
    )
    selected = definitions[definitions["metric_family"].isin(CANONICAL_FAMILIES)].copy()
    result = {family: [] for family in CANONICAL_FAMILIES}
    for row in selected.to_dict("records"):
        family = str(row["metric_family"])
        result[family].append(
            {
                **row,
                "expressions": parse_expressions(str(row["estimate_expression"])),
            }
        )
    if not all(result.values()):
        raise ValueError("Continuous socioeconomic definitions are incomplete")
    if [row["source_table"] for row in result["education_attainment"]] != ["B15002"]:
        raise ValueError("Education must use B15002 for the full series")
    if [row["source_table"] for row in result["employment_status"]] != ["B23001"]:
        raise ValueError("Employment must use tract-level B23001 for the full series")
    if [row["source_table"] for row in result["poverty_ratio"]] != ["C17002"]:
        raise ValueError("Poverty must use block-group C17002 for the full series")
    return result


def definition_for_year(
    definitions: Mapping[str, list[dict[str, object]]], family: str, year: int
) -> dict[str, object]:
    """Select the one canonical definition whose bounded scope includes a year."""
    matches = []
    for definition in definitions[family]:
        scope = str(definition["source_products"])
        bounds = [int(value.rsplit("_", 1)[1]) for value in scope.split("..")]
        start, end = (bounds[0], bounds[0]) if len(bounds) == 1 else bounds
        if start <= year <= end:
            matches.append(definition)
    if len(matches) != 1:
        raise ValueError(
            f"Expected one {family} definition for {year}, got {len(matches)}"
        )
    return matches[0]


def canonical_tables_for_year(year: int) -> list[str]:
    return ["B15002", "B23001", "C17002"]


def reference_tables_for_year(year: int) -> list[str]:
    tables = []
    if year >= 2015:
        tables.append("B15003")
    if year >= 2011:
        tables.append("B23025")
    return tables


def aggregate_additive_cells(
    frame: pd.DataFrame,
    expressions: Mapping[str, Iterable[str]],
) -> pd.DataFrame:
    """Aggregate published estimate cells and approximate their MOEs by RSS."""
    result = frame[
        [column for column in frame if not column.endswith(("E", "M"))]
    ].copy()
    for category, cells in expressions.items():
        estimate_cells = tuple(cells)
        moe_cells = tuple(cell[:-1] + "M" for cell in estimate_cells)
        result[f"{category}_estimate"] = frame[list(estimate_cells)].sum(axis="columns")
        result[f"{category}_moe"] = (
            frame[list(moe_cells)].pow(2).sum(axis="columns").pow(0.5)
        )
    return result


def allocate_categories(
    block_groups: pd.DataFrame,
    crosswalk: pd.DataFrame,
    categories: Iterable[str],
) -> pd.DataFrame:
    """Allocate additive block-group categories with separate estimate/MOE paths."""
    assigned = crosswalk[crosswalk["assignment_status"].eq("assigned")]
    source_id = (
        "source_geography_id"
        if "source_geography_id" in block_groups
        else "source_block_group_geoid"
    )
    allocated = assigned.merge(
        block_groups,
        left_on="source_geography_id",
        right_on=source_id,
        how="left",
        validate="many_to_one",
    )
    if (
        allocated[[f"{category}_estimate" for category in categories]]
        .isna()
        .any()
        .any()
    ):
        raise ValueError("Crosswalk references missing socioeconomic source rows")
    rows = []
    for district_id, district in allocated.groupby("target_district_id"):
        for category in categories:
            weighted_estimate = district["weight"] * district[f"{category}_estimate"]
            weighted_moe = district["weight"] * district[f"{category}_moe"]
            rows.append(
                {
                    "geography_id": int(district_id),
                    "category": category,
                    "estimate": float(weighted_estimate.sum()),
                    "margin_of_error": float(math.sqrt(weighted_moe.pow(2).sum())),
                }
            )
    return pd.DataFrame(rows)


def add_shares(frame: pd.DataFrame, denominator_category: str) -> pd.DataFrame:
    """Derive shares only after additive estimates have reached target geography."""
    result = frame.copy()
    denominator = result[result["category"].eq(denominator_category)][
        ["geography_id", "estimate"]
    ].rename(columns={"estimate": "denominator_estimate"})
    result = result.merge(
        denominator, on="geography_id", how="left", validate="many_to_one"
    )
    result["share"] = result["estimate"] / result["denominator_estimate"]
    return result


def _lookup_table(directory: Path, table_id: str) -> dict[str, int]:
    with (directory / "sequence_lookup.txt").open(
        encoding="latin1", newline=""
    ) as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        normalized = {
            str(key).strip(): str(value).strip() for key, value in row.items()
        }
        if normalized.get("Table ID") != table_id:
            continue
        position = normalized.get("Start Position") or normalized.get("position")
        if position in {None, "", "."}:
            continue
        sequence = normalized.get("Sequence Number") or normalized.get("seq")
        cells = normalized.get("Total Cells in Table") or normalized.get("cells")
        return {
            "sequence": int(str(sequence)),
            "position": int(position),
            "cells": int(str(cells).split()[0]),
        }
    raise ValueError(f"{table_id} not found in {directory / 'sequence_lookup.txt'}")


def _legacy_base_url(year: int, geography_folder: str) -> str:
    return (
        "https://www2.census.gov/programs-surveys/acs/summary_file/"
        f"{year}/data/5_year_seq_by_state/Pennsylvania/{geography_folder}"
    )


def _table_url(year: int, table_id: str) -> str:
    return (
        "https://www2.census.gov/programs-surveys/acs/summary_file/"
        f"{year}/table-based-SF/data/5YRData/acsdt5y{year}-{table_id.lower()}.dat"
    )


def download_inputs(
    root: Path,
    years: Iterable[int] = YEARS,
    *,
    include_references: bool = True,
) -> list[dict[str, object]]:
    """Download compact legacy inputs and PA-filter current nationwide table files."""
    sources = []
    for year in years:
        tables = canonical_tables_for_year(year)
        if include_references:
            tables.extend(reference_tables_for_year(year))
        if year <= 2020:
            sources.extend(_download_legacy_year(root, year, tables))
        else:
            for table_id in tables:
                sources.append(_download_filtered_table(root, year, table_id))
    return sources


def _download_legacy_year(
    root: Path, year: int, tables: Iterable[str]
) -> list[dict[str, object]]:
    directory = root / RAW_ROOT / str(year)
    directory.mkdir(parents=True, exist_ok=True)
    sources = []
    for table_id in tables:
        lookup = _lookup_table(root / f"data/raw/acs5_all_pa/{year}", table_id)
        sequence = str(lookup["sequence"]).zfill(4)
        filename = f"{year}5pa{sequence}000.zip"
        for grain, folder in (
            ("block_group", "Tracts_Block_Groups_Only"),
            ("state", "All_Geographies_Not_Tracts_Block_Groups"),
        ):
            path = directory / grain / filename
            url = f"{_legacy_base_url(year, folder)}/{filename}"
            sources.append(_download_file(path, url, year, table_id, grain))
    geography_suffix = "txt" if year == 2009 else "csv"
    geography_name = f"g{year}5pa.{geography_suffix}"
    geography_path = directory / "state" / geography_name
    geography_url = (
        f"{_legacy_base_url(year, 'All_Geographies_Not_Tracts_Block_Groups')}/"
        f"{geography_name}"
    )
    sources.append(
        _download_file(geography_path, geography_url, year, "geography", "state")
    )
    return sources


def _download_file(
    path: Path, url: str, year: int, table_id: str, grain: str
) -> dict[str, object]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        path.write_bytes(response.content)
    return _source_record(path, url, year, table_id, grain, sha256(path))


def _download_filtered_table(root: Path, year: int, table_id: str) -> dict[str, object]:
    directory = root / RAW_ROOT / str(year)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"acsdt5y{year}-{table_id.lower()}-pa.dat"
    checksum_path = path.with_suffix(".source_sha256")
    url = _table_url(year, table_id)
    missing_required_tracts = table_id == "B23001" and not _has_tract_row(path)
    if not path.exists() or not checksum_path.exists() or missing_required_tracts:
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        response.raw.decode_content = True
        digest = hashlib.sha256()
        with path.open("wb") as target:
            for index, line in enumerate(response.raw):
                digest.update(line)
                if index == 0 or line.startswith(
                    (b"0400000US42|", b"1400000US42", b"1500000US42")
                ):
                    target.write(line)
        checksum_path.write_text(digest.hexdigest() + "\n")
    source_checksum = checksum_path.read_text().strip()
    return _source_record(
        path, url, year, table_id, "state_and_block_group", source_checksum
    )


def _has_tract_row(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("rb") as source:
        return any(line.startswith(b"1400000US42") for line in source)


def _source_record(
    path: Path,
    url: str,
    year: int,
    table_id: str,
    grain: str,
    source_checksum: str,
) -> dict[str, object]:
    return {
        "producer": "U.S. Census Bureau",
        "exact_product": f"ACS {year} five-year {table_id}",
        "retrieval_timestamp": datetime.fromtimestamp(
            path.stat().st_mtime, UTC
        ).isoformat(),
        "reference_vintage": year,
        "source_url": url,
        "source_sha256": source_checksum,
        "local_extract_sha256": sha256(path),
        "local_path": path.as_posix(),
        "license": "Public federal data; cite U.S. Census Bureau",
        "crs": None,
        "schema": "ACS detailed table estimates and 90% margins of error",
        "geographic_universe": f"Pennsylvania {grain}",
    }


def _sequence_values(
    archive_path: Path,
    member: str,
    start: int,
    cells: int,
) -> dict[str, list[str]]:
    values = {}
    with ZipFile(archive_path) as archive, archive.open(member) as source:
        for raw_line in source:
            row = next(csv.reader([raw_line.decode("latin1")]))
            values[row[5]] = row[start : start + cells]
    return values


def _legacy_geographies(root: Path, year: int, grain: str) -> pd.DataFrame:
    if grain in {"block_group", "tract"}:
        path = (
            root
            / f"data/raw/acs5_all_pa/{year}/g{year}5pa.{'txt' if year == 2009 else 'csv'}"
        )
    else:
        path = (
            root
            / RAW_ROOT
            / str(year)
            / "state"
            / f"g{year}5pa.{'txt' if year == 2009 else 'csv'}"
        )
    rows = []
    if year == 2009:
        with path.open(encoding="latin1") as source:
            for line in source:
                summary_level = line[8:11]
                if grain == "block_group" and summary_level == "150":
                    rows.append(
                        (
                            line[13:20],
                            line[25:27] + line[27:30] + line[40:46] + line[46:47],
                        )
                    )
                if grain == "tract" and summary_level == "140":
                    rows.append((line[13:20], line[25:27] + line[27:30] + line[40:46]))
                if (
                    grain == "state"
                    and summary_level == "040"
                    and line[11:13] == "00"
                    and line[25:27] == "42"
                ):
                    rows.append((line[13:20], "42"))
    else:
        with path.open(newline="", encoding="latin1") as source:
            for row in csv.reader(source):
                if grain == "block_group" and row[2] == "150":
                    rows.append((row[4], row[9] + row[10] + row[13] + row[14]))
                if grain == "tract" and row[2] == "140":
                    rows.append((row[4], row[9] + row[10] + row[13]))
                if (
                    grain == "state"
                    and row[2] == "040"
                    and row[3] == "00"
                    and row[9] == "42"
                ):
                    rows.append((row[4], "42"))
    column = "geography_id" if grain == "state" else "source_geography_id"
    return pd.DataFrame(rows, columns=["LOGRECNO", column])


def load_detailed_table(
    root: Path, year: int, table_id: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load canonical estimate/MOE names for PA block groups and the direct state row."""
    if year <= 2020:
        return _load_legacy_table(root, year, table_id)
    return _load_filtered_table(root, year, table_id)


def _load_legacy_table(
    root: Path, year: int, table_id: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    lookup = _lookup_table(root / f"data/raw/acs5_all_pa/{year}", table_id)
    sequence = str(lookup["sequence"]).zfill(4)
    filename = f"{year}5pa{sequence}000.zip"
    frames = {}
    source_grain = "tract" if table_id == "B23001" else "block_group"
    for grain in (source_grain, "state"):
        archive_folder = "block_group" if grain == "tract" else grain
        archive_path = root / RAW_ROOT / str(year) / archive_folder / filename
        estimate_member = f"e{year}5pa{sequence}000.txt"
        margin_member = f"m{year}5pa{sequence}000.txt"
        start = lookup["position"] - 1
        estimates = _sequence_values(
            archive_path, estimate_member, start, lookup["cells"]
        )
        margins = _sequence_values(archive_path, margin_member, start, lookup["cells"])
        geography = _legacy_geographies(root, year, grain)
        rows = []
        for record in geography.to_dict("records"):
            logrecno = record.pop("LOGRECNO")
            if logrecno not in estimates or logrecno not in margins:
                continue
            row = record
            for cell in range(1, lookup["cells"] + 1):
                row[f"{table_id}_{cell:03d}E"] = estimates[logrecno][cell - 1]
                row[f"{table_id}_{cell:03d}M"] = margins[logrecno][cell - 1]
            rows.append(row)
        frames[grain] = _normalize_table(pd.DataFrame(rows), table_id)
    return frames[source_grain], frames["state"]


def _load_filtered_table(
    root: Path, year: int, table_id: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = root / RAW_ROOT / str(year) / f"acsdt5y{year}-{table_id.lower()}-pa.dat"
    frame = pd.read_csv(path, sep="|", dtype="string", keep_default_na=False)
    rename = {}
    for column in frame.columns:
        if column.startswith(f"{table_id}_E"):
            rename[column] = f"{table_id}_{column[-3:]}E"
        if column.startswith(f"{table_id}_M"):
            rename[column] = f"{table_id}_{column[-3:]}M"
    frame = frame.rename(columns=rename)
    source_prefix = "1400000US42" if table_id == "B23001" else "1500000US42"
    block_groups = frame[frame["GEO_ID"].str.startswith(source_prefix)].copy()
    block_groups["source_geography_id"] = block_groups["GEO_ID"].str.slice(9)
    state = frame[frame["GEO_ID"].eq("0400000US42")].copy()
    state["geography_id"] = "42"
    return _normalize_table(
        block_groups.drop(columns=["GEO_ID", "NAME"], errors="ignore"), table_id
    ), _normalize_table(
        state.drop(columns=["GEO_ID", "NAME"], errors="ignore"), table_id
    )


def _normalize_table(frame: pd.DataFrame, table_id: str) -> pd.DataFrame:
    result = frame.copy()
    value_columns = [column for column in result if column.startswith(f"{table_id}_")]
    result[value_columns] = result[value_columns].apply(pd.to_numeric, errors="raise")
    if result[value_columns].lt(0).any().any():
        raise ValueError(f"Negative estimate/MOE sentinel in {table_id}")
    return result


def _crosswalk_path(root: Path, year: int, plan_id: str) -> Path:
    regime = regime_for_year(year)
    return root / CROSSWALK_ROOT / f"{regime}__{plan_id}__v2.parquet"


def _metric_crosswalk(root: Path, year: int, plan_id: str, family: str) -> pd.DataFrame:
    block_group_crosswalk = pd.read_parquet(_crosswalk_path(root, year, plan_id))
    if family != "employment_status":
        return block_group_crosswalk
    population = load_acs5_block_group_population(
        year, root / f"data/raw/acs5_all_pa/{year}"
    ).rename(columns={"source_block_group_geoid": "source_geography_id"})
    assigned = block_group_crosswalk[
        block_group_crosswalk["assignment_status"].eq("assigned")
    ].merge(population, on="source_geography_id", how="left", validate="many_to_one")
    assigned["source_geography_id"] = assigned["source_geography_id"].str.slice(0, 11)
    assigned["raw_support"] = assigned["weight"] * assigned["B01003_001E"]
    grouped = assigned.groupby(
        ["source_geography_id", "target_district_id"], as_index=False
    )["raw_support"].sum()
    totals = grouped.groupby("source_geography_id")["raw_support"].transform("sum")
    grouped = grouped[totals.gt(0)].copy()
    totals = totals[totals.gt(0)]
    grouped["weight"] = grouped["raw_support"] / totals
    grouped["assignment_status"] = "assigned"
    return grouped


def applicable_partitions(root: Path, products: pd.DataFrame) -> pd.DataFrame:
    """Expand accepted ACS product/plan applicability to both chambers."""
    accepted = pd.read_csv(root / PARTITIONS_PATH, dtype="string", keep_default_na=False)
    accepted = accepted[
        accepted["population_product_id"].str.startswith("acs5_")
    ].copy()
    plans = pd.read_csv(root / PLANS_PATH, dtype="string", keep_default_na=False)
    product_fields = products[
        ["product_id", "estimate_year", "release_date"]
    ].rename(columns={"product_id": "population_product_id"})
    accepted = accepted.merge(
        product_fields,
        on="population_product_id",
        how="left",
        validate="many_to_one",
    )
    rows = []
    for record in accepted.to_dict("records"):
        for chamber in ("house", "senate"):
            matching = plans[
                plans["target_chamber"].eq(chamber)
                & plans["reference_vintage"].eq(
                    record["target_plan_reference_vintage"]
                )
            ]
            if len(matching) != 1:
                raise ValueError(
                    "Accepted ACS applicability does not resolve to one legislative plan"
                )
            rows.append(
                {
                    **record,
                    "target_chamber": chamber,
                    "target_plan_id": matching.iloc[0]["target_plan_id"],
                    "support_regime": regime_for_year(int(record["estimate_year"])),
                    "expected_district_count": EXPECTED_DISTRICTS[chamber],
                    "cutoff_basis": (
                        "inherits accepted ACS product/plan/election applicability "
                        "from legislative_population_partitions_v1.csv"
                    ),
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["estimate_year", "target_plan_id"], kind="stable"
    )


def _source_conservation_check(
    year: int,
    family: str,
    values: pd.DataFrame,
    categories: Iterable[str],
    denominator: str,
) -> dict[str, object]:
    category_total = values[
        [f"{category}_estimate" for category in categories]
    ].sum(axis="columns")
    deltas = category_total - values[f"{denominator}_estimate"]
    return {
        "check_id": f"{year}:{family}:source_rows_categories_conserve",
        "passed": bool(deltas.abs().le(1e-6).all()),
        "row_count": len(values),
        "rows_outside_tolerance": int(deltas.abs().gt(1e-6).sum()),
        "maximum_absolute_delta": float(deltas.abs().max()),
    }


def _partition_checks(
    year: int,
    family: str,
    partition: Mapping[str, object],
    allocated: pd.DataFrame,
    state_values: pd.DataFrame,
    categories: list[str],
    denominator: str,
) -> list[dict[str, object]]:
    prefix = f"{year}:{family}:{partition['target_plan_id']}"
    observed_districts = allocated["geography_id"].nunique()
    target_totals = allocated.groupby("category")["estimate"].sum()
    state_totals = state_values.set_index("category")["estimate"]
    total_deltas = target_totals - state_totals
    wide = allocated.pivot(
        index="geography_id", columns="category", values="estimate"
    )
    district_deltas = wide[categories].sum(axis="columns") - wide[denominator]
    return [
        {
            "check_id": f"{prefix}:district_coverage",
            "passed": observed_districts == int(partition["expected_district_count"]),
            "observed": observed_districts,
            "expected": int(partition["expected_district_count"]),
        },
        {
            "check_id": f"{prefix}:categories_conserve_state",
            "passed": bool(total_deltas.abs().le(1e-6).all()),
            "maximum_absolute_delta": float(total_deltas.abs().max()),
        },
        {
            "check_id": f"{prefix}:district_categories_conserve_parent",
            "passed": bool(district_deltas.abs().le(1e-6).all()),
            "districts_outside_tolerance": int(
                district_deltas.abs().gt(1e-6).sum()
            ),
            "maximum_absolute_delta": float(district_deltas.abs().max()),
        },
        {
            "check_id": f"{prefix}:release_cutoff_provenance_present",
            "passed": bool(partition["release_date"])
            and bool(partition["first_applicable_election"])
            and bool(partition["last_applicable_election"]),
            "release_date": partition["release_date"],
            "first_applicable_election": partition["first_applicable_election"],
            "last_applicable_election": partition["last_applicable_election"],
            "cutoff_basis": partition["cutoff_basis"],
        },
    ]


def _with_parent(
    values: pd.DataFrame, source: pd.DataFrame, table_id: str, parent: str
) -> pd.DataFrame:
    result = values.copy()
    result[f"{parent}_estimate"] = source[f"{table_id}_001E"]
    result[f"{parent}_moe"] = source[f"{table_id}_001M"]
    return result


def _comparison_check(
    year: int,
    family: str,
    grain: str,
    left: pd.DataFrame,
    right: pd.DataFrame,
    categories: Iterable[str],
) -> dict[str, object]:
    identifier = "source_geography_id" if grain != "state" else "geography_id"
    columns = [identifier]
    for category in categories:
        columns.extend([f"{category}_estimate", f"{category}_moe"])
    comparison = left[columns].merge(
        right[columns],
        on=identifier,
        how="outer",
        suffixes=("_detailed", "_published"),
        validate="one_to_one",
        indicator=True,
    )
    estimate_deltas = []
    moe_deltas = []
    for category in categories:
        estimate_deltas.append(
            (
                comparison[f"{category}_estimate_detailed"]
                - comparison[f"{category}_estimate_published"]
            ).abs()
        )
        moe_deltas.append(
            (
                comparison[f"{category}_moe_detailed"]
                - comparison[f"{category}_moe_published"]
            ).abs()
        )
    max_estimate_delta = float(pd.concat(estimate_deltas, ignore_index=True).max())
    max_moe_delta = float(pd.concat(moe_deltas, ignore_index=True).max())
    return {
        "check_id": f"{year}:{family}:{grain}:reference_estimates_equal",
        "passed": bool(comparison["_merge"].eq("both").all())
        and math.isclose(max_estimate_delta, 0.0, abs_tol=1e-6),
        "row_count": len(comparison),
        "maximum_absolute_estimate_delta": max_estimate_delta,
        "maximum_absolute_moe_delta_not_required_to_match": max_moe_delta,
    }


def _aggregate_block_groups_to_tract(
    values: pd.DataFrame, categories: Iterable[str]
) -> pd.DataFrame:
    result = values.copy()
    result["source_geography_id"] = result["source_geography_id"].str.slice(0, 11)
    aggregations = {}
    for category in categories:
        aggregations[f"{category}_estimate"] = "sum"
        result[f"{category}_moe_squared"] = result[f"{category}_moe"].pow(2)
        aggregations[f"{category}_moe_squared"] = "sum"
    grouped = result.groupby("source_geography_id", as_index=False).agg(aggregations)
    for category in categories:
        grouped[f"{category}_moe"] = grouped.pop(f"{category}_moe_squared").pow(0.5)
    return grouped


def overlap_checks(
    root: Path,
    years: Iterable[int],
    definitions: Mapping[str, list[dict[str, object]]],
) -> list[dict[str, object]]:
    """Validate point-estimate equivalence without requiring MOE equivalence."""
    checks = []
    detailed_employment = definition_for_year(definitions, "employment_status", 2009)[
        "expressions"
    ]
    published_employment = parse_expressions(B23025_REFERENCE_EXPRESSION)
    education = definition_for_year(definitions, "education_attainment", 2009)
    b15002_expressions = education["expressions"]
    b15003_expressions = parse_expressions(B15003_REFERENCE_EXPRESSION)
    for year in years:
        if year >= 2011:
            detailed = load_detailed_table(root, year, "B23001")
            published = load_detailed_table(root, year, "B23025")
            categories = [
                "employed",
                "unemployed",
                "armed_forces",
                "not_in_labor_force",
                "population_16_plus",
            ]
            for grain, detailed_source, published_source in zip(
                ("tract", "state"), detailed, published, strict=True
            ):
                left = aggregate_additive_cells(detailed_source, detailed_employment)
                right = aggregate_additive_cells(published_source, published_employment)
                if grain == "tract":
                    right = _aggregate_block_groups_to_tract(right, categories)
                checks.append(
                    _comparison_check(
                        year, "employment_status", grain, left, right, categories
                    )
                )
        if year >= 2015:
            b15002 = load_detailed_table(root, year, "B15002")
            b15003 = load_detailed_table(root, year, "B15003")
            categories = [
                "below_high_school",
                "high_school",
                "some_college_associate",
                "bachelors_plus",
                "population_25_plus",
            ]
            for grain, b15002_source, b15003_source in zip(
                ("block_group", "state"), b15002, b15003, strict=True
            ):
                left = _with_parent(
                    aggregate_additive_cells(b15002_source, b15002_expressions),
                    b15002_source,
                    "B15002",
                    "population_25_plus",
                )
                right = _with_parent(
                    aggregate_additive_cells(b15003_source, b15003_expressions),
                    b15003_source,
                    "B15003",
                    "population_25_plus",
                )
                checks.append(
                    _comparison_check(
                        year, "education_attainment", grain, left, right, categories
                    )
                )
    return checks


def run(root: Path, years: Iterable[int] = YEARS) -> dict[str, object]:
    """Build full legislative partitions plus statewide and sample trend evidence."""
    root = root.resolve()
    definitions = canonical_definitions(root)
    products = pd.read_csv(root / PRODUCTS_PATH, dtype="string", keep_default_na=False)
    partitions = applicable_partitions(root, products)
    records = []
    partition_records = []
    checks = []
    crosswalk_cache: dict[tuple[int, str, str], pd.DataFrame] = {}
    selected_years = tuple(years)
    partitions = partitions[
        partitions["estimate_year"].astype(int).isin(selected_years)
    ].copy()
    for year in selected_years:
        product = products[products["estimate_year"].eq(str(year))].iloc[0]
        for family in sorted(definitions):
            definition = definition_for_year(definitions, family, year)
            table_id = str(definition["source_table"])
            expressions = definition["expressions"]
            block_groups, state = load_detailed_table(root, year, table_id)
            block_group_values = aggregate_additive_cells(block_groups, expressions)
            state_values = aggregate_additive_cells(state, expressions)
            categories = str(definition["additive_output_categories"]).split("|")
            denominator = {
                "education_attainment": "population_25_plus",
                "employment_status": "population_16_plus",
                "poverty_ratio": "poverty_status_determined",
            }[family]
            if family in {"education_attainment", "poverty_ratio"}:
                state_values[f"{denominator}_estimate"] = state[f"{table_id}_001E"]
                state_values[f"{denominator}_moe"] = state[f"{table_id}_001M"]
                block_group_values[f"{denominator}_estimate"] = block_groups[
                    f"{table_id}_001E"
                ]
                block_group_values[f"{denominator}_moe"] = block_groups[
                    f"{table_id}_001M"
                ]
            categories_with_parent = [*categories, denominator]
            checks.append(
                _source_conservation_check(
                    year,
                    family,
                    block_group_values,
                    categories,
                    denominator,
                )
            )
            state_long = _wide_to_long(state_values, categories_with_parent)
            state_long["geography_type"] = "state"
            state_long["geography_id"] = "42"
            records.append(
                _annotate(
                    state_long, product, family, table_id, "direct_published_state"
                )
            )
            for chamber, sample_ids in SAMPLE_DISTRICTS.items():
                plan_id = CURRENT_PLANS[chamber]
                cache_key = (year, plan_id, family)
                if cache_key not in crosswalk_cache:
                    crosswalk_cache[cache_key] = _metric_crosswalk(
                        root, year, plan_id, family
                    )
                crosswalk = crosswalk_cache[cache_key]
                allocated = allocate_categories(
                    block_group_values, crosswalk, categories_with_parent
                )
                allocated = allocated[allocated["geography_id"].isin(sample_ids)].copy()
                allocated["geography_type"] = chamber
                geography_method = (
                    "modeled_tract_allocation_from_acs_population_support"
                    if family == "employment_status"
                    else "modeled_block_group_allocation"
                )
                records.append(
                    _annotate(
                        allocated,
                        product,
                        family,
                        table_id,
                        geography_method,
                    )
                )
            year_partitions = partitions[
                partitions["estimate_year"].eq(str(year))
            ]
            for partition in year_partitions.to_dict("records"):
                plan_id = str(partition["target_plan_id"])
                cache_key = (year, plan_id, family)
                if cache_key not in crosswalk_cache:
                    crosswalk_cache[cache_key] = _metric_crosswalk(
                        root, year, plan_id, family
                    )
                allocated = allocate_categories(
                    block_group_values,
                    crosswalk_cache[cache_key],
                    categories_with_parent,
                )
                checks.extend(
                    _partition_checks(
                        year,
                        family,
                        partition,
                        allocated,
                        state_long,
                        categories,
                        denominator,
                    )
                )
                allocated = add_shares(allocated, denominator)
                allocated["geography_type"] = partition["target_chamber"]
                geography_method = (
                    "modeled_tract_allocation_from_acs_population_support"
                    if family == "employment_status"
                    else "modeled_block_group_allocation"
                )
                allocated = _annotate(
                    allocated,
                    product,
                    family,
                    table_id,
                    geography_method,
                )
                allocated["population_product_id"] = partition[
                    "population_product_id"
                ]
                allocated["source_grain"] = definition["source_grain"]
                allocated["support_regime"] = partition["support_regime"]
                allocated["target_plan_id"] = plan_id
                allocated["target_plan_reference_vintage"] = partition[
                    "target_plan_reference_vintage"
                ]
                allocated["first_applicable_election"] = partition[
                    "first_applicable_election"
                ]
                allocated["last_applicable_election"] = partition[
                    "last_applicable_election"
                ]
                allocated["release_date"] = partition["release_date"]
                allocated["cutoff_basis"] = partition["cutoff_basis"]
                allocated["aggregation_note"] = definition["aggregation_note"]
                partition_records.append(allocated)
            state_category_total = float(
                state_long[state_long["category"].isin(categories)]["estimate"].sum()
            )
            state_parent = float(
                state_long[state_long["category"].eq(denominator)]["estimate"].iloc[0]
            )
            checks.append(
                {
                    "check_id": f"{year}:{family}:state_categories_conserve",
                    "passed": math.isclose(
                        state_category_total, state_parent, abs_tol=1e-6
                    ),
                    "observed_delta": state_category_total - state_parent,
                }
            )
    checks.extend(overlap_checks(root, selected_years, definitions))
    combined = pd.concat(records, ignore_index=True)
    combined = _derive_shares(combined)
    derived_rates = _derive_rates(combined)
    change_summary = _build_change_summary(combined, derived_rates)
    legislative = pd.concat(partition_records, ignore_index=True).sort_values(
        [
            "population_product_id",
            "metric_family",
            "target_plan_id",
            "geography_id",
            "category",
        ],
        kind="stable",
    )
    output_dir = root / OUTPUT_ROOT
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "socioeconomic_sample_trends_v1.parquet"
    rates_path = output_dir / "socioeconomic_derived_rates_v1.parquet"
    change_path = output_dir / "socioeconomic_change_summary_v1.parquet"
    legislative_path = output_dir / "socioeconomic_legislative_partitions_v1.parquet"
    combined.to_parquet(output_path, index=False)
    derived_rates.to_parquet(rates_path, index=False)
    change_summary.to_parquet(change_path, index=False)
    legislative_write = write_immutable_parquet(
        legislative,
        legislative_path,
        [
            "population_product_id",
            "metric_family",
            "target_plan_id",
            "geography_id",
            "category",
        ],
    )
    dependency_paths = {
        "metric_definitions": root / DEFINITIONS_PATH,
        "acs_products": root / PRODUCTS_PATH,
        "accepted_partition_applicability": root / PARTITIONS_PATH,
        "legislative_plans": root / PLANS_PATH,
        "source_manifest": root
        / ARTIFACT_ROOT
        / "socioeconomic_input_manifest.json",
    }
    crosswalk_hashes = {
        _crosswalk_path(root, year, plan_id).relative_to(root).as_posix(): sha256(
            _crosswalk_path(root, year, plan_id)
        )
        for year, plan_id, _family in sorted(crosswalk_cache)
    }
    qa = {
        "task": "POC036",
        "stage": "continuous_socioeconomic_trends",
        "years": list(selected_years),
        "fixed_plan_ids": CURRENT_PLANS,
        "sample_districts": SAMPLE_DISTRICTS,
        "legislative_partition_count": int(
            partitions.shape[0] * len(CANONICAL_FAMILIES)
        ),
        "uncertainty_note": UNCERTAINTY_NOTE,
        "trend_note": TREND_NOTE,
        "dependency_hashes": {
            name: sha256(path) for name, path in dependency_paths.items()
        },
        "crosswalk_file_hashes": crosswalk_hashes,
        "checks": checks,
        "hashes": {
            "sample_trends": logical_frame_hash(
                combined,
                [
                    "estimate_year",
                    "metric_family",
                    "geography_type",
                    "geography_id",
                    "category",
                ],
            ),
            "derived_rates": logical_frame_hash(
                derived_rates,
                ["estimate_year", "geography_type", "geography_id", "rate_id"],
            ),
            "change_summary": logical_frame_hash(
                change_summary,
                ["geography_type", "geography_id", "metric_id"],
            ),
            "legislative_partitions": logical_frame_hash(
                legislative,
                [
                    "population_product_id",
                    "metric_family",
                    "target_plan_id",
                    "geography_id",
                    "category",
                ],
            ),
        },
        "artifact_writes": {"legislative_partitions": legislative_write},
        "passed": all_pass(checks),
    }
    artifact_dir = root / ARTIFACT_ROOT
    artifact_dir.mkdir(parents=True, exist_ok=True)
    write_json(artifact_dir / "socioeconomic_trend_qa.json", qa)
    if not qa["passed"]:
        raise RuntimeError("POC036 socioeconomic trend checks failed")
    return qa


def _wide_to_long(frame: pd.DataFrame, categories: Iterable[str]) -> pd.DataFrame:
    rows = []
    for category in categories:
        rows.append(
            pd.DataFrame(
                {
                    "category": category,
                    "estimate": frame[f"{category}_estimate"],
                    "margin_of_error": frame[f"{category}_moe"],
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def _annotate(
    frame: pd.DataFrame,
    product: pd.Series,
    family: str,
    table_id: str,
    geography_method: str,
) -> pd.DataFrame:
    result = frame.copy()
    result["geography_id"] = result["geography_id"].astype("string")
    result["estimate_year"] = int(product["estimate_year"])
    result["period_start"] = product["period_start"]
    result["period_end"] = product["period_end"]
    result["metric_family"] = family
    result["source_table"] = table_id
    result["geography_method"] = geography_method
    result["uncertainty_note"] = UNCERTAINTY_NOTE
    return result


def _derive_shares(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    key = ["estimate_year", "metric_family", "geography_type", "geography_id"]
    denominator_names = {
        "education_attainment": "population_25_plus",
        "employment_status": "population_16_plus",
        "poverty_ratio": "poverty_status_determined",
    }
    result["denominator_category"] = result["metric_family"].map(denominator_names)
    denominators = result[result["category"].eq(result["denominator_category"])][
        [*key, "estimate"]
    ].rename(columns={"estimate": "denominator_estimate"})
    result = result.merge(denominators, on=key, how="left", validate="many_to_one")
    result["share"] = result["estimate"] / result["denominator_estimate"]
    return result.sort_values([*key, "category"], kind="stable").reset_index(drop=True)


def _derive_rates(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive compatible employment and poverty rates after target allocation."""
    rows = [_derive_employment_rates(frame), _derive_poverty_rates(frame)]
    return pd.concat(rows, ignore_index=True).sort_values(
        ["estimate_year", "geography_type", "geography_id", "rate_id"],
        kind="stable",
    )


def _derive_employment_rates(frame: pd.DataFrame) -> pd.DataFrame:
    employment = frame[frame["metric_family"].eq("employment_status")]
    key = ["estimate_year", "geography_type", "geography_id"]
    estimates = employment.pivot(
        index=key, columns="category", values="estimate"
    ).reset_index()
    civilian_labor_force = estimates["employed"] + estimates["unemployed"]
    labor_force = civilian_labor_force + estimates["armed_forces"]
    rates = {
        "employment_population_ratio": estimates["employed"]
        / estimates["population_16_plus"],
        "civilian_unemployment_rate": estimates["unemployed"] / civilian_labor_force,
        "labor_force_participation_rate": labor_force / estimates["population_16_plus"],
    }
    rows = []
    for rate_id, values in rates.items():
        row = estimates[key].copy()
        row["rate_id"] = rate_id
        row["rate"] = values
        row["rate_moe"] = pd.NA
        row["derivation_note"] = (
            "Derived after target allocation from compatible additive counts; "
            "no ratio MOE is reported because covariance is unavailable."
        )
        rows.append(row)
    return pd.concat(rows, ignore_index=True)


def _derive_poverty_rates(frame: pd.DataFrame) -> pd.DataFrame:
    poverty = frame[frame["metric_family"].eq("poverty_ratio")]
    key = ["estimate_year", "geography_type", "geography_id"]
    estimates = poverty.pivot(
        index=key, columns="category", values="estimate"
    ).reset_index()
    rates = {
        "below_poverty_line": (
            estimates["under_0_50"] + estimates["ratio_0_50_0_99"]
        )
        / estimates["poverty_status_determined"],
        "below_200_percent_poverty": (
            estimates["under_0_50"]
            + estimates["ratio_0_50_0_99"]
            + estimates["ratio_1_00_1_24"]
            + estimates["ratio_1_25_1_49"]
            + estimates["ratio_1_50_1_84"]
            + estimates["ratio_1_85_1_99"]
        )
        / estimates["poverty_status_determined"],
    }
    rows = []
    for rate_id, values in rates.items():
        row = estimates[key].copy()
        row["rate_id"] = rate_id
        row["rate"] = values
        row["rate_moe"] = pd.NA
        row["derivation_note"] = (
            "Derived after target allocation by summing mutually exclusive "
            "published C17002 bands and dividing by C17002_001E; no ratio MOE "
            "is reported because covariance is unavailable."
        )
        rows.append(row)
    return pd.concat(rows, ignore_index=True)


def _build_change_summary(
    frame: pd.DataFrame, derived_rates: pd.DataFrame
) -> pd.DataFrame:
    endpoint_years = {min(YEARS), max(YEARS)}
    distributions = frame[
        frame["metric_family"].isin({"education_attainment", "poverty_ratio"})
        & ~frame["category"].isin(
            {"population_25_plus", "poverty_status_determined"}
        )
        & frame["estimate_year"].isin(endpoint_years)
    ][["estimate_year", "geography_type", "geography_id", "category", "share"]]
    distributions = distributions.rename(
        columns={"category": "metric_id", "share": "value"}
    )
    rates = derived_rates[derived_rates["estimate_year"].isin(endpoint_years)][
        ["estimate_year", "geography_type", "geography_id", "rate_id", "rate"]
    ].rename(columns={"rate_id": "metric_id", "rate": "value"})
    endpoints = pd.concat([distributions, rates], ignore_index=True)
    summary = endpoints.pivot(
        index=["geography_type", "geography_id", "metric_id"],
        columns="estimate_year",
        values="value",
    ).reset_index()
    summary = summary.rename(
        columns={min(YEARS): "value_2009", max(YEARS): "value_2024"}
    )
    summary["percentage_point_change"] = (
        summary["value_2024"] - summary["value_2009"]
    ) * 100
    return summary.sort_values(
        ["geography_type", "geography_id", "metric_id"], kind="stable"
    ).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--canonical-only", action="store_true")
    parser.add_argument("--years", nargs="*", type=int, default=list(YEARS))
    args = parser.parse_args()
    if args.download:
        root = args.root.resolve()
        sources = download_inputs(
            root,
            args.years,
            include_references=not args.canonical_only,
        )
        for source in sources:
            source["local_path"] = (
                Path(str(source["local_path"])).relative_to(root).as_posix()
            )
        manifest = {
            "task": "POC036",
            "stage": "socioeconomic_source_inventory",
            "definition_sha256": sha256(root / DEFINITIONS_PATH),
            "source_count": len(sources),
            "sources": sources,
        }
        write_json(root / ARTIFACT_ROOT / "socioeconomic_input_manifest.json", manifest)
        print(json.dumps({"downloaded_sources": len(sources)}, sort_keys=True))
        return
    qa = run(args.root, args.years)
    print(json.dumps({"passed": qa["passed"], "checks": len(qa["checks"])}))


if __name__ == "__main__":
    main()
