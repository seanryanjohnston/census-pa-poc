# Accepted Philadelphia 2020 proof

Accepted 2026-08-07 for `POC006`–`POC007`.

## Outcome

The saved Python pipeline qualifies an official City of Philadelphia Political
Divisions candidate and runs three 2020 Census block-to-2021 LRC precinct
methods for Philadelphia County. It proves:

- the City candidate contains 1,703 unique four-character division IDs across
  all 66 wards, valid non-empty EPSG:3857 polygons, and no duplicate IDs;
- the frozen City GeoJSON has SHA-256
  `1b847f76069e6dd8c0185e59c20e337fa4261aea7739694f24dffc80fcf442a6`;
- the City service's data-edit timestamp is `2025-06-25T07:54:19Z`, its item
  modification timestamp is `2026-08-03T11:27:32Z`, and the exact snapshot was
  retrieved `2026-08-07T23:19:29.634849Z`;
- the City source does not publish an election-effective boundary date and is
  therefore a qualified current candidate, not a frozen November 2026 target;
- one City attribute inconsistency is preserved: `objectid=613` has canonical
  `division_num=1301` but `short_div_num=13`;
- after normalizing LRC `VTDST20` to four digits, the City and 2021 LRC layers
  share 1,652 identifiers, with 51 City-only and 51 LRC-only identifiers;
- 17,554 original Philadelphia Census blocks match the PL 94-171 population
  table and the normalized LRC corrected-block parents exactly;
- LRC replaces 13 source blocks with 26 `A`/`B` fragments assigned across two
  precincts each; seven split blocks contain population and six have zero
  population;
- the 13 split blocks contain 931 of Philadelphia's 1,603,797 people, or
  0.0580% of county population;
- all three crosswalks cover every source and all 1,703 targets, have finite
  weights in `[0, 1]`, sum to one per source, and conserve county population;
- the published corrected-fragment allocation reproduces every LRC precinct
  total exactly;
- representative-point allocation changes eight precinct totals, with 162
  total absolute persons and a maximum absolute precinct delta of 34; and
- equal-area overlay changes 12 precinct totals, with 80.904 total absolute
  persons and a maximum absolute precinct delta of 12.694.

The equal-area overlay uses EPSG:2272. Intersections no larger than `5e-6` of a
source block's area are typed as topology/projection slivers, dropped, and the
retained intersections are renormalized. This rule finds the same 13 split
source blocks as the LRC corrected fragments.

## Accepted method decision

For 2020 Census population targeting LRC Release 1b, use
`lrc_published_split_v1`. Positive-population fragments use the LRC published
fragment counts; zero-population fragments use area weights only to keep the
crosswalk valid, without affecting population totals.

Use `representative_point_v1` only as a whole-block fallback/comparison where a
published correction is unavailable. Keep `area_overlay_v1` as a geometry
diagnostic rather than a population model. This decision does not select a
weighting method for post-2021, historical, or ACS targets without published
split populations.

## Saved evidence

Tracked implementation:

- `src/census_pa_poc/philadelphia.py`
- `src/census_pa_poc/crosswalk.py`
- `src/census_pa_poc/sources.py`
- `src/census_pa_poc/validation.py`
- `tests/`

Ignored local evidence:

- `artifacts/poc006_poc007/input_manifest.json`
- `artifacts/poc006_poc007/source_gate.json`
- `artifacts/poc006_poc007/source_profile.json`
- `artifacts/poc006_poc007/qa_results.json`
- `artifacts/poc006_poc007/report.md`
- `data/processed/philadelphia/crosswalk_*.parquet`
- `data/processed/philadelphia/precinct_population.{parquet,csv}`
- `data/processed/philadelphia/method_comparison.{parquet,csv}`
- `data/processed/philadelphia/split_block_comparison.{parquet,csv}`

The logical crosswalk hashes are:

- `lrc_published_split_v1`:
  `f54f80763914291849906647aae3e9028f1ea9a917d8722175050c8890465e2c`
- `representative_point_v1`:
  `87769bacbd34dff1b1932d50da0c5973b0c98401913fb79fd3cdae4a818d8119`
- `area_overlay_v1`:
  `c5c407763a3d0c0c85f953712890376a2d7f9d1dd5257c09b87251c1ee2cfa26`

An identical rerun reported `reused_identical` for all three Philadelphia
crosswalks. Cumberland's two accepted crosswalks also remained identical. The
focused suite reports 13 passing tests.

## Source authority and terms

- City catalog and terms:
  https://opendataphilly.org/datasets/political-ward-divisions/
- Philadelphia City Commissioners' current 1,703-division statement:
  https://votes.phila.gov/resources-data/election-resources/political-maps/
- City ArcGIS feature service item `160a3665943d4864806d7b1399029a04` is
  public; its license text provides the data as-is, describes boundaries as
  self-reported, and disclaims warranties.
- LRC Release 1b remains a public download with redistribution terms not
  stated; derived publication still requires review.

## Limitation and next gate

The City layer is authoritative enough for source qualification and post-2021
change research, but its missing election-effective date prevents calling it
the November 3, 2026 snapshot. `POC008` must freeze that statewide target and
`POC009` must reconcile it to the 2021 LRC baseline before a statewide 2020-to-
2026 result is claimed.
