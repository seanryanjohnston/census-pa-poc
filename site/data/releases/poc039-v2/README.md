# Pennsylvania legislative model features v2

This directory is the corrected `POC039` model handoff. Version 2 supersedes
v1 because v1 used post-election ACS socioeconomic data for 1992–2010.

This public copy is the immutable, checksum-verified POC release for the
Pennsylvania Legislative District Explorer. See `release.json` for its public
scope, sources, sensitivity review, exclusions, and reuse notice. In particular,
the release contains no legislative-plan or source-geography files while the
Pennsylvania LRC geometry redistribution terms remain unstated.

- `pa_house_district_election_features_v2.csv`: 3,654 rows (203 districts ×
  18 general-election years).
- `pa_senate_district_election_features_v2.csv`: 900 rows (50 districts ×
  18 general-election years).
- `source_selection_v2.csv`: selected population and socioeconomic sources.
- `data_dictionary_v2.csv`: definitions for all 95 columns.
- `METRIC_CALCULATIONS.md`: plain-language formulas and Census count construction.

The unique key is `chamber`, `election_year`, and `district_id`. Every source
period ends on or before its election date, and every source product was also
released by that date. The 1992–2000 socioeconomic rows use 1990 STF3A; the
2002–2010 rows use Census 2000 SF3; later rows use the latest cutoff-safe ACS
five-year product.

## Joining external data

`district_id` is the official numeric district number read from the applicable
Pennsylvania Legislative Reapportionment Commission plan. Source labels such
as `001` are normalized to integer `1`; districts are not renumbered.

Join election-year data using `chamber`, `election_year`, and `district_id`.
For plan-specific data, use `chamber`, `target_plan_id`, and `district_id`.
Never join on `district_id` alone: House and Senate reuse the same numbers, and
a district number can represent different geography after redistricting.

The decennial socioeconomic tables are published sample estimates, not
complete counts. Their cell-level margins of error were not published, so the
corresponding `*_moe` fields are blank and
`socioeconomic_moe_status` records that limitation. ACS rows retain 90% MOEs.
Decennial total population is a complete count, so its MOE is also blank and
typed as not applicable rather than represented by a zero placeholder.

Education, employment, and poverty categories are exact additive bridges of
mutually exclusive published cells. District estimates are modeled by
allocating source block groups with same-decennial block-population support or
the accepted ACS support. Rates and shares are derived only after allocation.

`district_total_area_sq_km` is computed directly from the applicable
legislative-plan polygon in EPSG:5070 and includes water. It is therefore total
polygon area, not Census land area. The three `district_area_*` columns make
that source and treatment explicit.
