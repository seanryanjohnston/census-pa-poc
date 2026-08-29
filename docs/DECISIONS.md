# Decision register

## Accepted for the POC

| ID | Date | Decision | Consequence |
|---|---|---|---|
| `PD001` | 2026-08-07 | Isolate the analytical proof in a small Python repository. | The existing Elixir/PostGIS work remains untouched; only proven analytical code is promoted here. |
| `PD002` | 2026-08-07 | Keep standard total population as the sole first metric. | Use 2020 `P0010001`; prisoner-adjusted counts are a separate universe. |
| `PD003` | 2026-08-07 | Prove Cumberland first, then a difficult county, then statewide. | A clean pilot proves mechanics but cannot select the final allocation method by itself. |
| `PD004` | 2026-08-07 | Treat every source-to-target route as an explicit, versioned crosswalk. | Published/direct assignments, spatial assignments, relationship files, and modeled weights remain distinguishable. |
| `PD005` | 2026-08-07 | Keep decennial and ACS transformations as separate method families. | ACS block-group estimates and MOEs are not processed as if they were block counts. |
| `PD006` | 2026-08-07 | Run locally and keep POC inputs and artifacts internal. | Sources with unclear or restrictive redistribution terms can be evaluated locally; publication needs a later terms review. |
| `PD007` | 2026-08-07 | Use the precinct snapshot in force for the November 3, 2026 general election as the current target. | Superseded for the simplified POC by `PD014`; retain the source work as production-fidelity research. |
| `PD008` | 2026-08-07 | Inventory whatever mid-decade products are actually available and process them in a separate task. | Do not manufacture a symmetric midpoint series or mix block-group ACS logic into the decennial path. |
| `PD009` | 2026-08-07 | Build data products, not the prediction model, while preserving product release dates. | Downstream training can select information available by each election cutoff without the POC deciding model features. |
| `PD010` | 2026-08-07 | Create a target precinct snapshot for every even-year general election from 1990 through 2026. | Superseded for the simplified POC by `PD014`; actual historical snapshots remain the later production-fidelity target. |
| `PD011` | 2026-08-07 | Treat precinct geography as common to offices and record House/Senate assignments and contest eligibility separately. | Report every fixed precinct each cycle; only the applicable staggered Senate class has a regular Senate contest. Fixed-precinct crossings of older plans remain explicit allocation rows under `PD015`. |
| `PD012` | 2026-08-07 | Use Philadelphia as the complex-county pilot after the Cumberland mechanics proof. | Acquire an authoritative Philadelphia boundary candidate and document dense-boundary, multipart, split-block, and post-2021 change cases before comparing allocation methods. |
| `PD013` | 2026-08-07 | Use the published LRC corrected-fragment allocation as the 2020-to-2021 LRC baseline; retain representative points and equal-area overlay as comparison/diagnostic methods. | In Philadelphia, 13 corrected split blocks cover 931 people. The published route exactly reproduces all LRC precinct totals; representative points and area weights do not. Targets without published split populations still require a separately validated population-informed method. |
| `PD014` | 2026-08-09 | Use the 2021 LRC Data Set 1 precinct geography as one fixed precinct target for every POC population period and election cycle. | Outputs are constant-geography/counterfactual estimates, not reconstructions of the precincts actually in force in each election. `POC008`, `POC009`, and `POC018` become deferred production-fidelity work rather than blockers. Call the target `2021 LRC precincts`, not `2020 precincts` or `2026 precincts`. |
| `PD015` | 2026-08-09 | Use each election's official LRC State Senate plan polygons directly and intersect them with the fixed precinct target. | Do not derive or dissolve Senate districts from precinct assignments and do not assume a fixed precinct is wholly contained by every historical Senate plan. The atomic geography is population source unit ∩ fixed LRC precinct ∩ applicable Senate district. |
| `PD016` | 2026-08-09 | Do not assign uncovered source polygons to the nearest precinct or Senate district. | Prefer a published direct assignment; otherwise intersect in a suitable common CRS, require per-source weights to sum to one within tolerance, type immaterial water/precision exceptions, and fail material uncovered populated areas. Nearest-boundary results are diagnostics only. |
| `PD017` | 2026-08-09 | Normalize official Senate-plan topology within each fixed precinct using the proven `fixed_precinct_senate_overlay_v3` rules. | Remove ≤1 m² district slivers; remove material duplicated district overlap from the district with less raw area in that precinct; fill a plan/state-line gap only when one material district intersects the precinct; retain multi-district gaps as typed exceptions only when no uncovered LRC fragment representative point or population supports them; normalize weights over covered area. Never use nearest assignment. |
| `PD018` | 2026-08-29 | Use `relationship_atomic_area_2010_v1` as the 2010 POC baseline and retain `direct_atomic_area_2010_v1` as its diagnostic comparison. | The official 2010→2020 topology is composed only with corrected-fragment atomic area; do not use 2020 population as a historical weight. Both outputs remain area estimates, retain their measured deltas, and use typed zero-population exceptions rather than nearest assignment. |

## Decisions needed from the owner

No owner decision currently blocks the fixed-geography POC. The actual 2026
and historical precinct inventories remain useful production-fidelity research,
but `PD014` removes them from the POC's critical path. The City of Philadelphia
layer qualified under `POC006` still cannot be silently promoted to an
election-effective target.

## Pennsylvania election-structure authority

- The Pennsylvania Election Code defines an election district as a district,
  division, or precinct whose electors vote at one polling place. Section 502
  says newly formed election districts must be wholly contained within larger
  districts electing federal, state, county, municipal, or school officers:
  https://www.legis.state.pa.us/WU01/LI/LI/US/HTM/1937/0/0320.005.000..HTM
- Election Code section 601 places the general election biennially on the
  Tuesday after the first Monday of November in each even-numbered year:
  https://www.legis.state.pa.us/WU01/LI/LI/US/HTM/1937/0/0320..HTM
- The Pennsylvania Constitution provides two-year House terms and four-year
  Senate terms, with General Assembly elections every second year:
  https://www.legis.state.pa.us/WU01/LI/LI/CT/HTM/00/00.002..HTM
- Pennsylvania's official 2026 general-election candidate requirements list
  the even-numbered State Senate districts, confirming the 2026 Senate class:
  https://www.pa.gov/content/dam/copapwp-pagov/en/dos/programs/voting-and-elections/running-for-office/2026/nomination-papers-2026/2026%20district%20signature%20requirements%20-%20final%20%282%29.pdf

Section 502's containment rule applies to the election districts actually in
force with their larger districts. It does not imply that the fixed 2021 LRC
precinct polygons are contained by older Senate plans; those crossings are an
expected consequence of the counterfactual fixed-geography design.

## Deferred until evidence exists

- Whether DuckDB materially helps the POC; GeoPandas/Pyogrio/Shapely are enough
  to begin.
- Whether PostGIS is needed for statewide performance.
- The final split-aware weighting method.
- A release/publication format beyond local Parquet, CSV, JSON, and Markdown.
