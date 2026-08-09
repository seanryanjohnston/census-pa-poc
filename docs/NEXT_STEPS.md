# Next steps and blockers

Updated 2026-08-07.

## Finding

`POC006`–`POC007` pass for Philadelphia. The official City Political Divisions
candidate has 1,703 unique division IDs across all 66 wards, valid EPSG:3857
polygons, a fixed retrieval checksum, and public City terms. It is a mutable
current layer without a published election-effective date, so it is not yet the
November 3, 2026 target. Compared with 2021 LRC identifiers, 1,652 are common
and 51 occur only in each snapshot after normalizing to four digits.

Philadelphia contains 13 LRC corrected split Census blocks covering 931 people.
The versioned published corrected-fragment crosswalk reconciles exactly to all
1,703 LRC precinct totals and conserves 1,603,797 people. Representative-point
assignment changes eight precinct totals by 162 total absolute persons; an
equal-area overlay changes 12 by 80.904. `PD013` therefore selects the published
LRC corrected-fragment route for the 2020-to-2021 LRC baseline. Equal-area
weights remain diagnostic, not population truth.

`POC008` is now in progress with a validated 67-county resolution ledger. The
ledger currently contains two checksum-frozen candidates (Delaware and
Philadelphia) and 65
explicitly unreviewed counties; it is structurally valid but deliberately not
reported as a frozen statewide snapshot. Pennsylvania assigns election
administration to its 67 county boards of elections, so county resolutions are
the authoritative path when no election-effective statewide product exists.

The Pennsylvania DEP eMapPA Voting Districts layer was reviewed and rejected as
the 2026 shortcut. Its 9,530 feature parts collapse to 9,406 unique county/VTD
keys, it publishes neither election-effective date nor lineage, and its keys
match the 2010 VTD benchmark materially more closely than the 2020 benchmark.
The official 9,178-row 2020 Census VTD file is now cataloged only as a historical
benchmark, not as a current target.

Delaware County's official 2026 consolidation packet is also frozen. Its Board
of Elections enacted a net reduction of 45 precincts, from 428 to 383, for the
2026 primary and later elections. The packet establishes the change and maps
the affected precincts, but a complete machine-readable boundary snapshot and
legislative assignments remain unresolved, so the county is still a candidate.

## What follows

1. `POC008`: inventory authoritative county/state sources and freeze the actual
   November 3, 2026 general-election precinct snapshot with effective/as-of
   dates, checksums, legislative assignments, reviewed gaps, and a cutoff.
   Work county-by-county in `mappings/precinct_sources_2026.csv`; only change a
   row to `qualified` after all enforced gates pass.
2. `POC018`: inventory every earlier even-year general-election snapshot from
   1990 through 2024, using the Philadelphia historical archive as one research
   lead but requiring cycle-specific provenance and unchanged-boundary evidence.
3. `POC014`: inventory every usable ACS/mid-decade product, exact period,
   geography, estimate/MOE variable, release date, and acquisition manifest.
4. After `POC008`, run `POC009` to reconcile the 2021 LRC baseline to the frozen
   2026 target. The 51 Philadelphia identifier changes are an immediate test
   case, not a presumed one-to-one rename list.
5. Only after the target reconciliation, run statewide 2020 allocation and
   advance historical decennial and ACS method families.

## Blockers

- The 2026 statewide result is blocked on freezing the actual November 3, 2026
  precinct snapshot. Neither the 2021 LRC file nor the current Philadelphia
  layer may be relabeled as 2026.
- The current Philadelphia service does not publish an election-effective date.
  Its `2025-06-25` data-edit timestamp and `2026-08-03` item-modified timestamp
  are provenance, not proof of election vintage.
- Targets without LRC-published corrected fragment populations still require a
  tested population-informed split method; equal-area allocation is only a
  diagnostic baseline.
- Historical results are blocked on sourcing the precinct snapshot used for
  each even-year general election, or evidence that a snapshot was unchanged.
- Mid-decade allocation is blocked on completing the product inventory and
  choosing a tested block-group method that preserves estimates and margins of
  error separately.
- External publication remains blocked pending review of source redistribution
  terms, especially for Pennsylvania LRC-derived artifacts.

No owner decision currently blocks `POC008`, `POC014`, or `POC018`. The POC
directory is still not a Git repository, so its saved code and notes are not
committed or versioned outside the immutable local artifacts.
