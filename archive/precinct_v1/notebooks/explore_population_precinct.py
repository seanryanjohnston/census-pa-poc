"""Interactive, read-only explorer for accepted POC024 population products."""

import marimo

__generated_with = "0.24.0"
app = marimo.App(width="full")


@app.cell
def _():
    from pathlib import Path

    import altair as alt
    import marimo as mo

    from census_pa_poc.data_explorer import (
        load_explorer_tables,
        load_fixed_precinct_geometry,
        load_senate_geometry,
        prepare_precinct_view,
        prepare_senate_view,
        provenance_for_year,
        reconciliation_for_year,
        reconciliation_table_view,
        selection_for_year,
        summarize_view,
        table_view,
    )
    from census_pa_poc.precinct_inventory import COUNTIES

    return (
        COUNTIES,
        Path,
        alt,
        load_explorer_tables,
        load_fixed_precinct_geometry,
        load_senate_geometry,
        mo,
        prepare_precinct_view,
        prepare_senate_view,
        provenance_for_year,
        reconciliation_for_year,
        reconciliation_table_view,
        selection_for_year,
        summarize_view,
        table_view,
    )


@app.cell
def _(mo):
    mo.md(r"""
    # Pennsylvania election population explorer

    Inspect the accepted `POC024` election-year population views without
    modifying their Parquet artifacts. Precincts are always the fixed **2021
    LRC Data Set 1 target**; they are not the precinct boundaries historically
    in force. Senate districts use the official plan applicable to the selected
    election. Red/missing rows remain visible by design.
    """)
    return


@app.cell
def _(COUNTIES, Path, load_explorer_tables, load_fixed_precinct_geometry):
    explorer_root = Path(__file__).resolve().parents[1]
    explorer_tables = load_explorer_tables(explorer_root)
    explorer_precinct_geometry = load_fixed_precinct_geometry(explorer_root)
    explorer_years = sorted(
        int(year) for year in explorer_tables.selection["election_year"].unique()
    )
    explorer_county_options = {
        "All counties": "all",
        **{f"{fips} — {name}": fips for fips, name in COUNTIES.items()},
    }
    return (
        explorer_county_options,
        explorer_precinct_geometry,
        explorer_root,
        explorer_tables,
        explorer_years,
    )


@app.cell
def _(explorer_county_options, explorer_years, mo):
    election_control = mo.ui.dropdown(
        options=explorer_years,
        value=2026,
        label="Election year",
        full_width=True,
    )
    geography_control = mo.ui.radio(
        options={"Fixed precincts": "precinct", "State Senate": "senate"},
        value="Fixed precincts",
        inline=True,
        label="Geography",
    )
    county_control = mo.ui.dropdown(
        options=explorer_county_options,
        value="041 — Cumberland",
        searchable=True,
        label="County (precinct and reconciliation)",
        full_width=True,
    )
    district_control = mo.ui.dropdown(
        options={"All districts": "all", **{str(i): i for i in range(1, 51)}},
        value="All districts",
        searchable=True,
        label="District (Senate view)",
        full_width=True,
    )
    status_control = mo.ui.radio(
        options={
            "All rows": "all",
            "Available": "available",
            "Missing": "missing",
        },
        value="All rows",
        inline=True,
        label="Data status",
    )
    return (
        county_control,
        district_control,
        election_control,
        geography_control,
        status_control,
    )


@app.cell
def _(
    county_control,
    district_control,
    election_control,
    geography_control,
    mo,
    status_control,
):
    mo.vstack(
        [
            mo.hstack(
                [election_control, geography_control, status_control],
                widths=[1, 2, 2],
                gap=1.5,
            ),
            mo.hstack([county_control, district_control], widths="equal", gap=1.5),
        ],
        gap=1,
    )
    return


