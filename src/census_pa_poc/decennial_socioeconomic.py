"""Build cutoff-safe 1990 and 2000 decennial socioeconomic anchors.

The decennial long-form tables are sample estimates.  They publish no
cell-level margins of error, so this module leaves MOE values missing and
labels that limitation explicitly rather than writing zeroes.
"""

from __future__ import annotations

import csv
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
import pyogrio

from census_pa_poc.sources import (
    load_2000_pl94_block_population,
    sha256,
)
from census_pa_poc.statewide_1990 import SOURCES as SOURCES_1990
from census_pa_poc.statewide_2000 import SOURCES as SOURCES_2000
from census_pa_poc.validation import (
    all_pass,
    logical_frame_hash,
    write_immutable_parquet,
    write_json,
)

RAW_1990 = "data/raw/census_1990_pa_stf3"
RAW_2000 = "data/raw/census_2000_pa_sf3"
CROSSWALK_ROOT = "data/processed/direct_legislative/poc029/decennial_crosswalks"
OUTPUT_PATH = (
    "data/processed/direct_legislative/poc039_support/"
    "decennial_socioeconomic_legislative_v2.parquet"
)
QA_PATH = "artifacts/poc039/decennial_socioeconomic_qa_v2.json"

PRODUCTS = {
    "dec_socio_1990_stf3": {
        "estimate_year": 1990,
        "period_start": "1989-01-01",
        "period_end": "1990-04-01",
        "release_date": "1992-08-27",
        "source_grain": "1990 Census block group",
        "source_product": "1990 Census Summary Tape File 3A",
    },
    "dec_socio_2000_sf3": {
        "estimate_year": 2000,
        "period_start": "1999-01-01",
        "period_end": "2000-04-01",
        "release_date": "2002-09-25",
        "source_grain": "2000 Census block group",
        "source_product": "Census 2000 Summary File 3",
    },
}

PARENT_CATEGORIES = {
    "education_attainment": "population_25_plus",
    "employment_status": "population_16_plus",
    "poverty_ratio": "poverty_status_determined",
}

SOURCE_TABLES = {
    "dec_socio_1990_stf3": {
        "education_attainment": "P057",
        "employment_status": "P070",
        "poverty_ratio": "P121",
    },
    "dec_socio_2000_sf3": {
        "education_attainment": "P037",
        "employment_status": "P043",
        "poverty_ratio": "P088",
    },
}

CATEGORY_CELLS = {
    "dec_socio_1990_stf3": {
        "education_attainment": {
            "population_25_plus": tuple(f"P057{i:04d}" for i in range(1, 8)),
            "below_high_school": ("P0570001", "P0570002"),
            "high_school": ("P0570003",),
            "some_college_associate": ("P0570004", "P0570005"),
            "bachelors_plus": ("P0570006", "P0570007"),
        },
        "employment_status": {
            "population_16_plus": tuple(f"P070{i:04d}" for i in range(1, 9)),
            "armed_forces": ("P0700001", "P0700005"),
            "employed": ("P0700002", "P0700006"),
            "unemployed": ("P0700003", "P0700007"),
            "not_in_labor_force": ("P0700004", "P0700008"),
        },
        "poverty_ratio": {
            "poverty_status_determined": tuple(f"P121{i:04d}" for i in range(1, 10)),
            "under_0_50": ("P1210001",),
            "ratio_0_50_0_99": ("P1210002", "P1210003"),
            "ratio_1_00_1_24": ("P1210004",),
            "ratio_1_25_1_49": ("P1210005",),
            "ratio_1_50_1_84": ("P1210006", "P1210007"),
            "ratio_1_85_1_99": ("P1210008",),
            "ratio_2_00_plus": ("P1210009",),
        },
    },
    "dec_socio_2000_sf3": {
        "education_attainment": {
            "population_25_plus": ("P037001",),
            "below_high_school": (
                *(f"P037{i:03d}" for i in range(3, 11)),
                *(f"P037{i:03d}" for i in range(20, 28)),
            ),
            "high_school": ("P037011", "P037028"),
            "some_college_associate": (
                "P037012",
                "P037013",
                "P037014",
                "P037029",
                "P037030",
                "P037031",
            ),
            "bachelors_plus": (
                *(f"P037{i:03d}" for i in range(15, 19)),
                *(f"P037{i:03d}" for i in range(32, 36)),
            ),
        },
        "employment_status": {
            "population_16_plus": ("P043001",),
            "armed_forces": ("P043004", "P043011"),
            "employed": ("P043006", "P043013"),
            "unemployed": ("P043007", "P043014"),
            "not_in_labor_force": ("P043008", "P043015"),
        },
        "poverty_ratio": {
            "poverty_status_determined": ("P088001",),
            "under_0_50": ("P088002",),
            "ratio_0_50_0_99": ("P088003", "P088004"),
            "ratio_1_00_1_24": ("P088005",),
            "ratio_1_25_1_49": ("P088006",),
            "ratio_1_50_1_84": ("P088007", "P088008"),
            "ratio_1_85_1_99": ("P088009",),
            "ratio_2_00_plus": ("P088010",),
        },
    },
}

