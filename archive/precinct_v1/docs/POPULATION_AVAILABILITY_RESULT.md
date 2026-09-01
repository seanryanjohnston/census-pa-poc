# Accepted population-product/election availability map

`POC019` passed on 2026-08-29. It crosses all accepted or inventoried population
products with every Pennsylvania even-year general election from 1990 through
2026 and classifies whether each product was released by the election-day
information cutoff.

## Contract

The versioned mapping
`mappings/population_election_availability_v1.csv` contains 380 rows:

`19 elections × (4 decennial products + 16 ACS five-year products)`

Every row preserves:

- product identity, family, reference start/end, metric, source geography, and
  population universe;
- published release value, its precision, and conservative earliest/latest
  release bounds;
- election identity/date/role and the selected general-election-day cutoff;
- fixed 2021 LRC precinct target and the official Senate plan for that cycle;
- source processing and allocation readiness;
- accepted method ID where one is already proven; and
- reference-period completion, availability, and `POC016` candidacy.

The full cross-product is intentional. Post-election products remain as
`not_available` rows rather than disappearing from the record. Availability
does not select forecast features; it only prevents future-data leakage.

## Release precision

The 2000, 2010, and 2020 decennial releases and all 16 ACS releases have exact
dates. The 1990 STF 1B Pennsylvania release remains known only as `1991`, so
the matrix records:

- precision: `year_only`;
- earliest possible date: `1991-01-01`; and
- latest possible date: `1991-12-31`.

Those bounds classify every POC election without inventing a day. The product
was unavailable for the November 6, 1990 election even under the earliest
bound, and available for every 1992–2026 election even under the latest bound.
No pairing is indeterminate.

Under `PD022`, general-election day is the POC information cutoff. A later
training design may choose an earlier operational cutoff, but it must create a
new mapping version rather than reinterpret this one.

## Results

- 114 product/election pairings are available by election day.
- 266 pairings were released after the election.
- Zero pairings are indeterminate.
- Available product counts are monotonic for every product.
- Every row retains the fixed target and exactly one of the five period Senate
  plans selected by the election registry.

Products available by selected election include:

| Election | Available products |
|---|---:|
| 1990 | 0 |
| 1992–2000 | 1 each |
| 2002–2010 | 2 each |
| 2012 | 5 |
| 2014 | 7 |
| 2016 | 9 |
| 2018 | 11 |
| 2020 | 13 |
| 2022 | 16 |
| 2024 | 18 |
| 2026 | 20 |

The zero-product 1990 cycle is an explicit strict-cutoff limitation: none of
the currently cataloged Census/ACS products had been released by that election.
It is not repaired with a post-election product or hidden interpolation.

All 14 QA checks pass. A second complete run reused the versioned CSV
identically. Its logical SHA-256 is
`1f64182266de52f312e1b47483a551e389cf90e13d03d94bf2a49f2d8bb764c7`.
Machine-readable QA and the checksum-frozen input manifest are under ignored
`artifacts/poc019/`.

## Limits and next boundary

- The matrix identifies availability, not which population features a forecast
  should use.
- `POC016` subsequently allocated all 15 other ACS products with the non-
  leaking support regimes accepted in `PD023`.
- Reusing an old population product for a later election requires a distinct
  allocation when its period Senate plan changes. `POC016` executes those
  product/plan partitions rather than silently relabeling single-plan results.
- If a downstream design requires a population feature for 1990 that was
  available by election day, it needs a different pre-election source product
  or an explicit change to the information-cutoff policy.
