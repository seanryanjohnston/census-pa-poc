# Accepted population/election pairing execution

`POC016` passed on 2026-08-29. The run executes every population product that
`POC019` classifies as available by an election's general-election-day cutoff,
on the fixed 2021 LRC precinct target and the official Senate plan applicable to
that election.

## Accepted scope

- The 380-row availability matrix contains 114 eligible product/election
  pairings and 266 post-cutoff pairings.
- The 114 eligible pairings reduce to 39 unique population-product/Senate-plan
  allocations. Repeated election rows index those immutable partitions; an old
  population product is recomputed for each distinct period Senate plan rather
  than relabeled.
- The tracked execution manifest contains 115 rows: all 114 executed pairings
  plus one explicit no-product row for the November 6, 1990 election.
- Every unique partition contains all 9,178 fixed precincts and all 50 Senate
  districts. No nearest assignment is used.

The execution index is
`mappings/population_election_execution_v1.csv`. It preserves election and
release dates, fixed target and Senate-plan identities, population inputs,
crosswalk IDs and hashes, result partition hashes, QA paths, and known
limitations. The raw inputs and generated result artifacts remain local and
ignored by Git under the repository data/artifact policy.

## ACS support policy

The allocation support is chosen by population-product vintage, not by the
later election in which the product becomes available.

| ACS estimate years | Source geography | Accepted support | Reason |
|---|---|---|---|
| 2009 | 2009 Census 2000 block groups | normalized block-group area | No proven pre-period block-population support is available. |
| 2010 | 2010 block groups | normalized block-group area | Census 2010 population is contemporaneous/post-reference support, so the POC does not use it as if it were pre-period information. |
| 2011–2019 | 2010 block groups | 2010 Census block population | The support predates each ACS reference-period end; nine zero-support groups use typed area fallback. |
| 2020–2024 | 2020 block groups | 2010 Census population through the official 2010→2020 relationship | The population support predates these products; 74 zero-support 2020 groups use typed area fallback. |

The accepted `POC015` crosswalk is reused exactly for the 2011–2015 product on
the 2012 Revised Final plan. Estimates and 90% margins of error remain separate.
Each target MOE scales source MOEs by the allocation weights and combines them
by root-sum-square; source covariance and allocation-weight uncertainty are not
available.

## Validation result

All 19 `POC016` QA checks pass:

- every eligible pairing is executed and every execution row resolves to one
  indexed crosswalk and result partition;
- every product/plan partition covers exactly 9,178 fixed precincts and 50
  Senate districts;
- the maximum absolute state-total conservation delta is `0.0` for both
  precinct and Senate outputs;
- precinct and Senate state totals agree exactly;
- fixed-precinct totals are invariant across Senate-plan partitions within the
  declared `0.001`-person precision tolerance; the observed maximum range is
  `0.00003914396029358613` person;
- every ACS estimate has a complete, nonnegative MOE; and
- the nearest-assignment count is zero.

The accepted logical SHA-256 values are:

| Artifact | Logical SHA-256 |
|---|---|
| Execution manifest | `7deddb04760a22943b26c3eadc067c96c32ebd8d1439ae0685dee4d54bf3d5a6` |
| Fixed-precinct results | `7fb71ee710f2b6c3251e976cca5da1963fb96d05274088359b10e64ade8d3467` |
| Senate results | `03c29b4ab42eb48971fcdd6f3dbffad47a3ad8f72d032036bbbfd3f75b6647d2` |

Machine-readable local evidence is in `artifacts/poc016/input_manifest.json`,
`artifacts/poc016/qa_results.json`, and `artifacts/poc016/report.md`. Generated
crosswalks and combined results are under `data/processed/poc016/`.

## Interpretation and limitations

This result completes the simplified fixed-geography POC. It is not a
historical precinct reconstruction and it does not select forecast features.
The execution manifest shows what was available by each cutoff so downstream
modeling can make that choice without future-data leakage.

The 1990 election intentionally has no result because no cataloged product was
available by election day. Historical decennial allocations remain area-based
models, not population truth. The 2009 and 2010 ACS allocations use simple area;
later ACS products use increasingly stale 2010 population support, with typed
zero-support fallbacks. Target ACS MOEs remain approximations. Actual-vintage
precincts, legislative assignments, and contest eligibility remain the
deferred `POC008`, `POC009`, `POC018`, and `POC020` scope.

## Reproduce

With the checksum-frozen local inputs present:

```bash
.venv/bin/python -m census_pa_poc.all_pairings --root .
```

The command refuses to overwrite a changed versioned artifact. An identical
replay reuses the accepted artifacts and reproduces the logical hashes above.
