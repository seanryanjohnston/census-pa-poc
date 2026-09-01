# Experiment backlog

This is the authoritative POC task list. Status values are `ready`, `blocked`,
`in-progress`, `done`, and `deferred`. A task is `done` only with the evidence in
its "Done when" column.

Completed evidence: `POC001`–`POC005` — the saved Python run verifies all three
source hashes, 5,609 exact Cumberland block keys, 119 precincts, EPSG:4269, and
259,469 people. Every LRC block has one published precinct key; both versioned
crosswalks cover every block/target and conserve population. Direct and
representative-point assignments agree on all 5,609 blocks and reproduce all
119 LRC precinct totals exactly. Machine-readable local evidence is under
`artifacts/poc001_poc005/`; accepted evidence is summarized in
`docs/CUMBERLAND_2020_PROOF.md`.

Completed evidence: `POC006`–`POC007` — the saved Philadelphia run qualifies a
checksum-frozen City Political Divisions candidate and proves 13 LRC corrected
split blocks covering 931 people. The published corrected-fragment method
reconciles exactly to all 1,703 precinct totals; representative points change
eight precincts by 162 total absolute persons and equal-area overlay changes 12
precincts by 80.904 total absolute persons. Machine-readable local evidence is
under `artifacts/poc006_poc007/`; accepted evidence is summarized in
`docs/PHILADELPHIA_2020_PROOF.md`.

`POC017` — `mappings/election_cycles.csv` records all 19
even-year general elections from 1990 through 2026. Dates follow Pennsylvania
Election Code section 601; House scope and four-year staggered Senate classes
follow the Pennsylvania Constitution, with the even-numbered 2026 class
independently confirmed by Department of State candidate requirements. Under
`PD014`, every row now targets the fixed 2021 LRC precinct geography; Senate
plan identity remains cycle-specific.

Progress evidence: `POC008` — the 67-county resolution ledger now contains 13
checksum-frozen candidates and 54 unreviewed counties. Eleven exact PASDA
county layers have reproducible source profiles. Delaware's official table and
consolidation evidence deterministically map all 428 named old precincts to 383
active precincts with complete House/Senate assignments and valid candidate
geometry. One material unnamed source polygon and the unmet statewide cutoff
keep that county—and the statewide task—unqualified.

Completed evidence: `POC021` — the saved statewide audit proves complete LRC
baseline coverage for all 336,985 Census parent blocks, 337,039 corrected
fragments, and 9,178 fixed precincts. Fifty-three parent blocks are split. No
assigned representative point falls outside its target and no nearest assignment
is used. The second run reproduced all logical artifact hashes. Accepted
evidence is summarized in `docs/STATEWIDE_FIXED_GEOGRAPHY_PROOF.md`.

Completed evidence: `POC022` — all five official Senate plans are
checksum-frozen and source-profiled. The accepted `v3` overlay covers all 9,178
fixed precincts and all 50 districts per plan, preserves 997–1,126 historical
precinct crossings, types zero-population linework gaps, uses no nearest
assignments, and reproduced five immutable GeoParquet hashes. Accepted evidence
is summarized in `docs/STATE_SENATE_OVERLAY_PROOF.md`.

Completed evidence: `POC010` — the statewide result covers all 336,985 Census
parent blocks, 337,039 corrected fragments, 9,178 fixed precincts, 67 counties,
and 50 current-plan Senate districts. It conserves 13,002,700 people at state
and county levels. The accepted fixed-precinct/Senate route and the independent
official block-equivalency route agree exactly in every district. The second
run reused all five immutable artifacts identically. Accepted evidence is
summarized in `docs/STATEWIDE_2020_RESULT.md`.

Completed evidence: `POC014` — all 16 overlapping ACS five-year products from
2005–2009 through 2020–2024 have exact periods, official release dates,
block-group product identities, estimate/MOE fields, access routes, and 32
checksum-frozen API metadata files. Four early API manifests omit block groups
and are explicitly routed through official Summary Files; the 1990s gap remains
explicit. Accepted evidence is summarized in
`docs/ACS5_PRODUCT_INVENTORY.md`.

