# Proof status

This ledger separates documentary/source checks from a demonstrated analytical
pipeline. Claims inherited from `census-pa-map` were reviewed on 2026-08-07.

## Proven or implemented

| Prior ID | Evidence | What it proves | Limitation |
|---|---|---|---|
| `S001` | Exact official 2020 PA block geometry and P.L. 94-171 archives, URLs, SHA-256 values, schemas, row counts, exact geometry/population key match, and PA/Cumberland totals are recorded. | The 2020 Census inputs are available and internally joinable. | The ad hoc verification code was not preserved as the reusable Python POC. |
| `S002` | Exact LRC 2021 Release 1b geography archive, checksum, schema notes, 9,178 statewide precincts, and 119 Cumberland precincts are recorded. | A viable corrected 2021 precinct baseline exists. | It is not an authoritative 2026 snapshot and redistribution terms remain unclear. |
| `S003` | Cumberland has 5,609 matching Census/LRC blocks, compatible CRS, 119 precinct polygons, and total population 259,469 in each relevant source. | Cumberland is ready for a mechanics experiment with known totals. | It does not prove topology, assignment, a crosswalk, or precinct-level aggregation. |
| `F001`–`F005` | Git, Elixir application, PostGIS, schemas, commands, and smoke tests passed in the first repository. | Production-foundation mechanics work. | None of this proves the Census-to-precinct analytical method and it is not required by this Python POC. |
| `I001`–`I002` | Catalog constraints and an immutable HTTP retriever have tests in uncommitted work in the first repository. | A production provenance/download design is substantially implemented. | It is currently dirty/uncommitted and should not be mistaken for POC analysis code. |
| `POC001`–`POC005` | Saved Python loaders, two versioned crosswalk builders, aggregation, machine-readable QA, focused fixtures, and an accepted report all pass. | For Cumberland, 2020 standard total population can be reproducibly assigned to all 119 LRC Release 1b precincts by either the published key or a representative point. Both methods assign all 5,609 blocks identically and conserve 259,469 people. | Cumberland has no observed split or ambiguous blocks and cannot select the final statewide/split-aware method. The target is the 2021 LRC snapshot, not 2026. |
| `POC006`–`POC007` | A checksum-frozen City of Philadelphia boundary candidate, saved source/schema profile, three versioned crosswalks, method deltas, focused tests, and an accepted report all pass. | Philadelphia contains 13 LRC corrected split blocks covering 931 people. Published corrected-fragment allocation exactly reconciles 1,603,797 people to all 1,703 LRC precinct totals; representative points change eight precincts and equal-area overlay changes 12. | The published split route applies to the 2020-to-2021 LRC target. The current City layer lacks an election-effective date and differs from LRC by 51 IDs in each direction; post-2021 and other targets still need reconciliation and a validated weighting method. |

## Not yet proven

| Prior ID | Missing proof |
|---|---|
| `I004`–`I006` | Saved normalization code and repeatable loads for block geometry, population, and precinct boundaries. |
| `M003` statewide | Cumberland and Philadelphia now have deterministic direct/published, representative-point, and split-aware comparisons; statewide coverage remains unproven. |
| `M004` statewide/history | Cumberland precinct aggregation now has unique grain and exact conservation; statewide and historical targets remain unproven. |
| `M006` beyond LRC | Philadelphia's published corrected fragments, representative points, and equal-area overlay were compared. A population-informed method for targets without published split populations remains unproven. |
| `H002`–`H005` | A statewide 2020 result or any 2010, 2000, or 1990 result. |
| `H006`–`H007` | A mid-decade ACS/cutoff policy or pre-ACS interpolation policy. |
| `H008` | A reconciled, frozen 2026 precinct snapshot. |
| New POC scope | An inventory of the precinct snapshot used for every even-year general election from 1990 through 2026, including legislative-district assignments and Senate contest class. |

## Important interpretation

The Cumberland mechanics and Philadelphia complex-county method comparison are
now proven and saved. The published LRC split route is accepted for the
2020-to-2021 LRC baseline, but no statewide, 2026, historical, or ACS claim
follows from these county proofs. The next proof boundaries are the actual 2026
target (`POC008`), historical election snapshots (`POC018`), and the available
mid-decade product inventory (`POC014`).
