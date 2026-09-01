# Trusted Census county and state reconciliation

`POC027` adds an independent county/state audit to every accepted population
allocation and exposes it in the local explorer. It does not change any
crosswalk or allocated estimate.

## Two distinct benchmarks

The comparison deliberately preserves two Census values:

1. `official_source_unit_sum` is the exact sum of the official Census blocks
   (decennial) or block groups (ACS) that entered the crosswalk, grouped by
   source county and Pennsylvania.
2. `published_aggregate` is a directly published ACS `B01003` county or state
   record loaded independently from the accepted Census product. It is never
   reconstructed from the block-group sum.

This distinction tests both the allocation's conservation and, where possible,
whether the lower-level Census records agree with Census's own aggregate row.
The controlled total-population aggregate uses a negative Census MOE sentinel;
the loader converts it to a typed `controlled_estimate_no_meaningful_moe`
status rather than presenting it as a real uncertainty value.

## Reproduce

```bash
.venv/bin/python -m census_pa_poc.source_reconciliation --root .
```

The command reads accepted `POC016` fixed-precinct results and exact raw Census
products, then creates or proves identical:

- `data/processed/poc027/population_trusted_reconciliation_v1.parquet`;
- `artifacts/poc027/input_manifest.json`;
- `artifacts/poc027/qa_results.json`; and
- `artifacts/poc027/report.md`.

The Parquet has 2,652 rows: 39 unique population-product/Senate-plan partitions
times 68 geographies (Pennsylvania plus 67 counties). It retains provenance,
source-unit counts, both benchmarks, all signed deltas, a 0.001-person
tolerance, and typed statuses.

## Accepted findings

- All 39 allocated Pennsylvania totals match the official source-unit sums
  exactly.
- Every partition has all 67 county comparisons. County deltas balance back to
  the exact state total within floating-point precision.
- Direct published ACS aggregates are present in the accepted local table-based
  products for 2021–2024: 4 products × 68 geographies = 272 rows. Every one
  matches its official block-group sum exactly.
- The accepted 2009–2020 sequence archives are Census's tract/block-group-only
  extracts and do not carry state/county `B01003` cells. Those 816 aggregate
  rows use `not_present_in_accepted_tract_block_group_extract`; they are not
  silently filled from the source-unit sum.
- The largest county allocation delta is `+217.827576` people for Lehigh in the
  1990 product; Northampton carries the principal offset. This is evidence of
  older source geography being allocated into county-labeled units of the fixed
  2021 target, not loss of Pennsylvania population.
- The 2020 Census and ACS 2020–2024 products match every county exactly. Older
  products retain their measured county shifts.

Under `PD027`, exact statewide conservation is a strict gate. County differences
are audit evidence: they must be complete, signed, and balance statewide, but
are not forced to zero. Changing this behavior would require a new versioned
crosswalk or county-constrained allocation method, not a display adjustment.

## Explorer behavior

The county control now applies to both the precinct view and the reconciliation
panel. Selecting one county displays that county and Pennsylvania side by side;
selecting all counties displays all 68 rows. A warning appears when county
mapping differs while Pennsylvania remains conserved. The panel continues to
show typed unavailability for the 1990 election because no product was
available by its election-day cutoff.
