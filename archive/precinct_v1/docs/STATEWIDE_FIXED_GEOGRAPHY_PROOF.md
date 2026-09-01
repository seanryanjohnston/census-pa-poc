# Accepted statewide fixed-geography proof

Accepted 2026-08-09 for `POC021`.

## Claim proved

The checksum-frozen 2021 LRC Data Set 1 geography provides a complete fixed
precinct target for the entire 2020 Census Pennsylvania block universe without
nearest-boundary assignment.

The direct assignment unit is each published LRC corrected fragment. Each
fragment maps with weight 1 to its published precinct key. Parent Census blocks
that the LRC split remain explicit allocation groups rather than being forced
into one precinct.

## Inputs

| Source | SHA-256 |
|---|---|
| 2020 PL 94-171 TIGER/Line Pennsylvania tabulation blocks | `f2afff2b2a84170a3cf16bca52137562828d2811133419f22981ec790b2fbebb` |
| 2021-10-05 LRC Data Release No. 1b Data Set 1 geography | `14187001c627c6a16bf967415059408c4ef7007d366fd9105b5be30763250e3b` |

The local input manifest preserves producer, product, retrieval timestamp,
reference/effective vintage, URL, checksum, terms, CRS, schema, and universe.

## Accepted results

| Check | Result |
|---|---:|
| Unique Census parent blocks | 336,985 |
| LRC corrected fragments | 337,039 |
| Unique LRC parent blocks | 336,985 |
| Census-only / LRC-only parent IDs | 0 / 0 |
| Fixed precinct polygons / referenced target IDs | 9,178 / 9,178 |
| Target IDs without polygons / polygons without targets | 0 / 0 |
| Parent blocks assigned to one precinct | 336,932 |
| Parent blocks split across two precincts | 52 |
| Parent blocks split across three precincts | 1 |
| Corrected fragments belonging to split parents | 107 |
| Null required assignment fields | 0 |
| Null, empty, or invalid fragment/precinct geometries | 0 |
| Assigned representative points outside target | 0 |
| Nearest-boundary assignments | 0 |

Strict polygon coverage identified 12,383 numerical/linework slivers. Measured
after projection to EPSG:5070, their maximum outside area is
`0.09548947827464742` square meters and their statewide total is
`0.258205925954268` square meters. Both are below the declared tolerances of
one square meter per exception and ten square meters statewide. These are
typed precision exceptions, not materially uncovered geography.

## Reproducibility

A second full run reused all three immutable Parquet artifacts with identical
logical hashes:

- fragment assignments:
  `9660cd81d7d567f91b8d6cc1a9cf88a48acfb63cd9b63040674e0d8f7f837484`;
- split-parent fragments:
  `f0a7bb4bfaaff9d39bd181d48c73b88df95bc934ee987f6d2f51c51f031101ec`;
- precision exceptions:
  `309f9622d2d0d1f2c12f42e20fb84de74e2f43d14f74579cb4a54d0ee93e71e3`.

Machine-readable local evidence is under `artifacts/poc021/`; ignored processed
tables are under `data/processed/statewide_fixed_geography/`. Run with:

```bash
.venv/bin/python -m census_pa_poc.fixed_geography --root .
```

## Limits

This proves the fixed 2021 LRC target and its published 2020 block-fragment
assignments. It does not prove allocation from older blocks or ACS block groups,
the State Senate overlays, or any actual historical/2026 precinct snapshot.
