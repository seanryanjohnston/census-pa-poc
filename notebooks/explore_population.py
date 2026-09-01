"""Compact current-plan reconciliation and split-block explorer."""

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="medium")


@app.cell
def _():
    from pathlib import Path

    import altair as alt
    import marimo as mo

    from census_pa_poc.data_explorer import (
        current_district_results,
        current_metric_options,
        current_reconciliation,
        impacted_district_geometries,
        load_current_plan_tables,
        load_split_fragment_geometry,
        split_allocation_view,
        split_block_options,
        split_block_summary,
    )

    return (
        Path,
        alt,
        current_district_results,
        current_metric_options,
        current_reconciliation,
        impacted_district_geometries,
        load_current_plan_tables,
        load_split_fragment_geometry,
        mo,
        split_allocation_view,
        split_block_options,
        split_block_summary,
    )


@app.cell
def _(mo):
    mo.md(r"""
    # Pennsylvania 2026 legislative-plan population check

    This compact explorer answers two questions using the accepted direct
    Census-to-legislative products:

    1. Do the 203 House districts and 50 Senate districts each sum to the
       independently read Pennsylvania Census total?
    2. Which 2020 Census blocks cross district boundaries, and how were their
       values allocated?

    The plans are the 2021 Final House and Senate plans used for the 2022,
    2024, and 2026 elections. No precinct data are loaded or used.
    """)
    return


@app.cell
def _(Path, load_current_plan_tables):
    explorer_root = Path(__file__).resolve().parents[1]
    current_tables = load_current_plan_tables(explorer_root)
    return current_tables, explorer_root


@app.cell
def _(current_metric_options, current_tables, mo):
    metric_control = mo.ui.dropdown(
        options=current_metric_options(current_tables),
        value="Total population",
        label="Census metric",
        full_width=True,
    )
    mo.vstack(
        [
            metric_control,
            mo.md(
                "The source benchmark is read directly from the official "
                "Pennsylvania 2020 PL 94-171 block file, separately from both "
                "sets of district results."
            ),
        ],
        gap=0.5,
    )
    return (metric_control,)


@app.cell
def _(
    current_district_results,
    current_reconciliation,
    current_tables,
    metric_control,
    split_block_summary,
):
    reconciliation = current_reconciliation(current_tables, metric_control.value)
    district_results = current_district_results(current_tables, metric_control.value)
    split_summary = split_block_summary(current_tables, metric_control.value)
    selected_metric_label = current_tables.results.loc[
        current_tables.results["metric_id"].eq(metric_control.value), "metric_label"
    ].iloc[0]
    return district_results, reconciliation, selected_metric_label, split_summary


@app.cell
def _(mo, reconciliation, selected_metric_label):
    reconciliation_display = reconciliation.rename(
        columns={
            "geography": "Geography",
            "district_count": "Districts",
            "population": "Population",
            "difference_from_source": "Difference",
            "status": "Status",
        }
    )
    reconciliation_table = mo.ui.table(
        reconciliation_display,
        selection=None,
        format_mapping={
            "Population": "{0:,.0f}",
            "Difference": "{0:,.0f}",
        },
    )
    mo.vstack(
        [
            mo.md(f"## State reconciliation — {selected_metric_label}"),
            reconciliation_table,
            mo.callout(
                "Both chamber totals match the independent Pennsylvania source "
                "exactly when both district rows show **Pass**.",
                kind="success",
            ),
        ],
        gap=0.5,
    )
    return


@app.cell
def _(alt, district_results, selected_metric_label):
    district_distribution = (
        alt.Chart(district_results)
        .mark_boxplot(size=34, extent="min-max")
        .encode(
            x=alt.X(
                "estimate:Q",
                title=selected_metric_label,
                axis=alt.Axis(format=","),
            ),
            y=alt.Y("chamber:N", title=None),
            color=alt.Color("chamber:N", legend=None),
            tooltip=[
                alt.Tooltip("chamber:N", title="Chamber"),
                alt.Tooltip("estimate:Q", title=selected_metric_label, format=",.0f"),
            ],
        )
        .properties(width=500, height=110)
    )
    return (district_distribution,)


@app.cell
def _(district_distribution, mo):
    mo.vstack(
        [
            mo.md("## District distribution"),
            mo.md(
                "The compact box plots show the range and middle half of district "
                "values without drawing hundreds of overlapping bars."
            ),
            district_distribution,
        ],
        gap=0.5,
    )
    return