Completed evidence: `POC011` — 421,545 official 2010 blocks and 12,702,379
people allocate to all 9,178 fixed precincts and all 50 districts of the 2001
Final Senate plan. Direct atomic area and official relationship-assisted atomic
area routes both conserve state and source-county totals, retain measured method
deltas, and use no nearest assignments. Thirty-nine QA checks pass and the
second run reused all five immutable artifacts. Accepted evidence is summarized
in `docs/STATEWIDE_2010_RESULT.md`.

Completed evidence: `POC012` — 322,424 official Census 2000 blocks and
12,281,054 people allocate to all 9,178 fixed precincts and all 50 districts of
the 1991 Final Senate plan. Direct atomic area and official 2000→2010
relationship-assisted atomic area routes conserve state/source-county totals
without nearest assignment. Forty-two QA checks pass and the second run reused
all five immutable artifacts. Accepted evidence is summarized in
`docs/STATEWIDE_2000_RESULT.md`.

Completed evidence: `POC013` — 310,668 official 1990 STF 1B blocks and
11,881,643 people allocate to all 9,178 fixed precincts and all 50 districts of
the 1981 Senate plan. Same-topology Census 2000 TIGER faces carrying both block
codes reproduce all published 1990→2000 relationship pairs exactly and supply
the accepted geometry-only weights. Forty-eight QA checks pass and the second
run reused all five immutable artifacts. Accepted evidence is summarized in
`docs/STATEWIDE_1990_RESULT.md`.

Completed evidence: `POC015` — the 2011–2015 ACS five-year Summary File yields
9,740 block groups, a 12,779,559 estimate, and complete 90% MOEs. Simple area
and pre-period 2010 Census block-population support routes cover all 9,178 fixed
precincts and 50 districts of the 2012 Revised Final Senate plan. Estimate and
MOE paths remain separate, 41 QA checks pass, and the second run reused all five
immutable artifacts. Accepted evidence is summarized in
`docs/ACS5_2015_METHOD_RESULT.md`.

Completed evidence: `POC019` — a versioned 380-row matrix crosses all four
decennial and 16 ACS products with all 19 elections. General-election-day
cutoffs classify 114 available and 266 post-cutoff pairings with no
indeterminate rows. Conservative 1991 bounds preserve the unresolved 1990
release day while still classifying every cycle. Fourteen QA checks pass and the
second run reused the mapping identically. Accepted evidence is summarized in
`docs/POPULATION_AVAILABILITY_RESULT.md`.

Completed evidence: `POC016` — all 114 product/election pairings available by
their general-election-day cutoff resolve to 39 immutable product/Senate-plan
allocations. The tracked 115-row execution index retains one explicit 1990
no-product row. Every partition covers 9,178 fixed precincts and 50 Senate
districts, state totals conserve exactly, all ACS MOEs are complete, no nearest
assignment is used, and 19 QA checks pass. Accepted evidence is summarized in
`docs/ALL_PAIRINGS_RESULT.md`.

Completed evidence: `POC023` — one reusable command generates a 20-product by
19-election coverage matrix plus four-panel decennial and representative ACS
fixed-precinct population atlases. All 20 products match all 9,178 target
geometries, Senate-plan partition variance remains below `0.001` person, eight
integration checks and focused tests pass, and every input/output hash is
recorded. Accepted evidence is summarized in `docs/VISUAL_REVIEW.md`.

Completed evidence: `POC024` — a display-only newest-available-period rule
materializes all 174,382 election/fixed-precinct rows and all 950
election/Senate-district rows. All expected geographies remain present; 1990
visibly retains 9,178 missing precincts and 50 missing districts with typed
reasons, while 1992–2026 are complete. Nine integration checks, focused tests,
three identical-replay data hashes, a coverage chart, and 19 election detail
charts pass. Accepted evidence is summarized in
`docs/ELECTION_POPULATION_REVIEW.md`.

