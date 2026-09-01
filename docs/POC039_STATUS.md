# POC039 model-ready CSV status

Status: **done — corrected cutoff-safe 1992–2026 panels accepted**

`POC039` packages the readily usable direct-legislative work into one wide row
per district and general-election year. Version 2 supersedes version 1 because
the v1 socioeconomic bundle used post-election ACS 2005–2009 values in earlier
cycles.

| File | Rows | Columns | SHA-256 |
|---|---:|---:|---|
| `pa_house_district_election_features_v2.csv` | 3,654 | 95 | `46d7260b42bd52b45c3d271f28ca1d45a0e0b9a99c48d8bf87a3a857a9bc2e55` |
| `pa_senate_district_election_features_v2.csv` | 900 | 95 | `59641c43353ed1a295119428a4b62f75af4269be97e13dfa3a6341aaedbdbe58` |

Both live under `data/exports/model_features/v2/`, with
`source_selection_v2.csv`, `data_dictionary_v2.csv`, and a usage README.
`chamber`, `election_year`, and `district_id` form the unique join key.
`regular_contest` identifies the alternating Senate class while retaining all
50 districts in every election-year panel.

## Source timing and continuity

Every selected source period ends on or before the election date and every
product release also precedes the election. No future backfill remains.

| Elections | Total population | Socioeconomic source |
|---|---|---|
| 1992–2000 | 1990 decennial complete count | 1990 Census STF3A long-form sample estimates |
| 2002–2010 | 2000 decennial complete count | Census 2000 SF3 long-form sample estimates |
| 2012–2026 | Latest cutoff-safe ACS five-year product | Latest cutoff-safe ACS five-year product |

The 1990 bridge uses STF3A P057 education, P070 employment, and P121 poverty.
The 2000 bridge uses SF3 P037, P043, and P088. In both vintages, only mutually
exclusive published cells are summed, and every child category reconciles to
its published parent. The 1990 product was available by August 27, 1992; the
Pennsylvania 2000 SF3 release was September 25, 2002. Raw files and checksums
are recorded in `artifacts/poc039/decennial_socioeconomic_qa_v2.json`.

The decennial long-form tables are sample estimates. Cell-level MOEs were not
published, so their socioeconomic MOE fields are blank and
`socioeconomic_moe_status` says
`not_published_decennial_long_form_sample_estimate`. ACS rows retain their 90%
MOEs. Decennial total-population MOEs are blank and typed as not applicable;
they are no longer represented by zero placeholders.

## Geography and transformations

The source block-group estimates are allocated to the plan used in each
election. The 1990 and 2000 block-group/district weights collapse the already
accepted block crosswalks using total population from the same decennial
census as support. This is a modeled geographic allocation, not observed
person-level placement. All rates and shares are calculated only after the
additive counts reach the district. The four derived block-group crosswalks
are preserved under
`data/processed/direct_legislative/poc039_support/crosswalks/` with source and
target vintages, method version, weighting universe, allocation rows, hashes,
and validation diagnostics.

`district_total_area_sq_km` does not depend on a later Census area product. It
is derived directly from each applicable official legislative-plan polygon in
EPSG:5070 and includes water. `district_area_source_id`, `district_area_crs`,
and `district_area_water_treatment` make this explicit. Density is therefore
total-polygon-area density, not Census land-area density.

## Included features

- Total population, Pennsylvania share, chamber-mean deviation, total polygon
  area, density, and log density.
- Four education-attainment bands for population 25 and older.
- Four employment-status categories for population 16 and older, plus three
  compatible derived labor rates.
- Seven poverty-ratio bands plus below-poverty and below-200% counts and
  shares.

Historical VAP/CVAP, age, race/ethnicity, nativity/citizenship, household
income, tenure, and Census-land-area density remain deferred because their
complete 1992–2026 routes require separate support or concept decisions.

## Acceptance evidence

All gates pass: exact row/district coverage, unique keys, required-value
completeness, positive population and area, House/Senate statewide agreement,
MOE typing, source-period and release cutoffs, plan-vintage timing, explicit
area provenance, stripped text, bounded rates/shares, and conservation of all
three additive category families. The latest observed source period ends 672
days before its election; zero rows violate the source-period or release
cutoff.

The logical panel hash is
`a93d2048d1c5005fb0ba322064acda183a421cd2db9cbd8ba5affcde7f3d5372`.
Machine-readable evidence is in
`artifacts/poc039/model_export_qa_v2.json`; decennial source and allocation
evidence is in `artifacts/poc039/decennial_socioeconomic_qa_v2.json`.
