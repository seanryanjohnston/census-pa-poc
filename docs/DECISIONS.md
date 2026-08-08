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
| `PD007` | 2026-08-07 | Use the precinct snapshot in force for the November 3, 2026 general election as the current target. | Primary-election geography is not the 2026 target; the final source/as-of cutoff still must be recorded. |
| `PD008` | 2026-08-07 | Inventory whatever mid-decade products are actually available and process them in a separate task. | Do not manufacture a symmetric midpoint series or mix block-group ACS logic into the decennial path. |
| `PD009` | 2026-08-07 | Build data products, not the prediction model, while preserving product release dates. | Downstream training can select information available by each election cutoff without the POC deciding model features. |
| `PD010` | 2026-08-07 | Create a target precinct snapshot for every even-year general election from 1990 through 2026. | Population must be allocated to each election's contemporaneous precinct geography, not only to 2026 precincts. |
| `PD011` | 2026-08-07 | Treat precinct geography as common to offices and record House/Senate assignments and contest eligibility separately. | Gather all precincts every cycle; only the applicable staggered Senate class has a regular Senate contest. Historical split exceptions remain explicit QA findings. |
| `PD012` | 2026-08-07 | Use Philadelphia as the complex-county pilot after the Cumberland mechanics proof. | Acquire an authoritative Philadelphia boundary candidate and document dense-boundary, multipart, split-block, and post-2021 change cases before comparing allocation methods. |
| `PD013` | 2026-08-07 | Use the published LRC corrected-fragment allocation as the 2020-to-2021 LRC baseline; retain representative points and equal-area overlay as comparison/diagnostic methods. | In Philadelphia, 13 corrected split blocks cover 931 people. The published route exactly reproduces all LRC precinct totals; representative points and area weights do not. Targets without published split populations still require a separately validated population-informed method. |

## Decisions needed from the owner

No owner decision currently blocks `POC008`, `POC014`, or `POC018`. The City
of Philadelphia layer qualified under `POC006` is a current candidate without
an election-effective date, so it cannot be silently promoted to the November
3, 2026 target.

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

## Deferred until evidence exists

- Whether DuckDB materially helps the POC; GeoPandas/Pyogrio/Shapely are enough
  to begin.
- Whether PostGIS is needed for statewide performance.
- The final split-aware weighting method.
- A release/publication format beyond local Parquet, CSV, JSON, and Markdown.