@app.cell
def _(
    county_control,
    explorer_provenance,
    explorer_tables,
    explorer_year,
    mo,
    reconciliation_for_year,
    reconciliation_table_view,
):
    if explorer_provenance["population_product_id"] is None:
        explorer_reconciliation_output = mo.callout(
            "No Census comparison is available because this election has no "
            "cataloged population product available by its cutoff.",
            kind="warn",
        )
    else:
        explorer_reconciliation = reconciliation_for_year(
            explorer_tables,
            explorer_year,
            county_fips=None if county_control.value == "all" else county_control.value,
        )
        explorer_reconciliation_rows = reconciliation_table_view(
            explorer_reconciliation
        )
        explorer_county_differences = explorer_reconciliation_rows[
            explorer_reconciliation_rows["geography_level"].eq("county")
            & explorer_reconciliation_rows["allocation_comparison_status"].eq(
                "outside_tolerance"
            )
        ]
        explorer_state_differences = explorer_reconciliation_rows[
            explorer_reconciliation_rows["geography_level"].eq("state")
            & explorer_reconciliation_rows["allocation_comparison_status"].eq(
                "outside_tolerance"
            )
        ]
        if not explorer_state_differences.empty:
            explorer_reconciliation_note = mo.callout(
                "The allocated Pennsylvania total is outside the accepted "
                "0.001-person conservation tolerance.",
                kind="danger",
            )
        elif not explorer_county_differences.empty:
            explorer_reconciliation_note = mo.callout(
                "Pennsylvania conserves exactly, but one or more county labels "
                "differ after mapping the source geography into the fixed 2021 "
                "precinct target. The signed differences remain visible below.",
                kind="warn",
            )
        else:
            explorer_reconciliation_note = mo.callout(
                "The allocated total matches the trusted Census source-unit sum "
                "within 0.001 person for every displayed geography.",
                kind="success",
            )
        explorer_reconciliation_table = mo.ui.table(
            explorer_reconciliation_rows,
            pagination=True,
            page_size=15,
            show_search=True,
            show_download=True,
            selection=None,
            format_mapping={
                "allocated_estimate": "{0:,.3f}",
                "official_source_unit_sum": "{0:,.3f}",
                "allocated_minus_source_sum": "{0:+,.3f}",
                "published_aggregate": "{0:,.3f}",
                "allocated_minus_published_aggregate": "{0:+,.3f}",
                "source_sum_minus_published_aggregate": "{0:+,.3f}",
            },
        )
        explorer_reconciliation_output = mo.vstack(
            [explorer_reconciliation_note, explorer_reconciliation_table], gap=0.5
        )
    mo.vstack(
        [
            mo.md(
                "## Trusted Census reconciliation\n\n"
                "`official_source_unit_sum` independently sums the exact Census "
                "blocks or block groups used by the crosswalk. "
                "`published_aggregate` is a separate direct ACS B01003 "
                "county/state row when that row exists in the accepted local "
                "Census product; typed statuses explain unavailable cells."
            ),
            explorer_reconciliation_output,
        ],
        gap=0.5,
    )
    return


@app.cell
def _(
    county_control,
    district_control,
    election_control,
    explorer_precinct_geometry,
    explorer_root,
    explorer_tables,
    geography_control,
    load_senate_geometry,
    prepare_precinct_view,
    prepare_senate_view,
    selection_for_year,
    status_control,
):
    explorer_year = int(election_control.value)
    explorer_selection = selection_for_year(explorer_tables, explorer_year)
    if geography_control.value == "precinct":
        explorer_geography_label = "Fixed 2021 LRC precinct"
        explorer_full_view = prepare_precinct_view(
            explorer_tables,
            explorer_precinct_geometry,
            explorer_year,
            county_fips=None if county_control.value == "all" else county_control.value,
        )
        explorer_visible_view = prepare_precinct_view(
            explorer_tables,
            explorer_precinct_geometry,
            explorer_year,
            county_fips=None if county_control.value == "all" else county_control.value,
            data_status=status_control.value,
        )
    else:
        explorer_geography_label = "Applicable State Senate district"
        explorer_senate_geometry = load_senate_geometry(
            explorer_root, str(explorer_selection["senate_plan_id"])
        )
        explorer_full_view = prepare_senate_view(
            explorer_tables, explorer_senate_geometry, explorer_year
        )
        explorer_visible_view = prepare_senate_view(
            explorer_tables,
            explorer_senate_geometry,
            explorer_year,
            senate_district=(
                None if district_control.value == "all" else district_control.value
            ),
            data_status=status_control.value,
        )
    return (
        explorer_full_view,
        explorer_geography_label,
        explorer_visible_view,
        explorer_year,
    )


@app.cell
def _(
    explorer_full_view,
    explorer_geography_label,
    explorer_tables,
    explorer_visible_view,
    explorer_year,
    mo,
    provenance_for_year,
    summarize_view,
):
    explorer_summary = summarize_view(explorer_full_view)
    explorer_provenance = provenance_for_year(explorer_tables, explorer_year)
    explorer_total_label = (
        "Unavailable"
        if explorer_summary["estimate_total"] is None
        else f"{explorer_summary['estimate_total']:,.0f}"
    )
    explorer_stats = mo.hstack(
        [
            mo.stat(
                str(explorer_summary["rows"]),
                label=f"{explorer_geography_label} rows",
                bordered=True,
            ),
            mo.stat(
                str(explorer_summary["available_rows"]),
                label="Available",
                bordered=True,
            ),
            mo.stat(
                str(explorer_summary["missing_rows"]),
                label="Missing",
                bordered=True,
            ),
            mo.stat(
                explorer_total_label, label="Visible-scope population", bordered=True
            ),
        ],
        widths="equal",
        gap=1,
    )
    explorer_provenance_text = mo.md(
        f"""
        **Election:** {explorer_year}  
        **Population product:** `{explorer_provenance["population_product_id"] or "none"}`  
        **Reference period:** {explorer_provenance["reference_start"] or "—"} to {explorer_provenance["reference_end"] or "—"}  
        **Published:** {explorer_provenance["release_date_published"] or "—"}  
        **Senate plan:** `{explorer_provenance["senate_plan_id"]}`  
        **Fixed target:** `{explorer_provenance["precinct_snapshot_id"]}`  
        **Selection rule:** `{explorer_provenance["display_selection_rule"]}`  
        **Missing reason:** `{explorer_provenance["missing_reason"] or "none"}`
        """
    )
    explorer_filter_note = mo.callout(
        f"The controls currently show {len(explorer_visible_view):,} of "
        f"{len(explorer_full_view):,} rows in this scope. Filters change only the "
        "display; they never rewrite an accepted artifact.",
        kind="info",
    )
    mo.vstack(
        [
            explorer_stats,
            mo.accordion(
                {"Product, plan, and cutoff provenance": explorer_provenance_text}
            ),
            explorer_filter_note,
        ],
        gap=1,
    )
    return


