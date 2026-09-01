"""Read-only preparation helpers for the direct legislative explorer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd

from census_pa_poc.direct_legislative import CENSUS_SOURCE, LRC_SOURCE
from census_pa_poc.sources import (
    load_pl94_block_population_statewide,
    load_pl94_block_vap_statewide,
    vsi_zip_member,
)

DECENNIAL_RESULTS_PATH = (
    "data/processed/direct_legislative/poc029/"
    "decennial_legislative_results_v1.parquet"
)
ACS_RESULTS_PATH = (
    "data/processed/direct_legislative/poc029/acs_legislative_results_v1.parquet"
)
VAP_RESULTS_PATH = (
    "data/processed/direct_legislative/"
    "census_2020_p003_vap_legislative_results_v1.parquet"
)
PLAN_GEOMETRY_PATH = (
    "data/processed/direct_legislative/legislative_plans_1991_2021_v2.parquet"
)
PARTITION_MAPPING_PATH = "mappings/legislative_population_partitions_v1.csv"
EXPECTED_TOTAL_POPULATION_PARTITIONS = 78
EXPECTED_VAP_PARTITIONS = 2
CURRENT_P001_RESULTS_PATH = (
    "data/processed/direct_legislative/"
    "census_2020_p001_legislative_results_v1.parquet"
)
CURRENT_P003_RESULTS_PATH = VAP_RESULTS_PATH
CURRENT_P001_CROSSWALK_PATH = (
    "data/processed/direct_legislative/"
    "census_2020_p001_to_2021_legislative_plan_v1.parquet"
)
CURRENT_P003_CROSSWALK_PATH = (
    "data/processed/direct_legislative/"
    "census_2020_p003_vap_to_2021_legislative_plan_v1.parquet"
)
CURRENT_PLAN_IDS = {
    "house": "pa_house_2021_final",
    "senate": "pa_senate_2021_final",
}
CURRENT_METRICS = {
    "total_population": {
        "label": "Total population",
        "source_metric_id": "P0010001",
        "crosswalk_path": CURRENT_P001_CROSSWALK_PATH,
        "district_support_column": "district_support_value",
        "parent_support_column": "parent_support_value",
    },
    "voting_age_population": {
        "label": "Voting-age population (18+)",
        "source_metric_id": "P0030001",
        "crosswalk_path": CURRENT_P003_CROSSWALK_PATH,
        "district_support_column": "district_vap_support",
        "parent_support_column": "parent_vap_support",
    },
}


@dataclass(frozen=True)
class ExplorerTables:
    """Accepted direct result, plan, and applicability tables."""

    results: pd.DataFrame
    plans: gpd.GeoDataFrame
    partitions: pd.DataFrame


@dataclass(frozen=True)
class CurrentPlanTables:
    """Small current-plan dataset used by the simplified POC034 notebook."""

    results: pd.DataFrame
    plans: gpd.GeoDataFrame
    source_totals: pd.DataFrame
    split_allocations: pd.DataFrame


def load_current_plan_tables(root: Path) -> CurrentPlanTables:
    """Load only accepted 2020 metrics and the plans in effect for 2026."""
    root = root.resolve()
    p001 = normalize_current_p001(pd.read_parquet(root / CURRENT_P001_RESULTS_PATH))
    p003 = normalize_vap(pd.read_parquet(root / CURRENT_P003_RESULTS_PATH))
    results = pd.concat([p001, p003], ignore_index=True).sort_values(
        ["metric_id", "target_chamber", "target_district_id"]
    )
    plans = gpd.read_parquet(root / PLAN_GEOMETRY_PATH)
    plans = plans[
        plans.apply(
            lambda row: CURRENT_PLAN_IDS.get(row["target_chamber"])
            == row["target_plan_id"],
            axis=1,
        )
    ].copy()
    source_totals = load_current_source_totals(root)
    split_allocations = load_current_split_allocations(root)
    tables = CurrentPlanTables(
        results=results,
        plans=plans,
        source_totals=source_totals,
        split_allocations=split_allocations,
    )
    validate_current_plan_tables(tables)
    return tables


def normalize_current_p001(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize the independently accepted POC028 P1 current-plan result."""
    result = frame.rename(
        columns={
            "population": "estimate",
            "crosswalk_method_id": "method_id",
        }
    ).copy()
    result["target_district_id"] = result["target_district_id"].astype("Int64")
    result["target_plan_reference_vintage"] = "2021"
    return normalize_decennial(result)


