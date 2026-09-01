# Accepted POC029 direct historical legislative result

Status: **done — 100% complete**

`POC029` replaces precinct-mediated population allocation with direct
population-source-to-legislative-plan partitions for both Pennsylvania State
House and State Senate districts. The percentage uses five implementation
milestones rather than treating every output partition as equal work:

| Milestone | Weight | Status |
|---|---:|---|
| Contract and inherited-method audit | 10% | complete |
| Official historical House/Senate plan source gate | 20% | complete |
| Direct decennial partitions | 30% | complete |
| Direct ACS estimate/MOE partitions | 30% | complete |
| Full-suite replay and final accepted documentation | 10% | complete |

At the output-partition level, all 78 planned product/plan/chamber partitions
are complete: 22 decennial and 56 ACS. The final acceptance gate verifies that
every partition declares source grain, target plan and applicability, weighting
universe, fallback, uncertainty, QA, and immutable hashes.

## Completed plan source gate

The official Pennsylvania Legislative Reapportionment Commission catalog
provides the 1991 Final, 2001 Final, 2012 Revised Final, and 2021 Final plan
archives needed for both chambers. `mappings/legislative_plans_v1.csv` freezes
all eight exact sources, applicability, local paths, archive members, district
fields, and SHA-256 values.

The normalized GeoParquet contains 1,012 rows: one valid EPSG:4269 geometry for
each of 203 House and 50 Senate districts in each of four plan vintages. Its
logical SHA-256 is
`5e426cb123757c0d3eda588ec4c3c229c5dbb21012ce161ded97ac1e594f119d`,
and the verification replay reused it identically.

Source defects remain explicit rather than disappearing into the normalized
artifact:

- the 1991 House SHAPE source has no parsed CRS and publishes 220 multipart
  rows for 203 districts; its projection text supports EPSG:4269;
- one raw 1991 Senate geometry and one raw 2012 House geometry are invalid;
- the 2001 House, 2012 House, and 2012 Senate sources contain measured internal
  overlaps.

The source profile, QA, and human-readable report are under
`artifacts/poc029/`.

## Completed direct decennial stage

All 22 applicable decennial product/plan/chamber partitions pass. They cover
the four decennial products, both chambers, and the plan vintages applicable
from each source vintage forward:

| Product | State total conserved | Direct partitions |
|---|---:|---:|
| 1990 decennial | 11,881,643 | 8 |
| 2000 decennial | 12,281,054 | 6 |
| 2010 decennial | 12,702,379 | 6 |
| 2020 decennial | 13,002,700 | 2 |

Every partition has the expected 203 House or 50 Senate districts, weights sum
to one within tolerance, and no partition contains precinct identity, consumes
a precinct artifact, or uses nearest-boundary assignment. Historical products
retain their geometry-only relationship/area weighting uncertainty and typed
zero-population exceptions. The combined result's logical SHA-256 is
`d4728c5017a82ee32880f5ff3c3bd94ae3b91af57503fb8cfe55886f1aaa0eff`,
and the verification replay reused it identically.

One material source issue required a narrow evidence-backed exception. Census
1990 block `420490117010102` carries five people into Census 2000 block
`420490117011001`, but both official 1991 House SHAPE and KML linework leave the
target block uncovered. The official 1991 legal description assigns North East
township to House District 4, and official Census 2000 county-subdivision
geometry places the target block in that township. The crosswalk therefore
records one exact legal-description override to District 4, including all
three supporting checksums. It does not assign the block to the nearest
district.

## Completed direct ACS stage

All 56 direct ACS product/plan/chamber partitions pass across 16 products and
18 reusable crosswalks. They retain the accepted vintage-safe support policy:

- 2009 and 2010 use normalized block-group/plan area;
- 2011–2019 use 2010 Census block population, with nine typed zero-support
  area fallbacks; and
- 2020–2024 carry 2010 population through the official 2010→2020 relationship,
  with 74 typed zero-support area fallbacks.

Every partition has 203 House or 50 Senate districts, conserves its source
estimate, keeps estimates and 90% MOEs separate, and uses neither precinct
input nor nearest assignment. The combined ACS result's logical SHA-256 is
`46d8b71b6bb78083013da2b77da428e321f4719c38e97e230e2ba9d6db54deae`,
and the verification replay reused it identically.

Two zero-estimate water-only Census 2010 block groups—`420490124000` and
`420499900000`—fall wholly outside the official 2001 House polygons. They are
retained as typed unassigned exceptions rather than forced into a nearby
district. Their estimates sum to zero and their source MOEs sum linearly to
218; those MOEs are not assigned to a district.

## Final acceptance and remaining limitations

The final acceptance gate passes 13 checks across eight official plans, 20
population products, and all 78 unique partitions. It also verifies 502 stage
checks, valid per-partition hashes, identical plan/result replays, complete
contract declarations, both chambers, no precinct dependency, and no nearest
assignment.

The known analytical limitations remain: area is a model rather than
population truth, older ACS support becomes stale, and target MOEs omit
covariance and allocation-weight uncertainty. Crosswalk replays are I/O-heavy
because the 22 decennial files contain roughly 7.5 million allocation rows,
but both result families replay deterministically.

`POC029` is accepted and direct legislative parity is documented. `POC030`
subsequently archived precinct-only code, data, mappings, and tasks while
preserving shared inputs and frozen proof evidence; see `docs/POC030_ARCHIVE.md`.
