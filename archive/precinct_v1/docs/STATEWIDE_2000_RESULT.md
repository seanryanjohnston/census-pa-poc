# Accepted statewide Census 2000 result

`POC012` passed on 2026-08-29. It proves that Census 2000 standard total
population can be allocated to the fixed 2021 LRC precinct target and the 1991
Final State Senate plan by two explicit, reproducible area methods.

## Frozen inputs

| Input | Exact product / vintage | SHA-256 |
|---|---|---|
| Population geography | Census 2000 Pennsylvania PL 94-171 geography header, released 2001-03-09 | `34d4079451e3d3e1396b76287d54d0a96814de8d46059a327547b74c8ea3f672` |
| Population File 01 | Census 2000 Pennsylvania PL 94-171 File 01, released 2001-03-09 | `888e21ecac795732564c7cd1fa3122cac58f22a006ade8f907d437cbe7a6fe0f` |
| Source geometry | 2010 TIGER/Line Census 2000 Pennsylvania tabulation blocks | `a5771874f846018ddf7d3761939a8e9cd3ecdf8d34364caa53e84630707c85dc` |
| Relationship aid | Official Census 2000 to 2010 tabulation block relationship file | `ab32c86a78d72e39d791167b8eec6f960934cd13c0878833641d0c36e4be5fa7` |
| Intermediate geometry | 2010 TIGER/Line Pennsylvania tabulation blocks | `fc33d93eb53e71b0d61c3aa35d496a8a8b8d192933d68ebef206ccbaa9e19152` |
| Senate atomic target | Accepted `pa_senate_1991_final_fixed_precinct_overlay_v3` | logical SHA-256 `d60a3584ff2a457ef99736607ec656f2d376aed5a7000a2e30a84c82e5477d26` |

The population parser handles the separate fixed-width geography and
comma-delimited File 01 archives. Census 2000 places the state and county
fields at different offsets from the 2010 legacy header. The frozen parser
finds 322,424 unique block rows, matches all 322,424 valid source geometries,
and totals exactly 12,281,054 people.

## Compared methods

`direct_atomic_area_2000_v1` intersects each Census 2000 block directly with:

`fixed 2021 LRC precinct ∩ 1991 Final Senate district`

in EPSG:5070 and normalizes weights over covered area.

`relationship_atomic_area_2000_v1` first normalizes the official 2000→2010
land-plus-water intersection areas, then composes those weights with a
geometry-only 2010-block-to-atomic-target area crosswalk. It does not use 2010
or 2020 population as a historical support surface. Under `PD019`, this is the
accepted Census 2000 POC baseline because it preserves the official
inter-vintage topology; direct overlay remains the independent diagnostic.

Both methods are geographic area estimates, not population-weighted truth.

## Results and QA

- 322,424 source blocks, 9,178 fixed precincts, 67 source counties, and all 50
  districts of the 1991 Final Senate plan are accounted for.
- Both routes conserve 12,281,054 people at state and source-county levels.
- The direct route emits 484,794 atomic allocation rows and assigns every source
  block without an uncovered-source exception.
- The relationship route begins with 505,426 official rows covering every
  source block. It has 92,834 source blocks related to multiple 2010 blocks and
  as many as 216 relationship rows for one source.
- Neither route uses nearest-boundary assignment.
- The methods differ in 7,170 precincts by 8,678.841 total absolute persons;
  the largest precinct delta is 246.990.
- All 50 Senate districts differ, but only by 0.235 total absolute person; the
  largest district delta is 0.030.

The direct geometry audit found seven source representative points outside the
later atomic target; all seven blocks have zero population. It also found 131
blocks below 99% direct coverage. Forty-eight of those blocks are populated and
carry 901 people. Multiplying each source population by its uncovered area
share gives a 20.764-person diagnostic, with a maximum of 2.055 for one source.
That calculation is not an observed population location; it shows why the
direct covered-area normalization remains a comparison rather than the
baseline.

The 2010-to-atomic bridge leaves four 2010 blocks uncovered. Three occur in
relationship rows. Two affected Census 2000 source blocks have zero population;
the third has seven people and sends only 0.0596% of its relationship area to
the unsupported 2010 block. The equal-area-implied amount is 0.0042 person,
below the explicit 0.01-person QA tolerance. Every affected source retains
supported target area, per-source normalization stays explicit, and no nearest
assignment is used.

The relationship file contains four source-area mismatches carrying 22 people
in total. Published intersection coverage is at least 99.9610% for every source.

All 42 QA checks pass. A second complete run reused all five immutable artifacts
identically. Logical SHA-256 values are:

| Artifact | Logical SHA-256 |
|---|---|
| Atomic crosswalks | `eb9081b7f6b8259f4b54e94dee20f441f4031a7773557a07a671b54e95366d28` |
| Fixed-precinct results | `4e0e5afe8dfa22e6645f90aa0ede6821b1a1057656b0d1f86fccf2298ea5881a` |
| Senate results | `a25ce0081ba0e468d849b89aace346289063fd25687af206827ee2448a76fd04` |
| Precinct method comparison | `3554abec86ffa328f60d45b7502d336b81e5dc5ac3c473b291d1822675d77d3c` |
| Senate method comparison | `cdc1d60744784cbefab04b91ad443ebeca98e4aa6b5fc9ec91a673e01eab061a` |

Machine-readable evidence is under ignored `artifacts/poc012/`; derived data
remain ignored under `data/processed/statewide_2000/` pending a publication and
source-terms decision.

## Limits

- Area weights assume uniform within-block population and do not locate people
  within split blocks.
- The fixed precinct target is counterfactual for 2000 and is not the precinct
  geography used in that election.
- The 1991 Final plan applies to elections from 1992 through 2000;
  population/product-to-election pairing remains `POC019`.
- A population- or housing-informed historical support surface remains an open
  comparison, subject to vintage leakage and source terms.