def load_current_source_totals(root: Path) -> pd.DataFrame:
    """Read independent Pennsylvania totals from the Census PL block files."""
    archive = root / str(CENSUS_SOURCE["relative_path"])
    total_population = load_pl94_block_population_statewide(archive)["P0010001"].sum()
    voting_age_population = load_pl94_block_vap_statewide(archive)["P0030001"].sum()
    return pd.DataFrame(
        {
            "metric_id": ["total_population", "voting_age_population"],
            "source_metric_id": ["P0010001", "P0030001"],
            "state_source_total": [total_population, voting_age_population],
        }
    ).astype({"state_source_total": "float64"})


def load_current_split_allocations(root: Path) -> pd.DataFrame:
    """Load split parents from each accepted metric-specific crosswalk."""
    frames = []
    for metric_id, config in CURRENT_METRICS.items():
        crosswalk = pd.read_parquet(root / str(config["crosswalk_path"]))
        split = crosswalk[crosswalk["parent_target_count"].gt(1)].copy()
        split["metric_id"] = metric_id
        split["metric_label"] = config["label"]
        split["allocated_value"] = split[str(config["district_support_column"])]
        split["source_value"] = split[str(config["parent_support_column"])]
        frames.append(
            split[
                [
                    "metric_id",
                    "metric_label",
                    "source_metric_id",
                    "target_chamber",
                    "target_plan_id",
                    "source_geography_id",
                    "target_district_id",
                    "source_value",
                    "allocated_value",
                    "weight",
                    "weight_method",
                    "atomic_fragment_count",
                ]
            ]
        )
    return pd.concat(frames, ignore_index=True).sort_values(
        ["metric_id", "target_chamber", "source_geography_id", "target_district_id"]
    )


def validate_current_plan_tables(tables: CurrentPlanTables) -> None:
    """Reject incomplete or nonconserving current-plan notebook inputs."""
    expected_districts = {"house": 203, "senate": 50}
    for metric_id in CURRENT_METRICS:
        metric_results = tables.results[tables.results["metric_id"].eq(metric_id)]
        state_total = float(
            tables.source_totals.loc[
                tables.source_totals["metric_id"].eq(metric_id), "state_source_total"
            ].iloc[0]
        )
        for chamber, district_count in expected_districts.items():
            chamber_results = metric_results[
                metric_results["target_chamber"].eq(chamber)
            ]
            if chamber_results["target_district_id"].nunique() != district_count:
                raise ValueError(
                    f"{metric_id}:{chamber} does not contain {district_count} districts"
                )
            if abs(float(chamber_results["estimate"].sum()) - state_total) > 1e-9:
                raise ValueError(f"{metric_id}:{chamber} does not conserve state total")
    split_weight_sums = tables.split_allocations.groupby(
        ["metric_id", "target_chamber", "source_geography_id"]
    )["weight"].sum()
    if not split_weight_sums.sub(1).abs().le(1e-12).all():
        raise ValueError("split-block allocation weights do not sum to one")


def current_metric_options(tables: CurrentPlanTables) -> dict[str, str]:
    """Return the two independently accepted current-plan metric choices."""
    available = set(tables.results["metric_id"])
    return {
        str(config["label"]): metric_id
        for metric_id, config in CURRENT_METRICS.items()
        if metric_id in available
    }


def current_reconciliation(
    tables: CurrentPlanTables, metric_id: str
) -> pd.DataFrame:
    """Compare each chamber's district sum with the independent state source."""
    validate_current_metric(metric_id)
    metric_results = tables.results[tables.results["metric_id"].eq(metric_id)]
    state_total = float(
        tables.source_totals.loc[
            tables.source_totals["metric_id"].eq(metric_id), "state_source_total"
        ].iloc[0]
    )
    rows = [
        {
            "geography": "Pennsylvania source",
            "district_count": 1,
            "population": state_total,
            "difference_from_source": 0.0,
            "status": "Source benchmark",
        }
    ]
    for chamber, label in (("house", "State House"), ("senate", "State Senate")):
        chamber_results = metric_results[metric_results["target_chamber"].eq(chamber)]
        total = float(chamber_results["estimate"].sum())
        difference = total - state_total
        rows.append(
            {
                "geography": label,
                "district_count": int(chamber_results["target_district_id"].nunique()),
                "population": total,
                "difference_from_source": difference,
                "status": "Pass" if abs(difference) <= 1e-9 else "Fail",
            }
        )
    return pd.DataFrame(rows)


