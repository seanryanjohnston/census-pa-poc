# Accepted statewide Census 1990 result

`POC013` passed on 2026-08-29. It proves that 1990 Census standard total
population can be allocated to the fixed 2021 LRC precinct target and the 1981
State Senate plan by a reproducible legacy-data path.

## Frozen inputs

| Input | Exact product / vintage | SHA-256 |
|---|---|---|
| Population | 1990 Census STF 1B Pennsylvania geographic-header archive, published in 1991 | `9821d1a7d10d2065661d7174695e10d5b3624651c2b7dbcf8b8ab3d4accfd6d4` |
| Source topology | 67 Census 2000 TIGER/Line county archives carrying 1990 and 2000 block codes | logical collection `559b219b8700c4b95d84fd64531463b798ec4d43945190ca44b3128b77ce2666` |
| Relationship validation | 67 official 1990-to-2000 tabulation-block relationship files | logical collection `2844c2604b2676068e858a0b234aa74f94ce25a3b7d3fab04715a7170676328f` |
| Intermediate geometry | 2010 TIGER/Line Census 2000 Pennsylvania tabulation blocks | `a5771874f846018ddf7d3761939a8e9cd3ecdf8d34364caa53e84630707c85dc` |
| Senate atomic target | Accepted `pa_senate_1981_plan_fixed_precinct_overlay_v3` | logical `a68f672233c092ea3b24de2d67c12c5be60c5ec13ed653f66bc4a2e27a3524c2` |

The manifest preserves a checksum, byte count, and URL for every file in both
67-file collections. The compact 300-character STF 1B geographic-header record
contains the block identifiers, `POP100`, `HU100`, land/water area, and internal
point needed for this proof. Summary level `100` yields 310,668 unique
Pennsylvania blocks, 11,881,643 people, and 4,938,140 housing units across all
67 counties. All population blocks have reconstructed geometry.

The Census documentation establishes a 1991 STF 1 release, but the exact
Pennsylvania release day was not established. The manifest and population
registry preserve that distinction rather than substituting the retrieval date.

## Compared methods

`direct_atomic_area_1990_v1` reconstructs 1990 block polygons from Census 2000
TIGER/Line CompleteChain, shape-coordinate, polygon, landmark, geographic-code,
and polygon-geographic-code records. It directly intersects those blocks with:

`fixed 2021 LRC precinct ∩ 1981 State Senate district`

in EPSG:5070 and normalizes weights over covered area.

`relationship_tiger_face_area_1990_v1` reconstructs the Census 2000 TIGER
faces once. The same faces carry both 1990 and 2000 block codes, so their
EPSG:5070 areas create a same-topology 1990-to-2000 crosswalk. The method then
composes those weights with a geometry-only Census 2000 block-to-atomic-target
area bridge. It does not use 2000 or later population.

The official relationship files publish the valid 1990/2000 block pairs and
part flags, but no land-area or population weights. The face-derived pair set
matches the published pair set exactly: zero derived-only and zero
published-only pairs. Under `PD020`, the face-area relationship route is the
accepted baseline and the direct route is a diagnostic.

Both methods are geographic area estimates, not population-weighted truth.

## Results and QA

- All 310,668 population blocks, 9,178 fixed precincts, 67 source counties, and
  50 districts of the 1981 Senate plan are accounted for.
- The TIGER parser reconstructs 480,773 faces. Of those, 471,257 support STF
  population blocks.
- The official relationship files contain 394,566 rows, 316,159 source block
  codes, and all 322,424 Census 2000 target blocks. The STF population universe
  uses 386,723 relationship rows.
- Same-topology source area coverage ranges from
  `0.9999999999999908` to `1.0000000000000095`.
- The relationship composition produces 509,414 allocation rows, covers every
  source block, has no missing atomic target, and has a maximum normalized
  weight-sum difference of `2.220446049250313e-16`.
- Both routes conserve 11,881,643 people at state and source-county levels.
- Neither route uses nearest-boundary assignment.
- The methods differ in all 9,178 precincts by 333,363.830 total absolute
  persons; the largest precinct difference is 602.199.
- All 50 Senate districts differ by 14,085.678 total absolute persons; the
  largest district difference is 3,118.676.

The direct route emits 460,883 allocation rows and assigns 310,666 source
blocks. Its two uncovered blocks have zero population. Fourteen source internal
points lie outside the later atomic target and carry four people in total. More
materially, 192 source blocks have less than 99% direct geometry coverage; 109
are populated and contain 5,013 people. Applying each source's uncovered area
share to its population gives a 275.503-person equal-area diagnostic, with as
much as 51.016 for one source. This is not an observed population location. It
shows that spatial realignment between the reconstructed historical linework
and the later atomic target is too large for the direct route to be the
baseline.

Two TIGER internal points lie exactly on boundaries shared by three small
faces. The parser resolves those cases deterministically using the official
chain-to-polygon side references and ring orientation; the exception count is
preserved in QA.

All 48 QA checks pass. A second complete run reused all five immutable
artifacts identically. Logical SHA-256 values are:

| Artifact | Logical SHA-256 |
|---|---|
| Atomic crosswalks | `831e45e052dac3cda4a5b6d67648a72a3dc4d6c00c4b2ee4238e89fc1a9bcdf5` |
| Fixed-precinct results | `d899e3a1a5b1c6df8a14b889959f1e758c498dfa39e09e4a93e7fc6e78c053bd` |
| Senate results | `210632991621193255e3af8d901b43764d2559c51b3c2b21d13906e655c47b1d` |
| Precinct method comparison | `ed514eee02f963cfa3673a3e48afe73062a51ed524cbd916fb79519df1cc1b71` |
| Senate method comparison | `f0643678c3528814eac115389329e80fc2c21a3b2ac5aba90c0ea42506891d38` |

Machine-readable evidence is under ignored `artifacts/poc013/`; derived data
remain ignored under `data/processed/statewide_1990/` pending a publication and
source-terms decision.

## Limits

- Area weights assume uniform within-face and within-block population; they do
  not locate people inside split blocks.
- The fixed precinct target is counterfactual for 1990 and is not the precinct
  geography used in that election.
- The 1981 Senate plan is the applicable election geography for 1990, but
  population-product availability relative to that election remains `POC019`.
- The exact Pennsylvania STF 1B release day remains unresolved and must stay
  explicit in the later availability mapping.
- A population- or housing-informed historical support surface remains an open
  comparison, subject to vintage leakage and source terms.