Completed evidence: `POC025` — a 41-row versioned catalog and canonical guide
prioritize Census/ACS candidate metrics, tag Census Bureau supplements, record
geography/cadence/cutoff/crosswalk limitations, and explicitly separate concepts
without Census equivalents. Catalog validation tests pass; no row is claimed as
an implemented or selected forecasting feature. Evidence is summarized in
`docs/CENSUS_FEATURE_METRIC_CATALOG.md`.

Completed evidence: `POC026` — tested read-only joins and a Git-friendly marimo
notebook expose election/geography filters, product and plan provenance, exact
coverage, explicit missingness, maps, charts, and sortable rows. The notebook
executes against accepted artifacts; real-data checks retain all 119 Cumberland
precincts as missing in 1990 and all 50 applicable-plan Senate districts as
available in 2018. The QGIS geometry-audit path is documented in
`docs/DATA_EXPLORER.md`.

Completed evidence: `POC027` — a 2,652-row immutable reconciliation compares
all 39 population-product/Senate-plan allocations at Pennsylvania and 67-county
grain against exact official Census block or block-group sums. All statewide
totals conserve exactly; county deltas are signed, typed, and balance statewide.
Direct published ACS `B01003` state/county rows are independently available for
2021–2024 and match the source-unit sums exactly. Earlier accepted tract/block-
group-only extracts retain typed direct-aggregate unavailability. The explorer
shows the selected county plus Pennsylvania, or all counties. Evidence is in
`docs/TRUSTED_TOTAL_RECONCILIATION.md`.

Completed evidence: `POC029` — all eight official 1991, 2001, 2012 Revised
Final, and 2021 Final House/Senate plan sources are checksum-frozen and
normalize reproducibly to 1,012 district geometries. All 22 direct decennial
and 56 direct ACS product/plan/chamber partitions pass their coverage,
conservation, estimate/MOE, no-precinct-input, and no-nearest-assignment gates.
All 78 partitions declare the complete contract and reproduce their immutable
hashes. Final acceptance passes 13 combined checks. See
`docs/POC029_STATUS.md`.

## Core method proof

| ID | Status | Experiment | Depends on | Done when |
|---|---|---|---|---|
| `POC001` | done | Reproduce the prior `S001`–`S003` Cumberland source gate in Python. | — | A saved test/script verifies checksums, required fields, 5,609 exact block keys, 119 precincts, CRS, and total 259,469 from fresh or cached inputs. |
| `POC002` | done | Profile LRC Release 1b block fields for a direct corrected precinct assignment. | `POC001` | A report proves whether every Cumberland block has one usable precinct key and records duplicate, null, and split cases. |
| `POC003` | done | Build the versioned direct/published Cumberland crosswalk. | `POC002` | Allocation rows include source block, target precinct, weight, method/version, and diagnostics; coverage and weight checks pass. |
| `POC004` | done | Independently build a representative-point spatial crosswalk. | `POC001` | Every block is assigned or has a typed exception; boundary tie-breaking is deterministic. |
| `POC005` | done | Aggregate 2020 `P0010001` to Cumberland precincts and compare methods. | `POC003`, `POC004` | County total is 259,469, all 119 targets are accounted for, direct and spatial results are diffed, and LRC precinct totals are reconciled. |
| `POC006` | done | Select and acquire a Philadelphia complex-county boundary candidate. | Owner decision recorded in `PD012` | Source provenance, edge cases, and expected coverage are recorded. |
| `POC007` | done | Compare direct, point, and split-aware allocation on the complex county. | `POC005`, `POC006` | The share of blocks/population affected and precinct-level deltas support a documented method choice. |

## Election geography