def current_district_results(
    tables: CurrentPlanTables, metric_id: str
) -> pd.DataFrame:
    """Return one compact, downloadable House-and-Senate district table."""
    validate_current_metric(metric_id)
    result = tables.results[tables.results["metric_id"].eq(metric_id)].copy()
    result["chamber"] = result["target_chamber"].map(
        {"house": "State House", "senate": "State Senate"}
    )
    return result[
        [
            "chamber",
            "target_district_id",
            "estimate",
            "source_estimate_metric_id",
            "method_id",
        ]
    ].sort_values(["chamber", "target_district_id"])


def split_block_summary(
    tables: CurrentPlanTables, metric_id: str
) -> pd.DataFrame:
    """Count source blocks assigned to more than one district in each chamber."""
    validate_current_metric(metric_id)
    selected = tables.split_allocations[
        tables.split_allocations["metric_id"].eq(metric_id)
    ]
    counts = selected.groupby("target_chamber")["source_geography_id"].nunique()
    return pd.DataFrame(
        {
            "chamber": ["State House", "State Senate"],
            "split_source_blocks": [int(counts.get("house", 0)), int(counts.get("senate", 0))],
        }
    )


def split_block_options(
    tables: CurrentPlanTables, metric_id: str
) -> dict[str, str]:
    """Return readable choices for the split source blocks of one metric."""
    validate_current_metric(metric_id)
    selected = tables.split_allocations[
        tables.split_allocations["metric_id"].eq(metric_id)
    ]
    blocks = selected["source_geography_id"].drop_duplicates().sort_values()
    return {f"2020 Census block {block}": str(block) for block in blocks}


def split_allocation_view(
    tables: CurrentPlanTables, metric_id: str, source_geography_id: str
) -> pd.DataFrame:
    """Return compact accepted allocation rows for one split parent block."""
    validate_current_metric(metric_id)
    selected = tables.split_allocations[
        tables.split_allocations["metric_id"].eq(metric_id)
        & tables.split_allocations["source_geography_id"].eq(source_geography_id)
    ].copy()
    if selected.empty:
        raise ValueError(f"{source_geography_id} is not split for {metric_id}")
    selected["chamber"] = selected["target_chamber"].map(
        {"house": "State House", "senate": "State Senate"}
    )
    selected["allocation_percent"] = selected["weight"] * 100
    return selected[
        [
            "chamber",
            "target_district_id",
            "source_value",
            "allocated_value",
            "allocation_percent",
            "atomic_fragment_count",
            "weight_method",
        ]
    ].sort_values(["chamber", "target_district_id"])


def impacted_district_geometries(
    tables: CurrentPlanTables, metric_id: str, source_geography_id: str
) -> gpd.GeoDataFrame:
    """Return every district sharing one accepted split source block."""
    validate_current_metric(metric_id)
    split = tables.split_allocations[
        tables.split_allocations["metric_id"].eq(metric_id)
        & tables.split_allocations["source_geography_id"].eq(source_geography_id)
    ][
        [
            "target_chamber",
            "target_plan_id",
            "target_district_id",
        ]
    ].drop_duplicates()
    if split.empty:
        raise ValueError(f"{source_geography_id} is not split for {metric_id}")

    split = split.assign(
        district_join_id=split["target_district_id"].astype("string")
    )
    plans = tables.plans.assign(
        district_join_id=tables.plans["target_district_id"].astype("string")
    )
    result = split.merge(
        plans[
            [
                "target_chamber",
                "target_plan_id",
                "district_join_id",
                "geometry",
            ]
        ],
        on=["target_chamber", "target_plan_id", "district_join_id"],
        how="left",
        validate="one_to_one",
    )
    if result["geometry"].isna().any():
        missing = result.loc[
            result["geometry"].isna(),
            ["target_chamber", "target_district_id"],
        ].to_dict("records")
        raise ValueError(f"split-block districts are missing geometry: {missing}")
    result["district_label"] = (
        result["target_chamber"].str.title()
        + " district "
        + result["target_district_id"].astype(str)
    )
    return gpd.GeoDataFrame(
        result.drop(columns="district_join_id"),
        geometry="geometry",
        crs=tables.plans.crs,
    ).sort_values(["target_chamber", "target_district_id"])


