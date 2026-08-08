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
independently confirmed by Department of State candidate requirements.

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
| `POC017` | done | Establish the even-year general-election registry for 1990–2026. | — | Election date, cycle role, House scope, regular Senate class, and target snapshot identity are recorded for all 19 cycles. |
| `POC008` | ready | Freeze the statewide November 3, 2026 general-election precinct snapshot. | `POC017` | All 67 counties have an authoritative source/resolution or a reviewed gap, plus effective/as-of dates, checksums, House/Senate assignments, and a cutoff. |
| `POC009` | ready | Reconcile 2021 LRC precincts to the frozen 2026 target. | `POC007`, `POC008` | Added, removed, renamed, and geometry-changed precincts are reported and a 2020-block-to-2026 crosswalk passes statewide QA. |
| `POC018` | ready | Inventory the precinct snapshot for every earlier even-year general election from 1990 through 2024. | `POC017` | Every cycle references a sourced boundary snapshot or a documented gap; reuse across elections is supported by unchanged-boundary evidence. |
| `POC020` | deferred | Validate precinct-to-House/Senate assignments and contest eligibility for each cycle. | `POC008`, `POC018` | Precincts are wholly assigned or carry a typed historical split exception; all House contests and the correct staggered Senate class are represented. |

## Population products and election allocation

| ID | Status | Experiment | Depends on | Done when |
|---|---|---|---|---|
| `POC010` | deferred | Produce the statewide 2020-to-2026 general-election result. | `POC007`, `POC009` | Crosswalk, totals, and QA artifacts are repeatable; state and county totals conserve population. |
| `POC011` | deferred | Add 2010 decennial total population as a reusable source product. | `POC010` | Official source and geometry are confirmed; direct and relationship-assisted routes are compared; the source can be allocated to any selected election snapshot. |
| `POC012` | deferred | Add 2000 decennial total population as a reusable source product. | `POC011` | The source meets the same provenance, coverage, conservation, and method-comparison gates. |
| `POC013` | deferred | Add 1990 decennial total population as a reusable source product. | `POC012` | Legacy STF 1 and geometry parsing are reproducible and limitations are reported. |
| `POC014` | ready | Inventory all usable mid-decade/ACS population products and release dates. | — | Each available product has an exact period, release date, geography, variable, MOE field, source, and checksum/API manifest; unavailable gaps remain explicit. |
| `POC015` | deferred | Implement and test the block-group mid-decade allocation method. | `POC007`, `POC014` | Estimate and MOE paths are explicit; simple and population-informed methods are compared and can target any election snapshot. |
| `POC019` | deferred | Map available population products to election cycles without hiding availability. | `POC011`–`POC015`, `POC017` | Every candidate election/product pairing records reference period, release date, election date, target snapshot, and whether it was available by the selected cutoff. |
| `POC016` | deferred | Run all accepted population/election pairings. | `POC010`, `POC018`–`POC020` | One manifest indexes every election, precinct snapshot, population input, crosswalk, result, QA report, method version, and known limitation. |

## Immediate sequence

Use the completed `POC017` registry to drive `POC014`'s mid-decade inventory
and source research for `POC008` and `POC018`. Once `POC008` freezes the actual
November 3, 2026 target, run `POC009` to reconcile it to the 2021 LRC baseline.
Do not treat the qualified current Philadelphia City layer as election-effective
without additional evidence, and do not build production infrastructure before
the statewide and historical source gaps are understood.
