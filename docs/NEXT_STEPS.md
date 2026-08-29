# Next steps and blockers

Updated 2026-08-29.

## Current POC geography decision

The POC now uses the Pennsylvania LRC 2021 Data Set 1 precinct geography as a
single fixed target for every population period and election cycle (`PD014`).
This is a constant-geography/counterfactual model. It supports comparable units
across time but does not reconstruct the precincts that voters actually used in
1990–2026. The target must be labeled `2021 LRC precincts`, not `2020
precincts`, historical precincts, or 2026 precincts.

State Senate geography remains time-varying (`PD015`). Use the official LRC
plan polygons applicable to each election and overlay them with the fixed
precinct target. Do not derive Senate districts by dissolving precincts and do
not assume a fixed precinct is wholly contained by every historical Senate
district. The common atomic geography is:

`population source unit ∩ fixed 2021 LRC precinct ∩ applicable Senate plan`

Aggregate those fragments by fixed precinct for comparable precinct output and
by Senate district for period-correct Senate output. If only Senate totals are
needed, a direct source-to-Senate allocation can be retained as an independent
validation route.

## Fixed-target coverage finding

`POC021` now saves and reproduces the statewide audit against the frozen
Census/LRC inputs:

- 336,985 unique 2020 Census Pennsylvania parent blocks;
- the same 336,985 parent block IDs in 337,039 LRC block fragments;
- no Census-only or LRC-only parent block IDs;
- 9,178 unique target precincts and 9,178 referenced target IDs;
- 336,932 parent blocks assigned to one precinct, 52 split across two, and one
  split across three;
- no null, empty, or invalid block-fragment or precinct geometries; and
- all 337,039 assigned fragment representative points covered by their target
  precinct.

A strict full-polygon coverage test reported 12,383 linework/precision
exceptions, but their maximum outside area was about `1.01e-11` square degrees
and their total outside area about `1.79e-11` square degrees. These are
numerical/topological slivers, not evidence of semantically uncovered blocks.
The accepted evidence and logical artifact hashes are recorded in
`docs/STATEWIDE_FIXED_GEOGRAPHY_PROOF.md`.

Do not assign polygon stragglers to the closest boundary (`PD016`). Prefer a
published direct assignment; otherwise use intersection weights in a suitable
common CRS, require weights to sum to one within tolerance, retain typed
water/precision exceptions, and fail material uncovered populated areas.
Nearest-boundary assignment is diagnostic only.

## State Senate plan sequence

The official LRC GIS catalog publishes statewide Senate SHAPE files for every
plan needed by the POC:

| Elections | Senate plan |
|---|---|
| 1990 | 1981 plan |
| 1992–2000 | 1991 Final plan |
| 2002–2012 | 2001 Final plan |
| 2014–2020 | 2012 Revised Final plan |
| 2022–2026 | 2021 Final plan, effective for elections beginning in 2022 |

The 2001 plan remains the correct entry for the 2012 election because the
Pennsylvania Supreme Court rejected the initial post-2010 plan and left the
prior plan in force for that cycle:
https://www.pacourts.us/Storage/media/pdfs/20210208/160352-majorityopinion.pdf

No later legislative reapportionment supersedes the 2021 Final plan for 2026.
`mappings/senate_plans.csv` records the official source URLs and frozen
checksums, and `mappings/election_cycles.csv` selects a plan per cycle.

`POC022` passes with `fixed_precinct_senate_overlay_v3`. The source gate found
one repaired 1991 self-intersection, historical plan/state-line gaps, and an
official 2012 District 1/8 overlap confirmed independently by the official KML.
`PD017` preserves the accepted non-nearest normalization. All five outputs cover
9,178 fixed precincts and 50 districts; 997–1,126 fixed precincts split under
the historical plans, while none split under the 2021 Final plan. Typed
multi-district gaps contain zero uncovered LRC fragment representative points
and zero population. Full evidence is in
`docs/STATE_SENATE_OVERLAY_PROOF.md`.

Official catalog:
https://www.redistricting.state.pa.us/Maps/

## Actual precinct source research retained for later fidelity

The earlier `POC008` work remains useful but is no longer on the simplified
POC's critical path. Its 67-county ledger has two checksum-frozen candidates
(Delaware and Philadelphia) and 65 unreviewed counties. The DEP eMapPA voting
layer remains rejected as a 2026 shortcut because it lacks election-effective
lineage and resembles the 2010 VTD identifier set more than the 2020 benchmark.