def load_split_fragment_geometry(
    root: Path,
    tables: CurrentPlanTables,
    metric_id: str,
    source_geography_id: str,
) -> gpd.GeoDataFrame:
    """Load only the corrected fragments needed for one split-block map."""
    validate_current_metric(metric_id)
    split = tables.split_allocations[
        tables.split_allocations["metric_id"].eq(metric_id)
        & tables.split_allocations["source_geography_id"].eq(source_geography_id)
    ]
    if split.empty:
        raise ValueError(f"{source_geography_id} is not split for {metric_id}")
    split_chambers = (
        split.groupby("target_chamber")["target_district_id"]
        .nunique()
        .loc[lambda values: values.gt(1)]
        .index.tolist()
    )
    metric_field = str(CURRENT_METRICS[metric_id]["source_metric_id"])
    fragments = gpd.read_file(
        vsi_zip_member(
            root / str(LRC_SOURCE["relative_path"]), "Geography/WP_Blocks.shp"
        ),
        where=f"GEOID20 LIKE '{source_geography_id}%'",
        columns=["GEOID20", metric_field],
    ).rename(
        columns={
            "GEOID20": "source_fragment_geoid",
            metric_field: "fragment_value",
        }
    )
    assignments = pd.read_parquet(
        root
        / "data/processed/direct_legislative/"
        "lrc_fragment_to_2021_legislative_plan_v1.parquet",
        columns=["source_atomic_geoid", "target_chamber", "target_district_id"],
        filters=[("source_geography_id", "==", source_geography_id)],
    )
    assignments = assignments[assignments["target_chamber"].isin(split_chambers)]
    result = fragments.merge(
        assignments,
        left_on="source_fragment_geoid",
        right_on="source_atomic_geoid",
        how="inner",
        validate="one_to_one",
    )
    result["district_label"] = (
        result["target_chamber"].str.title()
        + " district "
        + result["target_district_id"].astype(str)
    )
    parent_total = float(result["fragment_value"].sum())
    result["fragment_percent"] = (
        result["fragment_value"] / parent_total * 100 if parent_total else 0.0
    )
    return gpd.GeoDataFrame(result, geometry="geometry", crs=fragments.crs)


def validate_current_metric(metric_id: str) -> None:
    if metric_id not in CURRENT_METRICS:
        raise ValueError(f"unsupported current-plan metric: {metric_id}")


def load_explorer_tables(root: Path) -> ExplorerTables:
    """Load and validate the accepted POC029 products without modifying them."""
    root = root.resolve()
    decennial = normalize_decennial(pd.read_parquet(root / DECENNIAL_RESULTS_PATH))
    acs = normalize_acs(pd.read_parquet(root / ACS_RESULTS_PATH))
    vap = normalize_vap(pd.read_parquet(root / VAP_RESULTS_PATH))
    results = pd.concat([decennial, acs, vap], ignore_index=True).sort_values(
        ["metric_id", "population_product_id", "target_plan_id", "target_district_id"]
    )
    plans = gpd.read_parquet(root / PLAN_GEOMETRY_PATH)
    partitions = pd.read_csv(root / PARTITION_MAPPING_PATH, dtype="string")
    validate_tables(results, plans, partitions)
    return ExplorerTables(results=results, plans=plans, partitions=partitions)


def normalize_decennial(frame: pd.DataFrame) -> pd.DataFrame:
    """Put additive decennial results into the explorer's common schema."""
    result = frame.rename(columns={"population": "estimate"}).copy()
    result["margin_of_error"] = pd.Series(pd.NA, index=result.index, dtype="Float64")
    result["result_family"] = "decennial"
    result["metric_id"] = "total_population"
    result["metric_label"] = "Total population"
    result["population_universe"] = "total_population"
    result["moe_treatment"] = "not_applicable_exact_decennial_count"
    result["source_estimate_metric_id"] = result["source_metric_id"]
    result["source_moe_metric_id"] = pd.NA
    result["moe_confidence_level"] = pd.NA
    result["uncertainty"] = (
        "Decennial counts are exact at source geography; split-source allocation "
        "still carries the declared crosswalk-model uncertainty."
    )
    return result[common_columns()]