@app.cell
def _(district_results, mo):
    district_table = mo.ui.table(
        district_results,
        pagination=True,
        page_size=15,
        show_search=True,
        show_download=True,
        selection=None,
        format_mapping={"estimate": "{0:,.0f}"},
    )
    mo.accordion({"District-level values": district_table})
    return


@app.cell
def _(mo, split_summary):
    split_summary_display = split_summary.rename(
        columns={
            "chamber": "Chamber",
            "split_source_blocks": "Split blocks",
        }
    )
    split_summary_table = mo.ui.table(split_summary_display, selection=None)
    mo.vstack(
        [
            mo.md("## Split 2020 Census blocks"),
            split_summary_table,
            mo.md(
                "A split block is one Census parent block whose corrected LRC "
                "fragments are assigned to more than one district in a chamber."
            ),
        ],
        gap=0.5,
    )
    return


@app.cell
def _(current_tables, metric_control, mo, split_block_options):
    split_choices = split_block_options(current_tables, metric_control.value)
    first_split_label = next(iter(split_choices))
    split_block_control = mo.ui.dropdown(
        options=split_choices,
        value=first_split_label,
        label="Split block detail",
        searchable=True,
        full_width=True,
    )
    mo.vstack([split_block_control])
    return (split_block_control,)


@app.cell
def _(
    current_tables,
    explorer_root,
    load_split_fragment_geometry,
    metric_control,
    impacted_district_geometries,
    split_allocation_view,
    split_block_control,
):
    split_allocations = split_allocation_view(
        current_tables,
        metric_control.value,
        split_block_control.value,
    )
    split_fragments = load_split_fragment_geometry(
        explorer_root,
        current_tables,
        metric_control.value,
        split_block_control.value,
    ).to_crs("EPSG:4326")
    impact_districts = impacted_district_geometries(
        current_tables,
        metric_control.value,
        split_block_control.value,
    )
    _district_label_points = (
        impact_districts.to_crs("EPSG:5070")
        .representative_point()
        .to_crs("EPSG:4326")
    )
    impact_districts = impact_districts.to_crs("EPSG:4326")
    impact_districts["label_longitude"] = _district_label_points.x
    impact_districts["label_latitude"] = _district_label_points.y
    _split_center = split_fragments.geometry.union_all().representative_point()
    split_marker = split_fragments.iloc[[0]].drop(columns="geometry").copy()
    split_marker["source_block"] = split_block_control.value
    split_marker["longitude"] = _split_center.x
    split_marker["latitude"] = _split_center.y
    return impact_districts, split_allocations, split_fragments, split_marker


@app.cell
def _(alt, split_allocations):
    allocation_chart = (
        alt.Chart(split_allocations)
        .mark_bar(size=30)
        .encode(
            x=alt.X(
                "allocation_percent:Q",
                title="Share of the source-block value (%)",
                scale=alt.Scale(domain=[0, 100]),
            ),
            y=alt.Y("chamber:N", title=None),
            color=alt.Color(
                "target_district_id:N",
                title="District",
                legend=alt.Legend(orient="bottom", columns=2),
            ),
            tooltip=[
                alt.Tooltip("target_district_id:N", title="District"),
                alt.Tooltip("allocated_value:Q", title="Allocated value", format=",.0f"),
                alt.Tooltip("allocation_percent:Q", title="Share", format=".2f"),
                alt.Tooltip("weight_method:N", title="Method"),
            ],
        )
        .properties(width=500, height=70)
    )
    return (allocation_chart,)