SEGMENTS_2000 = {
    "P037": ("pa00003_uf3.zip", "pa00003.uf3", 206, 35),
    "P043": ("pa00004_uf3.zip", "pa00004.uf3", 134, 15),
    "P088": ("pa00007_uf3.zip", "pa00007.uf3", 118, 10),
}


def load_1990_block_groups(root: Path) -> pd.DataFrame:
    """Read the three selected STF3A segments at summary level 150."""
    raw_root = root / RAW_1990
    tables = {}
    for family, table_id in SOURCE_TABLES["dec_socio_1990_stf3"].items():
        segment = {"P057": "10", "P070": "12", "P121": "23"}[table_id]
        frames = []
        for disc in ("48", "49", "50"):
            path = raw_root / f"CD90_3A_{disc}" / f"stf3{segment}pa.dbf"
            cells = _all_cells("dec_socio_1990_stf3", family)
            frame = pyogrio.read_dataframe(
                path,
                read_geometry=False,
                columns=["SUMLEV", "STATEFP", "CNTY", "TRACTBNA", "BLCKGR", *cells],
            )
            frame = frame[frame["SUMLEV"].eq("150")].copy()
            frame["source_geography_id"] = (
                frame["STATEFP"].str.strip().str.zfill(2)
                + frame["CNTY"].str.strip().str.zfill(3)
                + frame["TRACTBNA"].str.strip().str.ljust(6, "0")
                + frame["BLCKGR"].str.strip()
            )
            frames.append(frame[["source_geography_id", *cells]])
        combined = pd.concat(frames, ignore_index=True)
        if combined["source_geography_id"].duplicated().any():
            raise ValueError(f"duplicate 1990 block groups in {table_id}")
        tables[family] = _collapse_source_cells(combined, "dec_socio_1990_stf3", family)
    return pd.concat(tables.values(), ignore_index=True)


def load_2000_block_groups(root: Path) -> pd.DataFrame:
    """Read selected SF3 cells and join them to summary-level-150 geography."""
    raw_root = root / RAW_2000
    geography = _load_2000_block_group_geography(raw_root / "pageo_uf3.zip")
    families = []
    for family, table_id in SOURCE_TABLES["dec_socio_2000_sf3"].items():
        archive_name, member, start, count = SEGMENTS_2000[table_id]
        cells = [f"{table_id}{index:03d}" for index in range(1, count + 1)]
        records = []
        with (
            ZipFile(raw_root / archive_name) as archive,
            archive.open(member) as source,
        ):
            for raw_line in source:
                row = next(csv.reader([raw_line.decode("latin-1")]))
                geoid = geography.get(row[4])
                if geoid is None:
                    continue
                values = row[5 + start : 5 + start + count]
                records.append(
                    {"source_geography_id": geoid, **dict(zip(cells, values))}
                )
        frame = pd.DataFrame(records)
        frame[cells] = frame[cells].apply(pd.to_numeric, errors="raise")
        families.append(_collapse_source_cells(frame, "dec_socio_2000_sf3", family))
    return pd.concat(families, ignore_index=True)


