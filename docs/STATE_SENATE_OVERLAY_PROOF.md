# Accepted State Senate overlay proof

Accepted 2026-08-09 for `POC022`.

## Claim proved

The five official Pennsylvania LRC State Senate plans needed for 1990–2026 can
be reproducibly overlaid with the fixed 2021 LRC precinct target without
assuming whole-precinct containment and without nearest-boundary assignment.

Every plan contains 50 uniquely numbered districts in EPSG:4269. The accepted
overlay uses EPSG:5070 and method `fixed_precinct_senate_overlay_v3`. Every
allocation row preserves plan, fixed precinct, Senate district, raw and final
area, area weight, topology normalization, method, assignment status, and
geometry.

## Source gate

| Plan source | Elections | SHA-256 |
|---|---|---|
| 1981 plan | 1990 | `f12d88b92ad5c63ee00038ca92d294df1d1e9eee6091bcc0889384148b6f0388` |
| 1991 Final | 1992–2000 | `f7dd6a06d3ce24aafa5addce2fddc9772664fa6358cd6f85cc6e00afc9a87e6f` |
| 2001 Final | 2002–2012 | `01319695d77d9ad1d787549332e8d3f236cae9510411a9cc7d9e538c500b17d4` |
| 2012 Revised Final | 2014–2020 | `801da910909aea05be2201b755fcaa0fd3f890d9b438ace641250f4037105b04` |
| 2021 Final | 2022–2026 | `4dcfd5f111ddf7de58484585205ecc5b01631e4a1b20c0745889f741ec137e14` |

The 1991 source has one District 48 ring self-intersection. The recorded
`make_valid` repair produces a valid MultiPolygon. The other SHAPE inputs are
valid as published.

The official 2012 SHAPE contains a 45,622.590 m² District 1/8 overlap. The
official KML independently reproduces it at 45,622.592 m² (KML SHA-256
`a74c005840f2a059841039be1e33a01391258730fd5006e30c26799a6129af51`).
The legal plan description confirms Ward 40 Division 49 belongs to District 8
and Division 30 is a genuine block-level split, supporting precinct-local
overlap normalization rather than a whole-precinct label.

## Accepted normalization

`PD017` records the complete method:

- discard district intersections of at most one square meter as numerical
  slivers;
- remove material duplicated district overlap from the district with less raw
  intersection area inside that fixed precinct;
- fill historical plan/state-line gaps only when the precinct otherwise
  intersects one material district;
- leave multi-district gaps unassigned as typed exceptions only when no
  uncovered LRC fragment representative point or population falls in them;
- normalize area weights over the covered portion; and
- never use nearest-boundary assignment.

The weights describe geographic coverage, not population truth. Population
allocation must still operate on the atomic source-unit/precinct/Senate
intersection or use an independently validated population-informed route.

## Accepted results

| Plan | Rows | Fixed precincts | Split fixed precincts | Overlap removed m² | Single-district gaps filled m² | Typed multi-district gap precincts / population |
|---|---:|---:|---:|---:|---:|---:|
| 1981 | 10,221 | 9,178 | 997 | 0 | 3,785,553.581 | 5 / 0 |
| 1991 Final | 10,279 | 9,178 | 1,045 | 0 | 3,382,084.480 | 8 / 0 |
| 2001 Final | 10,358 | 9,178 | 1,126 | 0 | 3,190,361.967 | 9 / 0 |
| 2012 Revised Final | 10,278 | 9,178 | 1,055 | 45,622.591 | 3,204,678.673 | 8 / 0 |
| 2021 Final | 9,178 | 9,178 | 0 | 0 | 0.066 | 0 / 0 |

For every plan, all 9,178 fixed precincts and all 50 Senate districts are
supported, weights are finite and sum to one within `1e-9`, geometries are
valid, and nearest-assignment count is zero.

## Reproducibility

A second statewide `v3` run reused all five immutable GeoParquet artifacts with
identical logical hashes:

- 1981: `a68f672233c092ea3b24de2d67c12c5be60c5ec13ed653f66bc4a2e27a3524c2`;
- 1991: `d60a3584ff2a457ef99736607ec656f2d376aed5a7000a2e30a84c82e5477d26`;
- 2001: `4e28ffbafc81599dea78f06f15944c1895e1cd459460021cd2348c3909f85aeb`;
- 2012: `97a0c5c2f382174363de8ca7506dbe73f27f73901b4c495f2a2cf1ee4a74bc2b`;
- 2021: `193cd389d11dab8976124f0b2d8f0f45fc7ef6519dc1183625567d9a13ba3a7d`.

Machine-readable local evidence is under `artifacts/poc022/`; ignored outputs
are under `data/processed/senate_overlays/`. Run the source and overlay gates:

```bash
.venv/bin/python -m census_pa_poc.senate_plans --root .
.venv/bin/python -m census_pa_poc.senate_overlay --root .
```

## Limits

This proves geographic plan overlays and explicit topology normalization. It
does not yet allocate 2020 or historical population to Senate districts, and
its area weights must not be represented as population weights.