PASDA does not provide a complete statewide current precinct polygon product.
A broader public catalog review found county-origin polygon layers for 12 of
67 counties: Allegheny, Berks, Bucks, Centre, Crawford, Cumberland, Delaware,
Forest, Snyder, Union, Washington, and York. Clearfield and Montgomery expose
polling-location points rather than boundary polygons. Public historical
snapshots were also found for only a subset of those counties. Treat PASDA
layers as county candidate/validation sources, not as a statewide authoritative
snapshot, and never infer election vintage from a publication date.

PASDA search entry:
https://www.pasda.psu.edu/uci/SearchResults.aspx?Keyword=precinct

Delaware County's official 2026 consolidation packet remains a clear example of
why actual-vintage work is separate: it reduced 428 precincts to 383 for the
2026 primary and later elections, while the machine-readable PASDA layer does
not establish that complete election-effective target.

## Immediate sequence

`POC010` is complete. Its accepted result covers all 336,985 Census parent
blocks, 337,039 LRC fragments, 9,178 fixed precincts, 67 counties, and 50
current-plan Senate districts. State and county totals conserve 13,002,700
people. The fixed-precinct rollup and official direct block-equivalency routes
agree exactly in every Senate district. See `docs/STATEWIDE_2020_RESULT.md`.

`POC014` is also complete. Sixteen ACS five-year products cover 2005–2009
through 2020–2024, with exact release dates, block-group identities,
`B01003_001E`/`B01003_001M`, access routes, and 32 frozen metadata checksums.
The 2009–2012 API geography manifests omit block groups and therefore use
official Summary Files. The latest 2020–2024 product was actually released on
January 29, 2026 after its original December 2025 schedule was revised.

`POC011` is complete. Its 2010 result covers 421,545 Census blocks, all 9,178
fixed precincts, 67 source counties, and all 50 districts of the 2001 Final
Senate plan. Both the direct atomic-area route and the official
relationship-assisted atomic-area route conserve 12,702,379 people at state and
source-county levels. Their nonzero differences remain explicit uncertainty
evidence; neither route uses 2020 population as a historical weight.

The run exposed two boundary/serialization findings that are now handled
explicitly:

- Sixteen 2010 block representative points fall outside the later atomic target.
  Fifteen are zero-population. The remaining block has 11 people and 54.4%
  direct coverage, but the official relationship file supplies complete
  Pennsylvania topology support. The direct route remains a normalized
  diagnostic and the relationship-assisted route is the accepted baseline.
- Nullable target identifiers changed dtype after the first Parquet round trip.
  The accepted crosswalk schema now freezes nullable strings and `Int64` before
  hashing; the second complete run reused all five artifacts identically.

1. `POC012`: add the 2000 decennial source using the same provenance,
   atomic-target, method-comparison, and conservation gates.
2. `POC015`: implement the separate block-group ACS estimate/MOE allocation
   proof using a runtime API key or official Summary Files.
3. Continue the 1990 decennial input after 2000.

## Estimated completion

By authoritative task count, 13 of the 18 simplified fixed-geography POC tasks
are done: about **72%**. The denominator excludes only the four explicitly
deferred actual-vintage fidelity tasks (`POC008`, `POC009`, `POC018`, and
`POC020`). Counting those later-fidelity tasks in the full 22-task backlog gives
13 of 22 done: about **59%**. These are task-count estimates, not equal-effort or
schedule estimates.

## Remaining limitations and deferred blockers

- Historical/current actual-precinct outputs still require `POC008`, `POC009`,
  `POC018`, and `POC020`; fixed-geography results cannot answer questions about
  historical election administration or join historical precinct-level returns
  without additional crosswalks.
- The accepted 2010 relationship-assisted route and its direct comparison are
  equal-area estimates. The precinct methods differ by 11,852.091 total absolute
  persons and the Senate methods by 1,097.571; a population-informed support
  surface remains unproven.
- 2000/1990 blocks and ACS block groups can cross both the fixed precinct target
  and a Senate plan. Their allocation remains approximate unless a direct or
  population-informed source is available.
- Targets without published corrected-fragment populations still require a
  tested population-informed split method; equal-area allocation is a
  diagnostic baseline, not population truth.
- ACS estimates and margins of error require separate propagation and QA.
- Census data API requests require a runtime API key as of 2026-08-29. This is
  not an inventory blocker because official Summary Files remain available,
  but `POC015` must select and record one extraction route without storing a
  credential.
- External publication remains blocked pending review of source redistribution
  terms, especially for Pennsylvania LRC-derived artifacts.