| ID | Status | Experiment | Depends on | Done when |
|---|---|---|---|---|
| `POC017` | done | Establish the even-year general-election registry for 1990–2026. | — | Election date, cycle role, fixed target identity, Senate plan identity, House scope, and regular Senate class are recorded for all 19 cycles. |
| `POC008` | in-progress | Freeze the statewide November 3, 2026 general-election precinct snapshot for later production fidelity. | `POC017` | All 67 counties have an authoritative source/resolution or a reviewed gap, plus effective/as-of dates, checksums, House/Senate assignments, and a cutoff. |
| `POC009` | deferred | Reconcile 2021 LRC precincts to the actual 2026 target for later production fidelity. | `POC007`, `POC008` | Added, removed, renamed, and geometry-changed precincts are reported and a 2020-block-to-2026 crosswalk passes statewide QA. |
| `POC018` | deferred | Inventory the actual precinct snapshot for every earlier even-year general election from 1990 through 2024. | `POC017` | Every cycle references a sourced boundary snapshot or a documented gap; reuse across elections is supported by unchanged-boundary evidence. |
| `POC020` | deferred | Validate precinct-to-House/Senate assignments and contest eligibility for each cycle. | `POC008`, `POC018` | Precincts are wholly assigned or carry a typed historical split exception; all House contests and the correct staggered Senate class are represented. |
| `POC021` | done | Freeze and validate the statewide 2021 LRC Data Set 1 precinct geography as the fixed POC target. | `POC007`, `POC017` | A saved audit proves coverage of all 336,985 2020 Census parent blocks and all 9,178 precinct targets, records the 53 split parent blocks and corrected fragments, quantifies geometry precision exceptions, and emits no nearest-neighbor assignments. |
| `POC022` | done | Register official State Senate plans by election cycle and build fixed-precinct-to-Senate fragment geography. | `POC017`, `POC021` | The official 1981, 1991, 2001, 2012 Revised Final, and 2021 Final plan inputs have frozen provenance; every 1990–2026 cycle selects the applicable plan; overlay weights pass coverage/conservation QA; fixed precincts crossing Senate boundaries retain split rows. |

## Population products and election allocation

| ID | Status | Experiment | Depends on | Done when |
|---|---|---|---|---|
| `POC010` | done | Produce the statewide 2020 result on the fixed precinct target and 2021 Final Senate plan. | `POC021`, `POC022` | Crosswalk, precinct and Senate totals, and QA artifacts are repeatable; state and county totals conserve population. |
| `POC011` | done | Add 2010 decennial total population as a reusable source product. | `POC010` | Official source and geometry are confirmed; direct and relationship-assisted routes are compared; the source can be allocated to the fixed precinct target and applicable Senate plan. |
| `POC012` | done | Add 2000 decennial total population as a reusable source product. | `POC011` | The source meets the same provenance, coverage, conservation, and method-comparison gates. |
| `POC013` | done | Add 1990 decennial total population as a reusable source product. | `POC012` | Legacy STF 1 and geometry parsing are reproducible and limitations are reported. |
| `POC014` | done | Inventory all usable mid-decade/ACS population products and release dates. | — | Each available product has an exact period, release date, geography, variable, MOE field, source, and checksum/API manifest; unavailable gaps remain explicit. |
| `POC015` | done | Implement and test the block-group mid-decade allocation method. | `POC007`, `POC014` | Estimate and MOE paths are explicit; simple and population-informed methods are compared against the fixed precinct target and applicable Senate plan. |
| `POC019` | done | Map available population products to election cycles without hiding availability. | `POC011`–`POC015`, `POC017` | Every candidate election/product pairing records reference period, release date, election date, fixed target, Senate plan, and whether it was available by the selected cutoff. |
| `POC016` | done | Run all accepted population/election pairings on the fixed target. | `POC010`–`POC015`, `POC017`, `POC019`, `POC021`, `POC022` | One manifest indexes every election, fixed precinct target, Senate plan, population input, crosswalk, result, QA report, method version, and known limitation. |

## Visual review

