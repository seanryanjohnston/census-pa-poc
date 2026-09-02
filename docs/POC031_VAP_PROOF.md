# POC031 direct voting-age population proof

Status: **done — 100% complete**

`POC031` selects one exact additive metric and proves it independently on the
direct legislative contract:

- product: 2020 Census State Redistricting Data PL 94-171;
- table: P3, Race for the Population 18 Years and Over;
- metric: `P0030001`, total;
- universe: Total population 18 years and over;
- source geography: 2020 Census tabulation block; and
- target: the 2021 Final Pennsylvania State House and State Senate plans used
  for the 2022, 2024, and 2026 general elections.

The Census Bureau's official [PL 94-171 dataset page](https://www.census.gov/data/datasets/2020/dec/2020-census-redistricting-summary-file-dataset.html)
and [state summary-file technical documentation](https://www2.census.gov/programs-surveys/decennial/2020/technical-documentation/complete-tech-docs/summary-file/2020Census_PL94_171Redistricting_StatesTechDoc_English.pdf)
define P3 and its universe. The checksum-frozen local Census and LRC inputs are
recorded in `mappings/source_manifests/direct_2020_v1.json`.

## Metric-specific support proof

The LRC corrected-fragment geography publishes `P0030001` on every one of its
337,039 fragments. Those fragments collapse to all 336,985 Census parent
blocks, and every parent sum agrees exactly with File 02 `P0030001` in the
official Census PL archive.

The VAP crosswalk is therefore versioned separately as
`lrc_fragment_p003_vap_direct_legislative_v1`. It does not reuse or relabel the
accepted P001 total-population weights. Of particular importance, the only
parent block split by either current plan is House block `421010257002008`:
its District 194 fragment has P3 VAP 40 and its District 200 fragment has P3
VAP 0. The VAP weights are consequently 1 and 0 from P3 support itself. No
zero-VAP area fallback affects either chamber's result.

## Acceptance evidence

| Check | House | Senate |
|---|---:|---:|
| Districts | 203 | 50 |
| Fragment assignments | 337,039 | 337,039 |
| Parent/district allocation rows | 336,986 | 336,985 |
| Split parent blocks | 1 | 0 |
| Zero-VAP fallback rows | 0 | 0 |
| Allocated VAP | 10,353,548 | 10,353,548 |
| Difference from direct fragment P3 sum | 0 | 0 |

All 30 partition checks pass. A second complete execution reports
`reused_identical` for every versioned output.

| Artifact | Logical SHA-256 |
|---|---|
| VAP parent/district crosswalk | `4dbadc9399587d4b25442e11591b0b2522a6fd1d460d329e90256cb99f602f98` |
| VAP district results | `a7b1e87030a726d8248df40797c6b315ab025d2779e1199d3a5ddeecf0c0dfeb` |
| Direct fragment comparison | `bd0f72318c90dbac3868e1d9e83a7bda50befb3257e57de5a347446e4e4533f8` |

The current notebook's consolidated P1/P3 QA is in
`artifacts/poc034/explorer_qa.json`.

## Uncertainty boundary

`P0030001` is a decennial count, not an ACS estimate, so there is no sampling
margin of error to carry or aggregate. Census disclosure-avoidance and
nonsampling limitations still apply. The crosswalk adds no modeled allocation
error in this accepted result because the only split parent is resolved by
published P3 fragment support, but that fact must be rechecked for every new
metric and plan combination.

## Reproduce

```bash
.venv/bin/python -m census_pa_poc.direct_legislative_vap --root .
```
