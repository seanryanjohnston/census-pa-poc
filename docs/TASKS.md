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
| `POC008` | deferred | Freeze the statewide November 3, 2026 general-election precinct snapshot for later production fidelity. | `POC017` | All 67 counties have an authoritative source/resolution or a reviewed gap, plus effective/as-of dates, checksums, House/Senate assignments, and a cutoff. |
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
| `POC012` | ready | Add 2000 decennial total population as a reusable source product. | `POC011` | The source meets the same provenance, coverage, conservation, and method-comparison gates. |
| `POC013` | deferred | Add 1990 decennial total population as a reusable source product. | `POC012` | Legacy STF 1 and geometry parsing are reproducible and limitations are reported. |
| `POC014` | done | Inventory all usable mid-decade/ACS population products and release dates. | — | Each available product has an exact period, release date, geography, variable, MOE field, source, and checksum/API manifest; unavailable gaps remain explicit. |
| `POC015` | ready | Implement and test the block-group mid-decade allocation method. | `POC007`, `POC014` | Estimate and MOE paths are explicit; simple and population-informed methods are compared against the fixed precinct target and applicable Senate plan. |
| `POC019` | deferred | Map available population products to election cycles without hiding availability. | `POC011`–`POC015`, `POC017` | Every candidate election/product pairing records reference period, release date, election date, fixed target, Senate plan, and whether it was available by the selected cutoff. |
| `POC016` | deferred | Run all accepted population/election pairings on the fixed target. | `POC010`–`POC015`, `POC017`, `POC021`, `POC022` | One manifest indexes every election, fixed precinct target, Senate plan, population input, crosswalk, result, QA report, method version, and known limitation. |

## Immediate sequence

`POC010`, `POC011`, `POC014`, `POC021`, and `POC022` are complete. Advance
historical decennial inputs newest to oldest with `POC012`; `POC015` is also
ready for the separate ACS block-group allocation proof.
`POC008`, `POC009`, `POC018`, and `POC020` remain explicit later-fidelity tasks;
their source research is useful but no longer blocks the fixed-geography POC.
