# Accepted statewide 2010 result

`POC011` passed on 2026-08-29. It proves that 2010 standard total population can
be allocated to the fixed 2021 LRC precinct target and the 2001 Final State
Senate plan by two explicit, reproducible area methods.

## Frozen inputs

| Input | Exact product / vintage | SHA-256 |
|---|---|---|
| Population | Census 2010 Pennsylvania PL 94-171 Summary File, released 2011-03-09 | `3cf2460ea17d1be087d9b12700e45962b164f6233f8c1071ddc67ab55392951a` |
| Source geometry | 2010 TIGER/Line Pennsylvania tabulation blocks | `fc33d93eb53e71b0d61c3aa35d496a8a8b8d192933d68ebef206ccbaa9e19152` |
| Relationship aid | Official 2010 block to 2020 block relationship file | `6e8ac323b98bf7259dac59ae7000c14fa72ce38207f77648d08645bbea29a323` |
| Fixed target support | 2021-10-05 LRC Data Release 1b geography | `14187001c627c6a16bf967415059408c4ef7007d366fd9105b5be30763250e3b` |
| Senate atomic target | Accepted `pa_senate_2001_final_fixed_precinct_overlay_v3` | logical SHA-256 `4e28ffbafc81599dea78f06f15944c1895e1cd459460021cd2348c3909f85aeb` |

The population parser follows the official fixed-width 2010 geographic header
and comma-delimited File 01 layouts. It finds 421,545 unique blocks and exactly
12,702,379 people, matching the official Pennsylvania total.

## Compared methods

`direct_atomic_area_2010_v1` intersects each 2010 block directly with:

`fixed 2021 LRC precinct ∩ 2001 Final Senate district`

in EPSG:5070 and normalizes weights over covered area.

`relationship_atomic_area_2010_v1` first normalizes the official 2010→2020
land-plus-water intersection areas, then composes those weights with a
geometry-only 2020 corrected-fragment-to-atomic-target area crosswalk. It does
not use 2020 population as a historical support surface. Under `PD018`, this is
the accepted 2010 POC baseline because it preserves the official inter-vintage
topology; direct overlay remains the independent diagnostic.

Both methods are geographic area estimates, not population-weighted truth.

## Results and QA

- 421,545 source blocks, 9,178 fixed precincts, 67 source counties, and 50
  Senate districts are accounted for.
- Both routes conserve 12,702,379 people at the state and source-county levels.
- The direct route emits 606,696 assigned atomic rows plus four typed
  zero-population uncovered exceptions.
- The relationship route begins with 464,515 official rows covering 421,542
  source blocks, including 32,981 sources related to multiple 2020 blocks. Its
  three absent source blocks all have zero population.
- No relationship row lacks 2020 atomic-target support.
- Neither route uses nearest-boundary assignment.
- The methods differ in 6,987 precincts by 11,852.091 total absolute persons;
  the largest precinct delta is 399.003.
- All 50 Senate districts differ by 1,097.571 total absolute persons; the
  largest district delta is 91.818.

The direct geometry audit found 16 representative points outside the later
atomic target. Fifteen are zero-population blocks. Block `421150320001013`
carries 11 people and has only 54.4% direct geometric coverage, but the official
relationship file maps its complete published 2010 area to a Pennsylvania 2020
block. The direct method therefore remains a covered-area diagnostic; the
published relationship resolves the populated linework exception without a
nearest assignment.

The relationship file also omits three zero-population Northampton County
blocks and contains eight source-area mismatches. Seven mismatches have zero
population; the eighth carries 27 people and retains 99.8% published area
coverage. Per-source normalization is explicit in the crosswalk.

All 39 QA checks pass. A second complete run reused all five accepted immutable
artifacts identically. Logical SHA-256 values are:

| Artifact | Logical SHA-256 |
|---|---|
| Atomic crosswalks | `a62c09b9bed84253cfa22360aa59d91c95f066675746c134e7be16bd886d5318` |
| Fixed-precinct results | `03433f05f3e6a2701f2341b917813e462c4041349561238ecf37503b49e32826` |
| Senate results | `fe0c28934d595764350eaec3a4a4b0cf2b984268826ccf86bed1ae825e7b1a10` |
| Precinct method comparison | `545405c892b9383cee09920a97574ef12b1cd6f550fa88add3d70b73b9ae755d` |
| Senate method comparison | `408b37b159e07622be27396756e97258209988e5868368f46d8e26b9fb4c1f76` |

Machine-readable evidence is under ignored `artifacts/poc011/`; derived data
remain ignored under `data/processed/statewide_2010/` pending a publication and
source-terms decision.

## Limits

- Area weights assume uniform within-block population and do not locate people
  within split blocks.
- The fixed precinct target is counterfactual for 2010 and is not the precinct
  geography used in that election.
- The 2001 Final plan is the applicable period plan for the 2002–2012 election
  cycles; population/product-to-election pairing remains `POC019`.
- A population- or housing-informed historical support surface remains an open
  comparison, subject to vintage leakage and source terms.