def normalize_acs(frame: pd.DataFrame) -> pd.DataFrame:
    """Put ACS estimates and MOEs into the explorer's common schema."""
    result = frame.copy()
    result["result_family"] = "acs5"
    result["metric_id"] = "total_population"
    result["metric_label"] = "Total population"
    if "population_universe" not in result:
        result["population_universe"] = "total_population"
    result["moe_treatment"] = "weighted_source_moe_then_rss_v1"
    return result[common_columns()]


def normalize_vap(frame: pd.DataFrame) -> pd.DataFrame:
    """Put the accepted POC031 P3 VAP result into the common schema."""
    result = frame.copy()
    result["target_district_id"] = result["target_district_id"].astype("Int64")
    result["target_plan_reference_vintage"] = "2021"
    result["result_family"] = "decennial"
    result["metric_id"] = "voting_age_population"
    result["source_estimate_metric_id"] = result["source_metric_id"]
    result["source_moe_metric_id"] = pd.NA
    result["moe_confidence_level"] = pd.NA
    result["margin_of_error"] = pd.Series(pd.NA, index=result.index, dtype="Float64")
    result["method_id"] = result["crosswalk_method_id"]
    result["uncertainty"] = (
        "Decennial P3 is an exact source count with no sampling MOE. Published "
        "fragment-level P0030001 support resolves the only split parent; Census "
        "disclosure-avoidance and nonsampling limitations remain."
    )
    return result[common_columns()]


def common_columns() -> list[str]:
    return [
        "population_product_id",
        "result_family",
        "metric_id",
        "metric_label",
        "population_universe",
        "source_estimate_metric_id",
        "source_moe_metric_id",
        "moe_confidence_level",
        "target_chamber",
        "target_plan_id",
        "target_plan_reference_vintage",
        "target_district_id",
        "estimate",
        "margin_of_error",
        "moe_treatment",
        "method_id",
        "uncertainty",
    ]


def validate_tables(
    results: pd.DataFrame,
    plans: gpd.GeoDataFrame,
    partitions: pd.DataFrame,
) -> None:
    """Reject stale precinct-era or incomplete explorer inputs."""
    forbidden = {column for column in results.columns if "precinct" in column.lower()}
    if forbidden:
        raise ValueError(f"direct results contain precinct columns: {sorted(forbidden)}")
    result_keys = results[
        ["metric_id", "population_product_id", "target_chamber", "target_plan_id"]
    ].drop_duplicates()
    total_keys = result_keys[result_keys["metric_id"].eq("total_population")]
    vap_keys = result_keys[result_keys["metric_id"].eq("voting_age_population")]
    if len(total_keys) != EXPECTED_TOTAL_POPULATION_PARTITIONS:
        raise ValueError(
            "expected "
            f"{EXPECTED_TOTAL_POPULATION_PARTITIONS} total-population partitions, "
            f"found {len(total_keys)}"
        )
    if len(vap_keys) != EXPECTED_VAP_PARTITIONS:
        raise ValueError(
            f"expected {EXPECTED_VAP_PARTITIONS} VAP partitions, found {len(vap_keys)}"
        )
    expected_districts = {"house": 203, "senate": 50}
    counts = plans.groupby(["target_chamber", "target_plan_id"])[
        "target_district_id"
    ].nunique()
    invalid = [
        f"{chamber}:{plan_id}:{count}"
        for (chamber, plan_id), count in counts.items()
        if count != expected_districts[chamber]
    ]
    if invalid:
        raise ValueError(f"invalid legislative plan district counts: {invalid}")
    if len(partitions) != EXPECTED_TOTAL_POPULATION_PARTITIONS // 2:
        raise ValueError(
            "direct partition mapping must contain 39 product/plan-vintage rows"
        )


def plan_options(tables: ExplorerTables, chamber: str) -> dict[str, str]:
    """Return display labels mapped to plan IDs for one chamber."""
    validate_chamber(chamber)
    rows = (
        tables.plans[tables.plans["target_chamber"].eq(chamber)][
            [
                "target_plan_id",
                "target_plan_reference_vintage",
                "first_applicable_election",
                "last_applicable_election",
            ]
        ]
        .drop_duplicates()
        .sort_values("target_plan_reference_vintage")
    )
    return {
        (
            f"{row.target_plan_reference_vintage} plan "
            f"({row.first_applicable_election}–{row.last_applicable_election})"
        ): row.target_plan_id
        for row in rows.itertuples(index=False)
    }