@app.cell
def _(explorer_visible_view, mo):
    if explorer_visible_view.empty:
        explorer_map_output = mo.callout(
            "No rows match the current display filters.", kind="warn"
        )
    else:
        explorer_map_frame = explorer_visible_view.to_crs("EPSG:4326").copy()
        explorer_map_frame["geometry"] = explorer_map_frame.geometry.simplify(
            0.00025, preserve_topology=True
        )
        explorer_map_tooltips = [
            column
            for column in (
                "county_name",
                "target_precinct_geoid",
                "precinct_code",
                "senate_district",
                "estimate",
                "margin_of_error",
                "data_status",
                "missing_reason",
                "population_product_id",
            )
            if column in explorer_map_frame.columns
        ]
        if explorer_map_frame["estimate"].notna().any():
            explorer_folium_map = explorer_map_frame.explore(
                column="estimate",
                cmap="YlGnBu",
                tooltip=explorer_map_tooltips,
                tiles="CartoDB positron",
                legend=True,
                missing_kwds={
                    "color": "#d73027",
                    "label": "Missing",
                    "hatch": "xxx",
                },
                style_kwds={
                    "color": "#ffffff",
                    "weight": 0.5,
                    "fillOpacity": 0.82,
                },
            )
        else:
            explorer_folium_map = explorer_map_frame.explore(
                color="#d73027",
                tooltip=explorer_map_tooltips,
                tiles="CartoDB positron",
                style_kwds={
                    "color": "#8f241e",
                    "weight": 0.5,
                    "fillOpacity": 0.72,
                    "fillPattern": "xxx",
                },
            )
        explorer_map_output = mo.as_html(explorer_folium_map)
    mo.vstack([mo.md("## Map"), explorer_map_output], gap=0.5)
    return


@app.cell
def _(alt, explorer_geography_label, explorer_visible_view, mo, table_view):
    explorer_chart_frame = table_view(explorer_visible_view)
    explorer_chart_frame = explorer_chart_frame[
        explorer_chart_frame["estimate"].notna()
    ].copy()
    if explorer_chart_frame.empty:
        explorer_chart_output = mo.callout(
            "No population estimates are available for a chart under these filters.",
            kind="warn",
        )
    else:
        if "target_precinct_geoid" in explorer_chart_frame.columns:
            explorer_chart_frame["geography"] = explorer_chart_frame[
                "target_precinct_geoid"
            ]
            explorer_chart_frame = explorer_chart_frame.nlargest(30, "estimate")
            explorer_chart_title = "Largest 30 visible fixed-precinct estimates"
        else:
            explorer_chart_frame["geography"] = "District " + explorer_chart_frame[
                "senate_district"
            ].astype(str)
            explorer_chart_title = "Visible State Senate district estimates"
        explorer_altair_chart = (
            alt.Chart(explorer_chart_frame)
            .mark_bar(color="#178277")
            .encode(
                x=alt.X("estimate:Q", title="Population estimate"),
                y=alt.Y("geography:N", sort="-x", title=explorer_geography_label),
                tooltip=[
                    alt.Tooltip("geography:N", title="Geography"),
                    alt.Tooltip("estimate:Q", title="Estimate", format=",.1f"),
                    alt.Tooltip("margin_of_error:Q", title="90% MOE", format=",.1f"),
                    alt.Tooltip("data_status:N", title="Status"),
                ],
            )
            .properties(height=max(300, min(800, len(explorer_chart_frame) * 18)))
        )
        explorer_chart_output = mo.ui.altair_chart(
            explorer_altair_chart, chart_selection=False, legend_selection=False
        )
    mo.vstack(
        [
            mo.md(
                f"## {explorer_chart_title if not explorer_chart_frame.empty else 'Chart'}"
            ),
            explorer_chart_output,
        ],
        gap=0.5,
    )
    return


@app.cell
def _(explorer_visible_view, mo, table_view):
    explorer_rows = table_view(explorer_visible_view)
    explorer_table = mo.ui.table(
        explorer_rows,
        pagination=True,
        page_size=25,
        selection="multi",
        show_search=True,
        show_download=True,
        label="Visible accepted rows",
        format_mapping={
            "estimate": "{0:,.1f}",
            "margin_of_error": "{0:,.1f}",
        },
    )
    mo.vstack(
        [
            mo.md(
                "## Rows\nSearch, sort, select, or download only the currently "
                "visible rows. The source Parquet remains unchanged."
            ),
            explorer_table,
        ],
        gap=0.5,
    )
    return


if __name__ == "__main__":
    app.run()
