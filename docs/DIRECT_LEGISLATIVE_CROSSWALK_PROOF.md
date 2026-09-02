# Direct legislative crosswalk proof

`POC028` passed on 2026-08-30. It establishes the active baseline for direct
Census/ACS-to-legislative-plan work and does not use a precinct target or
precinct crosswalk.

## Proven contract

The proof assigns Pennsylvania LRC corrected 2020 block fragments directly to
the official 2021 Final State House and State Senate plans. It preserves two
separate contracts:

1. `lrc_2021_final_block_equivalency_v1` assigns each atomic fragment to a
   chamber, plan, and district. It is metric-independent.
2. `lrc_fragment_p001_direct_legislative_v1` converts standard Census parent
   blocks into metric-specific district weights for `P0010001`. It records the
   weighting universe and fallback and cannot be relabeled for another metric.

Official LRC block equivalencies are the accepted assignments. Representative
points of the corrected fragment geometries against the official plan polygons
provide an independent diagnostic; no geometry assignment disagrees with the
published assignment.

## Frozen inputs

| Input | Reference/effective vintage | SHA-256 |
|---|---|---|
| 2020 Census Pennsylvania PL 94-171 | 2020-04-01 | `2d33a7dab29c8dd5692bbde203d253e06eebbc44fcbaa96b1caa958d454026ae` |
| LRC Data Release 1b corrected geography | 2020 / 2021-10-05 | `14187001c627c6a16bf967415059408c4ef7007d366fd9105b5be30763250e3b` |
| 2021 Final House SHAPE | 2022–2026 elections | `11960e83f61416276d46205785adaf5dee1995ab21f05a1b5113b649e6c329f6` |
| 2021 Final House block equivalency | 2022–2026 elections | `17e11f451196cf0b6253c01386592426f867949b76b189c084f04bbf24a92e15` |
| 2021 Final Senate SHAPE | 2022–2026 elections | `4dcfd5f111ddf7de58484585205ecc5b01631e4a1b20c0745889f741ec137e14` |
| 2021 Final Senate block equivalency | 2022–2026 elections | `ff7a79d2da3df2094bebe9ab0f19d91bc2bfec8537f8d07a034b6b0d1b3dfbef` |

The canonical manifest at `mappings/source_manifests/direct_2020_v1.json` also
preserves producer, exact product, URL, retrieval timestamp, schema, CRS,
license note, and geographic/population universe. Raw inputs remain ignored
pending a publication and redistribution decision.

## Statewide evidence

| Check | House | Senate |
|---|---:|---:|
| Plan districts | 203 | 50 |
| Atomic assignment rows | 337,039 | 337,039 |
| Census parent blocks covered | 336,985 | 336,985 |
| Parent/district weight rows | 336,986 | 336,985 |
| Parent blocks split across districts | 1 | 0 |
| Published/geometry mismatches | 0 | 0 |
| Allocated population | 13,002,700 | 13,002,700 |
| Difference from direct published-fragment total | 0 | 0 |

The one House-split parent block is `421010257002008`. Its populated fragment
has 40 residents in District 194 and its zero-population fragment is in
District 200. The parent weights therefore use the published fragment
`P0010001` support. No statewide row needed the defined zero-support
atomic-area fallback.

The four accepted logical hashes are:

| Artifact | Rows | Logical SHA-256 |
|---|---:|---|
| Atomic assignments | 674,078 | `ea511cf343023c786fe5d6b71ebf94b5da5300f186eafb16f00e8cdb3ec6e34c` |
| `P0010001` parent/district crosswalk | 673,971 | `f247ea8a84256d0d96e44f5319959a97776848206b7948cf7cd3eee661429d8f` |
| District results | 253 | `17e85124f1b2d2c56dbee83b7b05392cf2a818a52fbfa2299d6e468687d0836f` |
| Published-method comparison | 253 | `9d414b06a012892bb14b78eb4a693cc52cbb7374166670c3cbdc52305c9d4526` |

A second statewide run reported `reused_identical` for all four products. The
repository-wide verification also passed Ruff and all 101 tests.

## Boundary of the proof

This result proves only standard 2020 Census total population on the 2021 Final
House and Senate plans. It does not prove that published fragment population is
a valid support surface for another metric. `POC029` separately versioned and
validated the historical decennial and ACS combinations without a precinct
dependency. The superseded precinct route is recoverable from Git history.

## Reproduce

```bash
.venv/bin/python -m census_pa_poc.direct_legislative --root .
.venv/bin/ruff check .
.venv/bin/pytest -q
```
