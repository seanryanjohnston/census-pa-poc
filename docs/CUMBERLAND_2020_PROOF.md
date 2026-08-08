# Accepted Cumberland 2020 proof

Accepted 2026-08-07 for `POC001`–`POC005`.

## Outcome

The saved Python pipeline loads checksum-verified copies of the official 2020
Census block geometry and PL 94-171 population products plus Pennsylvania LRC
Release 1b geography. For Cumberland County it proves:

- 5,609 unique Census geometry blocks, PL population blocks, and LRC blocks
  have exactly matching `GEOID20` keys;
- the block, LRC block, and LRC precinct layers use EPSG:4269;
- all 5,609 LRC block rows have non-null `STATEFP20`, `COUNTYFP20`, `VTD`,
  `VTDST20`, and `GEOID20` values;
- `VTD` and `VTDST20` agree on every Cumberland block;
- `STATEFP20 + COUNTYFP20 + VTDST20` yields one published target key per block,
  covering all 119 LRC precincts with no duplicates or split block IDs;
- the published direct crosswalk and independently computed polygon
  representative-point crosswalk assign all 5,609 blocks identically;
- both methods support all 119 targets and conserve exactly 259,469 people; and
- both methods reproduce every LRC precinct `P0010001` total exactly.

No invalid or empty source/target geometries were observed. Every source
representative point was strictly within exactly one target; no boundary
tie-break was needed in the real Cumberland run.

## Saved evidence

Tracked implementation:

- `src/census_pa_poc/sources.py`
- `src/census_pa_poc/crosswalk.py`
- `src/census_pa_poc/validation.py`
- `src/census_pa_poc/cumberland.py`
- `tests/`

Ignored local evidence:

- `artifacts/poc001_poc005/input_manifest.json`
- `artifacts/poc001_poc005/source_gate.json`
- `artifacts/poc001_poc005/lrc_block_profile.json`
- `artifacts/poc001_poc005/qa_results.json`
- `artifacts/poc001_poc005/report.md`
- `data/processed/cumberland/crosswalk_lrc_direct_v1.parquet`
- `data/processed/cumberland/crosswalk_representative_point_v1.parquet`
- `data/processed/cumberland/precinct_population.{parquet,csv}`
- `data/processed/cumberland/method_comparison.{parquet,csv}`

The logical crosswalk hashes are:

- `lrc_direct_v1`:
  `80ec7c27ce252058032d333d609cc6be93027f574ca7b0693d8fe086d3ce983f`
- `representative_point_v1`:
  `017e0c17fbdcdc0b93cb0e4668afc7bb7a0d8cba0d31e5e79daae96e688aba25`

An identical rerun reported `reused_identical` for both versioned crosswalks.
The focused suite reports nine passing tests.

## Limitation and next gate

Cumberland is a clean mechanics pilot. Agreement here does not prove how to
handle split blocks, overlapping/ambiguous targets, operational precinct
changes after 2021, or statewide coverage. Philadelphia is the accepted
complex-county pilot under `PD012` and subsequently passed `POC006`–`POC007`;
its accepted evidence is in `docs/PHILADELPHIA_2020_PROOF.md`. A statewide run
still waits on freezing and reconciling the election-effective 2026 target.