def _load_2000_block_group_geography(archive_path: Path) -> dict[str, str]:
    result = {}
    with ZipFile(archive_path) as archive, archive.open("pageo.uf3") as source:
        for raw_line in source:
            line = raw_line.decode("latin-1")
            if line[8:11] != "150" or line[29:31] != "42":
                continue
            result[line[18:25]] = line[29:31] + line[31:34] + line[55:61] + line[61:62]
    return result


def _all_cells(product_id: str, family: str) -> list[str]:
    expressions = CATEGORY_CELLS[product_id][family]
    return sorted({cell for cells in expressions.values() for cell in cells})


def _collapse_source_cells(
    frame: pd.DataFrame, product_id: str, family: str
) -> pd.DataFrame:
    rows = []
    for category, cells in CATEGORY_CELLS[product_id][family].items():
        estimate = frame[list(cells)].sum(axis="columns")
        rows.append(
            pd.DataFrame(
                {
                    "source_geography_id": frame["source_geography_id"],
                    "metric_family": family,
                    "category": category,
                    "estimate": estimate,
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def block_group_crosswalk(
    root: Path, product_year: int, chamber: str, plan_id: str
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Collapse an accepted block crosswalk using same-census population support."""
    product_id = f"dec_{product_year}"
    path = root / CROSSWALK_ROOT / f"{product_id}__{plan_id}__v1.parquet"
    crosswalk = pd.read_parquet(path)
    crosswalk = crosswalk[crosswalk["assignment_status"].eq("assigned")].copy()
    population = _load_block_population(root, product_year)
    merged = crosswalk.merge(
        population, on="source_geography_id", how="left", validate="many_to_one"
    )
    if merged["P0010001"].isna().any():
        raise ValueError(f"missing {product_year} block population in {path.name}")
    merged["source_geography_id"] = merged["source_block_group_id"]
    merged["raw_support"] = merged["weight"] * merged["P0010001"]
    grouped = merged.groupby(
        ["source_geography_id", "target_district_id"], as_index=False
    )["raw_support"].sum()
    totals = grouped.groupby("source_geography_id")["raw_support"].transform("sum")
    positive = grouped[totals.gt(0)].copy()
    positive["weight"] = positive["raw_support"] / totals[totals.gt(0)]
    positive["source_dataset_id"] = product_id
    positive["source_reference_vintage"] = str(product_year)
    positive["target_chamber"] = chamber
    positive["target_plan_id"] = plan_id
    positive["target_plan_reference_vintage"] = plan_id.split("_")[2]
    positive["method_id"] = (
        "collapse_accepted_block_crosswalk_by_same_decennial_population_v1"
    )
    positive["method_version"] = "1.0.0"
    positive["weighting_universe"] = (
        f"{product_year} decennial complete-count block total population"
    )
    positive["assignment_status"] = "assigned"
    diagnostics = {
        "source_block_groups_with_positive_support": int(
            positive["source_geography_id"].nunique()
        ),
        "source_block_groups_without_positive_support": int(
            grouped.loc[totals.eq(0), "source_geography_id"].nunique()
        ),
        "maximum_weight_sum_delta": float(
            positive.groupby("source_geography_id")["weight"].sum().sub(1).abs().max()
        ),
        "source_crosswalk": path.relative_to(root).as_posix(),
        "source_crosswalk_sha256": sha256(path),
        "support_universe": f"{product_year} decennial block total population",
        "target_chamber": chamber,
    }
    fields = [
        "source_dataset_id",
        "source_reference_vintage",
        "source_geography_id",
        "target_chamber",
        "target_plan_id",
        "target_plan_reference_vintage",
        "target_district_id",
        "weight",
        "weighting_universe",
        "method_id",
        "method_version",
        "assignment_status",
    ]
    return positive[fields], diagnostics


def _load_block_population(root: Path, year: int) -> pd.DataFrame:
    if year == 1990:
        return _load_1990_block_population_with_groups(
            root / SOURCES_1990["census_population"]["relative_path"]
        )
    if year == 2000:
        frame = load_2000_pl94_block_population(
            root / SOURCES_2000["census_population_geography"]["relative_path"],
            root / SOURCES_2000["census_population_file01"]["relative_path"],
        )
        frame = frame.rename(columns={"source_block_geoid": "source_geography_id"})
        frame["source_block_group_id"] = frame["source_geography_id"].str.slice(0, 12)
        return frame[["source_geography_id", "source_block_group_id", "P0010001"]]
    raise ValueError(f"unsupported decennial year: {year}")


def _load_1990_block_population_with_groups(archive_path: Path) -> pd.DataFrame:
    """Read 1990 block population and the explicit header block-group field."""
    rows = []
    with ZipFile(archive_path) as archive:
        member = archive.namelist()[0]
        with archive.open(member) as source:
            for raw_line in source:
                line = raw_line.decode("latin-1").rstrip("\r\n")
                if line[10:13] != "100" or line[132:134] != "42":
                    continue
                county = line[71:74]
                tract = line[51:57].strip().ljust(6, "0")
                block = line[46:50].strip().zfill(4)
                block_group = line[50:51]
                rows.append(
                    {
                        "source_geography_id": f"42{county}{tract}{block}",
                        "source_block_group_id": f"42{county}{tract}{block_group}",
                        "P0010001": int(line[290:299]),
                    }
                )
    return pd.DataFrame(rows)


def allocate_to_plan(
    source: pd.DataFrame,
    crosswalk: pd.DataFrame,
    product_id: str,
    chamber: str,
    plan_id: str,
    reference_vintage: str,
) -> pd.DataFrame:
    """Allocate additive block-group estimates and derive district shares."""
    assigned = source.merge(
        crosswalk, on="source_geography_id", how="inner", validate="many_to_many"
    )
    assigned["allocated_estimate"] = assigned["estimate"] * assigned["weight"]
    result = assigned.groupby(
        ["metric_family", "category", "target_district_id"], as_index=False
    )["allocated_estimate"].sum()
    result = result.rename(
        columns={"target_district_id": "geography_id", "allocated_estimate": "estimate"}
    )
    parent = result[
        result.apply(
            lambda row: row["category"] == PARENT_CATEGORIES[row["metric_family"]],
            axis="columns",
        )
    ][["metric_family", "geography_id", "estimate"]].rename(
        columns={"estimate": "denominator_estimate"}
    )
    result = result.merge(
        parent, on=["metric_family", "geography_id"], how="left", validate="many_to_one"
    )
    result["share"] = result["estimate"] / result["denominator_estimate"]
    result.loc[
        result.apply(
            lambda row: row["category"] == PARENT_CATEGORIES[row["metric_family"]],
            axis="columns",
        ),
        "share",
    ] = pd.NA
    product = PRODUCTS[product_id]
    result["margin_of_error"] = pd.NA
    result["geography_type"] = chamber
    result["estimate_year"] = product["estimate_year"]
    result["period_start"] = product["period_start"]
    result["period_end"] = product["period_end"]
    result["source_table"] = result["metric_family"].map(SOURCE_TABLES[product_id])
    result["geography_method"] = "modeled_block_group_population_allocation"
    result["uncertainty_note"] = (
        "Decennial long-form sample estimate; cell-level MOEs were not published. "
        "Allocation adds geographic-model uncertainty that is not quantified."
    )
    result["population_product_id"] = product_id
    result["source_grain"] = product["source_grain"]
    result["support_regime"] = f"dec_{product['estimate_year']}_block_population"
    result["target_plan_id"] = plan_id
    result["target_plan_reference_vintage"] = reference_vintage
    result["release_date"] = product["release_date"]
    result["aggregation_note"] = (
        "Exact additive bridge from published mutually exclusive decennial cells; "
        "district estimates use same-decennial block-population support."
    )
    result["socioeconomic_moe_status"] = (
        "not_published_decennial_long_form_sample_estimate"
    )
    return result


def source_checks(source: pd.DataFrame, product_id: str) -> list[dict[str, object]]:
    checks = []
    for family, parent_category in PARENT_CATEGORIES.items():
        selected = source[source["metric_family"].eq(family)]
        pivot = selected.pivot(
            index="source_geography_id", columns="category", values="estimate"
        )
        children = [column for column in pivot if column != parent_category]
        delta = pivot[children].sum(axis="columns").sub(pivot[parent_category]).abs()
        checks.append(
            _check(
                f"{product_id}:{family}:source_categories_conserve",
                bool(delta.le(1e-9).all()),
                float(delta.max()),
            )
        )
    return checks


def _raw_manifest(root: Path) -> list[dict[str, object]]:
    paths = [
        *(root / RAW_1990).glob("CD90_3A_*/stf*.dbf"),
        *(root / RAW_2000).glob("*.zip"),
    ]
    records = []
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        details = _raw_source_details(path)
        records.append(
            {
                "path": relative,
                "sha256": sha256(path),
                "producer": "U.S. Census Bureau",
                "license_access": "Public federal data; cite U.S. Census Bureau",
                "crs": None,
                **details,
            }
        )
    return records


def _raw_source_details(path: Path) -> dict[str, object]:
    if "census_1990_pa_stf3" in path.as_posix():
        disc = path.parent.name
        return {
            "product": f"1990 Census STF3A Pennsylvania {path.name}",
            "source_url": (f"https://www2.census.gov/census_1990/{disc}/{path.name}"),
            "retrieved_at": "2026-09-01T09:55:00-06:00",
            "reference_vintage": "1990-04-01",
            "effective_vintage": "1990 Census sample-data tabulation",
            "schema": (
                "dBASE segment; filter SUMLEV 150 and join by state, county, "
                "tract/BNA, and block group"
            ),
            "geographic_universe": (
                "Pennsylvania 1990 Census geography records; block-group rows used"
            ),
        }
    return {
        "product": f"Census 2000 SF3 Pennsylvania {path.name}",
        "source_url": (
            "https://www2.census.gov/census_2000/datasets/Summary_File_3/"
            f"Pennsylvania/{path.name}"
        ),
        "retrieved_at": "2026-09-01T09:56:00-06:00",
        "reference_vintage": "2000-04-01",
        "effective_vintage": "Census 2000 sample-data tabulation",
        "schema": (
            "fixed-width geography header or comma-delimited SF3 data segment; "
            "join by LOGRECNO and filter SUMLEV 150"
        ),
        "geographic_universe": (
            "Pennsylvania Census 2000 geography records; block-group rows used"
        ),
    }


def run(root: Path) -> dict[str, object]:
    """Build and validate both decennial socioeconomic anchors."""
    root = root.resolve()
    sources = {
        "dec_socio_1990_stf3": load_1990_block_groups(root),
        "dec_socio_2000_sf3": load_2000_block_groups(root),
    }
    records = []
    support_diagnostics = []
    for product_id, source in sources.items():
        year = PRODUCTS[product_id]["estimate_year"]
        plan_vintage = "1991" if year == 1990 else "2001"
        for chamber in ("house", "senate"):
            plan_id = f"pa_{chamber}_{plan_vintage}_final"
            crosswalk, diagnostics = block_group_crosswalk(root, year, chamber, plan_id)
            derived_crosswalk_path = (
                root
                / "data/processed/direct_legislative/poc039_support/crosswalks"
                / f"{product_id}__{plan_id}__v2.parquet"
            )
            diagnostics["derived_crosswalk_write"] = write_immutable_parquet(
                crosswalk,
                derived_crosswalk_path,
                ["source_geography_id", "target_district_id"],
            )
            diagnostics["derived_crosswalk"] = derived_crosswalk_path.relative_to(
                root
            ).as_posix()
            diagnostics["derived_crosswalk_sha256"] = sha256(derived_crosswalk_path)
            source_ids = set(source["source_geography_id"])
            support_ids = set(crosswalk["source_geography_id"])
            missing = source_ids - support_ids
            nonzero_missing = source[
                source["source_geography_id"].isin(missing) & source["estimate"].ne(0)
            ]
            diagnostics["source_block_groups_missing_support"] = len(missing)
            diagnostics["nonzero_source_cells_missing_support"] = len(nonzero_missing)
            if not nonzero_missing.empty:
                raise ValueError(
                    f"{product_id} has nonzero source cells without {plan_id} support"
                )
            records.append(
                allocate_to_plan(
                    source,
                    crosswalk,
                    product_id,
                    chamber,
                    plan_id,
                    plan_vintage,
                )
            )
            support_diagnostics.append(diagnostics)
    combined = pd.concat(records, ignore_index=True).sort_values(
        [
            "population_product_id",
            "metric_family",
            "target_plan_id",
            "geography_id",
            "category",
        ],
        kind="stable",
    )
    output_path = root / OUTPUT_PATH
    write_status = write_immutable_parquet(
        combined,
        output_path,
        [
            "population_product_id",
            "metric_family",
            "target_plan_id",
            "geography_id",
            "category",
        ],
    )
    checks = [
        *(
            check
            for key, value in sources.items()
            for check in source_checks(value, key)
        ),
        _check(
            "no_nonzero_source_cells_missing_support",
            all(
                item["nonzero_source_cells_missing_support"] == 0
                for item in support_diagnostics
            ),
            support_diagnostics,
        ),
        _check(
            "complete_district_coverage",
            _complete_district_coverage(combined),
            combined.groupby(["population_product_id", "target_plan_id"])[
                "geography_id"
            ]
            .nunique()
            .rename("district_count")
            .reset_index()
            .to_dict("records"),
        ),
        _check(
            "house_senate_statewide_estimates_agree",
            _chamber_totals_agree(combined),
            "maximum absolute delta <= 1e-6",
        ),
    ]
    qa = {
        "task": "POC039",
        "stage": "cutoff_safe_decennial_socioeconomic_anchors_v2",
        "products": PRODUCTS,
        "raw_inputs": _raw_manifest(root),
        "source_urls": {
            "1990": "https://www2.census.gov/census_1990/CD90_3A_48/ (plus volumes 49 and 50)",
            "2000": "https://www2.census.gov/census_2000/datasets/Summary_File_3/Pennsylvania/",
        },
        "crs": None,
        "geographic_universe": "Pennsylvania 1990 or 2000 Census block groups",
        "row_count": len(combined),
        "logical_hash": logical_frame_hash(
            combined,
            [
                "population_product_id",
                "metric_family",
                "target_plan_id",
                "geography_id",
                "category",
            ],
        ),
        "output_path": OUTPUT_PATH,
        "output_write": write_status,
        "output_sha256": sha256(output_path),
        "support_diagnostics": support_diagnostics,
        "checks": checks,
        "passed": all_pass(checks),
    }
    write_json(root / QA_PATH, qa)
    if not qa["passed"]:
        raise RuntimeError(f"decennial socioeconomic checks failed; inspect {QA_PATH}")
    return qa


def _complete_district_coverage(frame: pd.DataFrame) -> bool:
    coverage = frame.groupby(["population_product_id", "target_plan_id"])[
        "geography_id"
    ].nunique()
    return bool(
        all(
            count == (203 if "_house_" in plan_id else 50)
            for (_, plan_id), count in coverage.items()
        )
    )


def _chamber_totals_agree(frame: pd.DataFrame) -> bool:
    totals = (
        frame.groupby(
            ["population_product_id", "metric_family", "category", "geography_type"]
        )["estimate"]
        .sum()
        .unstack("geography_type")
    )
    return bool(totals["house"].sub(totals["senate"]).abs().le(1e-6).all())


def _check(check_id: str, passed: bool, observed: object) -> dict[str, object]:
    return {"check_id": check_id, "passed": bool(passed), "observed": observed}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    qa = run(args.root)
    print(f"Decennial socioeconomic anchors passed: {qa['row_count']} rows")


if __name__ == "__main__":
    main()
