# Accepted statewide 2020 result

`POC010` passed on 2026-08-29. The saved command produces Pennsylvania's 2020
standard total population on the fixed 2021 LRC precinct target and the 2021
Final State Senate plan without a nearest-boundary assignment.

## Inputs and methods

The input manifest freezes the official Census 2020 Pennsylvania PL 94-171
summary file, LRC 2021 Release 1b Data Set 1 geography, the official 2021 Final
Senate block equivalency CSV, and the accepted `POC022` current-plan overlay.
It preserves product identity, retrieval or creation timestamp, reference and
effective vintage, URL, checksum, license/access note, CRS, schema, and
geographic and population universe.

The accepted precinct method is `lrc_published_split_v1`. Census parent-block
population is allocated through the LRC corrected fragments using published
fragment population shares. Nine zero-population split parents use fragment
area only to make their zero-population allocation rows total and valid.

The accepted Senate method is `fixed_precinct_senate_overlay_v3`. For the 2021
Final plan, all 9,178 fixed precincts are wholly contained by one Senate
district, so every overlay weight is exactly one. An independent route,
`lrc_senate_block_equivalency_v1`, aggregates published LRC fragment population
through the official block equivalency file.

## Proven results

- all 336,985 Census parent blocks are represented by 337,039 crosswalk rows;
- all 9,178 fixed precincts and all 67 counties are represented;
- every LRC parent-block population equals its Census PL value;
- every fixed-precinct result equals the published LRC precinct total;
- state and every county total conserve the Pennsylvania total of 13,002,700;
- the official Senate equivalency file has one row for every LRC fragment and
  covers all 50 districts;
- both Senate methods conserve 13,002,700 and agree exactly in every district;
- total absolute Senate-method delta is zero; and
- no nearest-boundary assignment is used.

The largest crosswalk weight-sum deviation is
`2.220446049250313e-16`, below the declared `1e-12` numerical tolerance.

## Reproducibility

Run:

```sh
.venv/bin/python -m census_pa_poc.statewide_2020 --root .
```

The successful verification run reused all five immutable Parquet artifacts
identically. Logical hashes are:

| Artifact | SHA-256 |
|---|---|
| block-to-fixed-precinct crosswalk | `7ce2b5360609767337f5066d5dd042486a2083b54b45067d8b9edfeb6f36ae7a` |
| fragment-to-Senate equivalency | `5463cc8509125e4d8c14d963beb25205f574b4e12ff18a11f1745323fa9a0013` |
| fixed-precinct population | `7468a05dd6ee9496451b434bea024f73618021c68dcc327ecf26816d24d8dbc7` |
| Senate population, both methods | `6946e23f237dc6f3eaeb4de8355a00572a0b3f1a40933db1f8a6536f55abaa39` |
| Senate-method comparison | `33af3d6b5f6e1e300f348ac370e5c9e63b2c3310ed5a4e2aee9872a6cd85f2f5` |

Machine-readable evidence is in `artifacts/poc010/`; generated data remains
ignored under `data/processed/statewide_2020/`.

## Scope limitation

This result is a geography/population product, not yet a single-election
feature selection. The 2021 Final plan applies to the 2022, 2024, and 2026
general elections. `POC019` remains responsible for explicit election/product
availability pairing.
