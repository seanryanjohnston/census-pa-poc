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
| `POC021` | A checksum-verified statewide command, 20 explicit QA checks, immutable assignment/split/precision tables, logical hashes, focused tests, and an accepted report all pass. | The fixed 2021 LRC target covers all 336,985 Census parent blocks through 337,039 corrected fragments and all 9,178 precincts. It records 53 split parents, zero representative-point exceptions, and zero nearest assignments. | The 12,383 strict-cover exceptions total only 0.258206 square meters and are typed numerical/linework slivers. Older source allocation and Senate overlays remain unproven. |
| `POC022` | Five checksum-frozen official plans, an independent 2012 KML cross-check, source/topology profiles, accepted `v3` overlay code, explicit QA, focused tests, and reproducible GeoParquet hashes all pass. | Every 1990–2026 cycle selects an official plan; every plan covers all 9,178 fixed precincts and 50 districts after explicit non-nearest normalization. Historical fixed precincts split across as many as four Senate districts. | Area weights are geographic, not population weights. Typed multi-district gaps have zero uncovered LRC fragment representative points/population; `POC010` independently validates the current plan, while historical population allocations remain future work. |
| `POC010` | A checksum-verified statewide command, immutable crosswalk/result artifacts, 30 explicit QA checks, an independent official Senate block-equivalency route, focused tests, and reproducible logical hashes all pass. | All 336,985 Census parent blocks allocate through 337,039 corrected fragments to all 9,178 fixed precincts. State and all 67 county totals conserve 13,002,700 people. Both routes cover 50 Senate districts and agree exactly in every district. | This is the 2020 PL product on the fixed 2021 LRC target and 2021 Final plan. Election/product availability pairing and older decennial/ACS sources remain unproven. |
| `POC014` | A 16-row tracked product registry, 32 checksum-frozen public API metadata files, 19 QA checks, focused fixtures, and a saved report pass. | Every ACS five-year product from 2005–2009 through 2020–2024 has an exact period, official release date, block-group identity, `B01003_001E` estimate, `B01003_001M` MOE, and viable access route. The 1990s gap stays explicit. | No ACS population has been extracted or allocated. The 2009–2012 API geography manifests omit block groups and need Summary Files; API data requests currently require a runtime key. |
| `POC011` | Three checksum-frozen official Census inputs, fixed-width PL parsing, two atomic crosswalk methods, 39 QA checks, focused fixtures, and five reproducible immutable artifacts pass. | All 421,545 2010 blocks and 12,702,379 people allocate to all 9,178 fixed precincts and all 50 districts of the 2001 Final Senate plan. Direct and relationship-assisted routes conserve state/source-county totals without nearest assignment. | Both methods are area estimates. They differ by 11,852.091 total absolute persons at precinct level and 1,097.571 at Senate level. Sixteen direct representative points expose later-boundary linework, including one relationship-supported block with 11 people. |

## Not yet proven

| Prior ID | Missing proof |
|---|---|
| `I004`–`I006` | Saved normalization code and repeatable loads for block geometry, population, and precinct boundaries. |
| `M003` history | The 2020 published split-aware and 2010 area-based methods are proven statewide; 2000 and 1990 source geometries still need tested crosswalks. |
| `M004` history | Statewide 2020 and 2010 fixed-precinct/Senate results now have unique grain and conservation; 2000 and 1990 remain unproven. |
| `M006` beyond LRC | Philadelphia's published corrected fragments, representative points, and equal-area overlay were compared. A population-informed method for targets without published split populations remains unproven. |
| `H003`–`H004` | Any statewide 2000 or 1990 result. |
| `H006` | A tested ACS block-group allocation and MOE-propagation method; the source inventory itself is complete. |
| `H007` | A pre-ACS interpolation policy; the POC currently leaves the 1990s gap explicit. |
| `H008` | A reconciled, frozen actual 2026 precinct snapshot. This is deferred production-fidelity work under `PD014`, not a fixed-geography POC blocker. |
| Deferred actual-vintage scope | Election-effective precinct snapshots from 1990 through 2026 and actual precinct-to-legislative assignments. PASDA and county research is incomplete and cannot be replaced by the fixed target. |

## Important interpretation

The Cumberland mechanics and Philadelphia complex-county method comparison are
proven and saved. The published LRC split route is accepted for the
2020-to-2021 LRC baseline, and `POC021` now proves that fixed target statewide.
The fixed target, period Senate overlays, statewide 2020 and 2010 population
results, and complete ACS five-year inventory are now proven. No 2000/1990 or
ACS allocation follows yet. The next proof boundary is 2000 decennial allocation
(`POC012`) or the separate ACS block-group method (`POC015`). Actual 2026 and
historical precinct reconstruction remains explicitly deferred.