| ID | Status | Experiment | Depends on | Done when |
|---|---|---|---|---|
| `POC023` | done | Build reproducible visuals for election/product coverage and population allocated to the fixed precinct target. | `POC016`, `POC019`, `POC021` | Saved year-coverage and precinct-population visuals are generated from accepted artifacts; all 20 products, 19 elections, four decennial maps, 9,178 target precincts, input hashes, and focused QA are represented without relabeling the fixed target as historical precinct geography. |
| `POC024` | done | Build election-year precinct population views and applicable-plan Senate district rollups with explicit missingness. | `POC016`, `POC017`, `POC019`, `POC023` | A documented display-only product rule yields complete election × precinct and election × Senate district tables; reusable per-election visuals expose the selected product, applicable plan, values, and every expected missing precinct/district rather than dropping it. |

## Forecast feature planning

| ID | Status | Experiment | Depends on | Done when |
|---|---|---|---|---|
| `POC025` | done | Establish a versioned Census candidate metric catalog for downstream election prediction. | `POC016`, `POC019` | Canonical and machine-readable catalogs identify Census/ACS or explicitly tagged Census Bureau supplement source families, geography, cadence, cutoff treatment, transformations, crosswalk compatibility, priority, and limitations; cover the requested employment, education, demographic, income, urbanization/permitting, and migration concepts; explicitly record concepts without a Census equivalent; and do not claim that candidates are selected model features. |

## Data exploration

| ID | Status | Experiment | Depends on | Done when |
|---|---|---|---|---|
| `POC026` | done | Add a reusable local explorer for manual inspection of accepted election-year population products. | `POC024` | A documented, version-controlled explorer loads the accepted precinct and Senate outputs read-only; exposes election, geography, county/district, and missingness controls; shows provenance, coverage, a map/chart, and sortable rows; preserves explicit missing records; and has tested data-preparation functions plus a practical geometry-audit path. |
| `POC027` | done | Add trusted Census county and statewide reconciliation to the local explorer. | `POC016`, `POC024`, `POC026` | A reproducible comparison artifact and explorer panel show allocated fixed-precinct sums against official source-unit sums for Pennsylvania and every county; directly published ACS `B01003` county/state totals are retained as a separate benchmark where available; provenance, typed unavailability, tolerances, and deltas are explicit; and focused plus real-data checks pass. |

## Immediate sequence

1. Preserve the accepted `POC029` direct district products and evidence.
2. Archive precinct-only code and ignored artifacts under `POC030`, retaining
   shared inputs and frozen proof evidence through an explicit manifest.

## Direct legislative-plan replacement

| ID | Status | Experiment | Depends on | Done when |
|---|---|---|---|---|
| `POC028` | done | Build a reusable direct legislative-plan crosswalk and prove it with 2020 Census total population on both 2021 Final plans. | `POC010`, `POC022` evidence only | The official House and Senate plan/equivalency inputs are checksum-frozen; the crosswalk contract is chamber-neutral and contains no precinct identity; atomic fragment assignments are separate from metric-specific weights; all 336,985 parent blocks, 203 House districts, and 50 Senate districts are covered; weights sum to one; 13,002,700 people are conserved; official equivalency and independent geometry diagnostics are compared; immutable artifacts and focused tests reproduce. |
| `POC029` | done | Extend the direct crosswalk contract to the applicable 1991, 2001, 2012 Revised Final, and 2021 Final plans and accepted decennial/ACS source families. | `POC028` | Every supported population-product/plan/chamber partition declares its source grain, target plan, weighting universe, fallback policy, applicability, uncertainty, QA, and immutable hash; no partition depends on a precinct artifact. |
| `POC030` | in-progress | Archive precinct-only code, tasks, mappings, and ignored data after direct legislative products reach documented parity. | `POC029` | A manifest identifies retained shared code and frozen evidence; precinct-only material is moved to an explicit archive without deleting accepted proof; active commands, docs, and mappings no longer select precinct products. |
