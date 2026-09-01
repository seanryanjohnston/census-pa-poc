# Project scope

## Active goal

Allocate Census decennial and ACS total-population products directly from their
published source geographies to the official Pennsylvania State House and State
Senate plan applicable to elections from 1992 through 2026.

Prove additional additive metrics one exact table and universe at a time. The
first accepted extension is 2020 PL 94-171 `P0030001` voting-age population on
the 2021 Final plans; it has its own metric-specific support crosswalk. The
remaining POC bundle covers eligible-electorate and demographic person counts,
socioeconomic person counts, household and occupied-housing counts, and
population density as grouped in `docs/TASKS.md`.

Every accepted partition preserves its source grain, product and metric,
legislative chamber and plan vintage, election applicability, weighting
universe, fallback policy, uncertainty, QA, and immutable logical hashes.
Precinct geography is not an active target or intermediate.

## Proven boundary

- `POC028` proves direct 2020 Census P001 allocation to both 2021 Final plans.
- `POC029` extends the contract to all 20 accepted population products and all
  applicable 1991, 2001, 2012 Revised Final, and 2021 Final House/Senate plans.
- `POC030` moves precinct-only material into an explicit archive and pivots the
  active explorer, commands, docs, and mappings to the direct products.
- `POC031` proves 2020 voting-age population for both current chambers without
  reusing total-population weights.
- `POC032` exposes the VAP result through a separate metric-universe selector
  in the direct explorer.
- `POC034` narrows the notebook to the 2021 Final plans used in 2026, proves
  both chamber sums against an independently read Census state total, and
  exposes the accepted metric-specific split-block allocations.
- `POC039` closes the POC with complete 1992–2026 House and Senate
  district-by-election CSV panels over all readily usable accepted metrics.

The POC is closed by `POC039`, which packages all readily usable accepted work
as complete House and Senate district-by-election CSV panels for 1992–2026.
Harder inventoried families may be deferred instead of manufacturing weak
continuity. Later user-guided explorer changes and manual quality investigations
may continue without extending the proof scope.

## Current non-goals

- Precinct aggregation or reconstruction.
- Election-result ingestion or forecasting.
- Metrics that cannot be made complete under the `POC039` export contract with
  a transparent, defensible source or transformation.
- Treating area weights as observed population distribution.
- Treating derived ACS district MOEs as total uncertainty.
- Publishing raw or derived data before redistribution terms are reviewed.

Shared legacy-named modules may remain active only when the direct pipeline
imports their Census parsers, source constants, geometry loaders, or hashing
helpers. Their precinct output commands are not part of the active workflow.
