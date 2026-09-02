# Project scope

## Active goal

Allocate Census decennial and ACS total-population products directly from their
published source geographies to the official Pennsylvania State House and State
Senate plan applicable to elections from 1992 through 2026.

The current-plan notebook also includes 2020 PL 94-171 `P0030001` voting-age
population with its own metric-specific support crosswalk. The final exports
add the completed education, employment, and poverty series.

Every accepted partition preserves its source grain, product and metric,
legislative chamber and plan vintage, election applicability, weighting
universe, fallback policy, uncertainty, QA, and immutable logical hashes.
Precinct geography is not an active target or intermediate.

## Proven boundary

- `POC028` proves direct 2020 Census P001 allocation to both 2021 Final plans.
- `POC029` extends the contract to all 20 accepted population products and all
  applicable 1991, 2001, 2012 Revised Final, and 2021 Final House/Senate plans.
- `POC031` proves 2020 voting-age population for both current chambers without
  reusing total-population weights.
- `POC032` exposes the VAP result through a separate metric-universe selector
  in the direct explorer.
- `POC034` narrows the notebook to the 2021 Final plans used in 2026, proves
  both chamber sums against an independently read Census state total, and
  exposes the accepted metric-specific split-block allocations.
- `POC036` proves the education, employment, and poverty inputs used by the
  final exports.
- `POC039` closes the POC with complete 1992–2026 House and Senate
  district-by-election CSV panels.

The POC is closed by `POC039`. Its maintained surface is the direct population
proof and QA totals, the current notebook, and the v2 House and Senate exports.

## Current non-goals

- Precinct aggregation or reconstruction.
- Election-result ingestion or forecasting.
- Adding metric families beyond the accepted export columns.
- Treating area weights as observed population distribution.
- Treating derived ACS district MOEs as total uncertainty.
- Publishing raw or derived data before redistribution terms are reviewed.

Some legacy-named modules remain because the direct pipeline imports their
Census parsers, source constants, geometry loaders, or hashing helpers. Their
former precinct outputs are not part of the working tree or active workflow.