def product_options(
    tables: ExplorerTables,
    chamber: str,
    plan_id: str,
    metric_id: str = "total_population",
) -> dict[str, str]:
    """Return the products accepted for a chamber/plan partition."""
    rows = tables.results[
        tables.results["target_chamber"].eq(chamber)
        & tables.results["target_plan_id"].eq(plan_id)
        & tables.results["metric_id"].eq(metric_id)
    ][["population_product_id", "result_family"]].drop_duplicates()
    rows = rows.sort_values("population_product_id")
    return {
        f"{row.population_product_id} ({row.result_family})": row.population_product_id
        for row in rows.itertuples(index=False)
    }


def metric_options(
    tables: ExplorerTables, chamber: str, plan_id: str
) -> dict[str, str]:
    """Return distinct proven metric universes for one chamber and plan."""
    rows = tables.results[
        tables.results["target_chamber"].eq(chamber)
        & tables.results["target_plan_id"].eq(plan_id)
    ][["metric_id", "metric_label"]].drop_duplicates()
    order = {"total_population": 0, "voting_age_population": 1}
    rows = rows.assign(
        display_order=rows["metric_id"].map(order).fillna(len(order))
    ).sort_values(["display_order", "metric_label"])
    return {
        row.metric_label: row.metric_id for row in rows.itertuples(index=False)
    }


def district_view(
    tables: ExplorerTables,
    chamber: str,
    plan_id: str,
    product_id: str,
    district_id: int | None = None,
    metric_id: str = "total_population",
) -> gpd.GeoDataFrame:
    """Join one accepted direct result partition to its official plan geometry."""
    validate_chamber(chamber)
    values = tables.results[
        tables.results["target_chamber"].eq(chamber)
        & tables.results["target_plan_id"].eq(plan_id)
        & tables.results["population_product_id"].eq(product_id)
        & tables.results["metric_id"].eq(metric_id)
    ]
    if values.empty:
        raise ValueError(
            f"unknown direct partition: {metric_id}:{product_id}:{chamber}:{plan_id}"
        )
    geometry = tables.plans[
        tables.plans["target_chamber"].eq(chamber)
        & tables.plans["target_plan_id"].eq(plan_id)
    ][["target_district_id", "geometry"]]
    joined = geometry.merge(values, on="target_district_id", how="left", validate="1:1")
    if joined["estimate"].isna().any():
        missing = joined.loc[joined["estimate"].isna(), "target_district_id"].tolist()
        raise ValueError(f"partition is missing district results: {missing}")
    if district_id is not None:
        joined = joined[joined["target_district_id"].eq(district_id)]
        if joined.empty:
            raise ValueError(f"district {district_id} is not in {plan_id}")
    return gpd.GeoDataFrame(joined, geometry="geometry", crs=tables.plans.crs)


def provenance(view: gpd.GeoDataFrame) -> dict[str, object]:
    """Summarize the identity and limitations of one selected partition."""
    first = view.iloc[0]
    return {
        "population_product_id": first["population_product_id"],
        "result_family": first["result_family"],
        "metric_id": first["metric_id"],
        "metric_label": first["metric_label"],
        "population_universe": first["population_universe"],
        "target_chamber": first["target_chamber"],
        "target_plan_id": first["target_plan_id"],
        "target_plan_reference_vintage": first["target_plan_reference_vintage"],
        "source_estimate_metric_id": first["source_estimate_metric_id"],
        "source_moe_metric_id": first["source_moe_metric_id"],
        "moe_confidence_level": first["moe_confidence_level"],
        "moe_treatment": first["moe_treatment"],
        "method_id": first["method_id"],
        "uncertainty": first["uncertainty"],
    }


def summarize_view(view: gpd.GeoDataFrame) -> dict[str, object]:
    """Return exact visible-scope counts and estimate totals."""
    return {
        "district_count": len(view),
        "estimate_total": float(view["estimate"].sum()),
        "moe_available": bool(view["margin_of_error"].notna().all()),
    }


def table_view(view: gpd.GeoDataFrame) -> pd.DataFrame:
    """Return sortable display columns without geometry bytes."""
    return view[
        [
            "target_district_id",
            "estimate",
            "margin_of_error",
            "metric_label",
            "population_universe",
            "population_product_id",
            "target_chamber",
            "target_plan_id",
            "method_id",
        ]
    ].sort_values("target_district_id")


def validate_chamber(chamber: str) -> None:
    if chamber not in {"house", "senate"}:
        raise ValueError(f"unsupported legislative chamber: {chamber}")