@app.cell
def _(alt, impact_districts, split_marker):
    impact_maps = []
    for _index, _focus_id in enumerate(
        impact_districts["target_district_id"].astype(str).tolist()
    ):
        _map_data = impact_districts.copy()
        _map_data["map_role"] = "Other district sharing block"
        _map_data.loc[
            _map_data["target_district_id"].astype(str).eq(_focus_id),
            "map_role",
        ] = "Focus district"
        _district_layer = (
            alt.Chart(_map_data)
            .mark_geoshape(stroke="#ffffff", strokeWidth=1.5)
            .encode(
                color=alt.Color(
                    "map_role:N",
                    title="District role",
                    scale=alt.Scale(
                        domain=[
                            "Focus district",
                            "Other district sharing block",
                        ],
                        range=["#2563eb", "#cbd5e1"],
                    ),
                    legend=(
                        alt.Legend(orient="bottom", columns=1)
                        if _index == 0
                        else None
                    ),
                ),
                tooltip=[
                    alt.Tooltip("district_label:N", title="District"),
                    alt.Tooltip("map_role:N", title="Role"),
                ],
            )
        )
        _district_outlines = (
            alt.Chart(_map_data)
            .mark_geoshape(fillOpacity=0, stroke="#334155", strokeWidth=0.8)
        )
        _district_labels = (
            alt.Chart(_map_data)
            .mark_text(color="#0f172a", fontSize=13, fontWeight="bold")
            .encode(
                longitude=alt.Longitude("label_longitude:Q"),
                latitude=alt.Latitude("label_latitude:Q"),
                text=alt.Text("target_district_id:N"),
            )
        )
        _block_marker = (
            alt.Chart(split_marker)
            .mark_point(
                color="#dc2626",
                filled=True,
                shape="diamond",
                size=180,
                stroke="#ffffff",
                strokeWidth=1,
            )
            .encode(
                longitude=alt.Longitude("longitude:Q"),
                latitude=alt.Latitude("latitude:Q"),
                tooltip=[
                    alt.Tooltip("source_block:N", title="Split block"),
                ],
            )
        )
        _focus_label = _map_data.loc[
            _map_data["target_district_id"].astype(str).eq(_focus_id),
            "district_label",
        ].iloc[0]
        impact_maps.append(
            (
                _district_layer
                + _district_outlines
                + _district_labels
                + _block_marker
            )
            .project(type="mercator")
            .properties(
                width=240,
                height=240,
                title=f"Impact view: {_focus_label}",
            )
        )
    return (impact_maps,)


@app.cell
def _(impact_maps, mo):
    mo.vstack(
        [
            mo.md("### Impacted districts"),
            mo.hstack(impact_maps, widths="equal", gap=1),
            mo.md(
                "Each map includes every district sharing the selected split "
                "block. Blue is the map's focus district, gray is the other "
                "impacted district, and the red diamond marks the split block."
            ),
        ],
        gap=0.5,
    )
    return


@app.cell
def _(alt, split_fragments):
    split_map = (
        alt.Chart(split_fragments)
        .mark_geoshape(stroke="#ffffff", strokeWidth=2)
        .encode(
            color=alt.Color(
                "district_label:N",
                title="Fragment assignment",
                legend=alt.Legend(orient="bottom", columns=2),
            ),
            tooltip=[
                alt.Tooltip("source_fragment_geoid:N", title="Corrected fragment"),
                alt.Tooltip("district_label:N", title="Assignment"),
                alt.Tooltip("fragment_value:Q", title="Fragment value", format=",.0f"),
                alt.Tooltip("fragment_percent:Q", title="Value share (%)", format=".2f"),
            ],
        )
        .project(type="mercator")
        .properties(width=500, height=280)
    )
    return (split_map,)


@app.cell
def _(allocation_chart, mo, split_allocations, split_map):
    allocation_display = split_allocations[
        [
            "target_district_id",
            "source_value",
            "allocated_value",
            "allocation_percent",
        ]
    ].rename(
        columns={
            "target_district_id": "District",
            "source_value": "Block value",
            "allocated_value": "Allocated value",
            "allocation_percent": "Share",
        }
    )
    allocation_method = split_allocations["weight_method"].iloc[0]
    allocation_table = mo.ui.table(
        allocation_display,
        selection=None,
        format_mapping={
            "Block value": "{0:,.0f}",
            "Allocated value": "{0:,.0f}",
            "Share": "{0:.2f}%",
        },
    )
    mo.vstack(
        [
            mo.md("### Accepted allocation"),
            allocation_chart,
            allocation_table,
            mo.md(f"Allocation method: `{allocation_method}`."),
            mo.md("### Corrected block fragments"),
            split_map,
            mo.md(
                "The map is intentionally zoomed to one source block. Polygon "
                "color shows the district assignment; the allocation bar and table "
                "show how much of the selected metric each district receives."
            ),
        ],
        gap=0.5,
    )
    return


if __name__ == "__main__":
    app.run()
