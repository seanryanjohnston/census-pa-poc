# Current-plan reconciliation and split-block explorer

The version-controlled marimo notebook at
`notebooks/explore_population.py` is the compact `POC034` audit for the 2021
Final Pennsylvania State House and State Senate plans used in the 2022, 2024,
and 2026 elections. It reads accepted direct products only; precinct geography
is neither loaded nor used.

The accepted historical decennial and ACS products remain preserved under
`data/processed/direct_legislative/poc029/` and supported by the general
explorer helpers and tests. They are intentionally absent from the primary
notebook so that its reconciliation and split-allocation evidence stays clear.

## Start the explorer

From the repository root:

```bash
.venv/bin/python -m pip install -e '.[dev,explore]'
.venv/bin/marimo run notebooks/explore_population.py
```

Use `marimo edit` instead of `marimo run` to inspect or edit cells.

## Notebook controls and views

One metric selector switches between the two independently accepted current
products:

- 2020 Census P1 `P0010001`, standard total population; and
- 2020 Census P3 `P0030001`, total population 18 years and over.

For the selected metric, the notebook shows:

1. a three-row state reconciliation table containing the independently read
   Pennsylvania source benchmark, the sum of 203 House districts, and the sum
   of 50 Senate districts;
2. two compact box plots summarizing the House and Senate district
   distributions without hundreds of bars;
3. a searchable, downloadable district table inside an accordion;
4. House and Senate split-block counts derived from the accepted
   metric-specific crosswalk;
5. a compact allocation bar and four-column table for the selected split
   parent block; and
6. one compact context map per impacted district, with every district sharing
   the block visible, the focus district highlighted, district numbers printed
   on the polygons, and the split block marked; and
7. a map zoomed to only that block's corrected LRC fragments, colored by their
   district assignments.

No full-state district polygon map is rendered. This keeps the page small and
ensures the only split block is visible at a useful scale.

## Reconciliation evidence

The state benchmarks are read from the official Pennsylvania 2020 PL 94-171
block files independently from the House and Senate district-result artifacts.

| Metric | Pennsylvania source | House districts / sum | Senate districts / sum | Difference |
|---|---:|---:|---:|---:|
| P1 total population | 13,002,700 | 203 / 13,002,700 | 50 / 13,002,700 | 0 / 0 |
| P3 voting-age population | 10,353,548 | 203 / 10,353,548 | 50 / 10,353,548 | 0 / 0 |

`load_current_plan_tables` rejects the notebook inputs if a chamber has the
wrong district count, a chamber total differs from the independent state
benchmark, or split-block weights fail to sum to one.

## Split-block evidence

Both accepted metric-specific crosswalks identify the same current-plan
pattern:

- State House: one split Census parent block;
- State Senate: zero split Census parent blocks; and
- split parent: `421010257002008`.

The House split consists of corrected fragments `421010257002008B` in District
194 and `421010257002008A` in District 200. For both P1 and P3, the parent value
is 40: District 194 receives 40 (100%) and District 200 receives 0 (0%). The
method selector changes from `published_fragment_p001` to
`published_fragment_p003` with the metric; total-population weights are not
relabelled as VAP weights.

The notebook renders two 240-by-240-pixel context maps for this split. Both
show House districts 194 and 200 at the same extent. The first highlights 194;
the second highlights 200. A red diamond marks the shared split block on their
common boundary. The close-up fragment map remains below these context views.

## Interpretation

- P1 and P3 are exact decennial source counts without sampling MOEs.
- Census disclosure-avoidance and nonsampling limitations still apply.
- The visible split is resolved with published metric-specific fragment
  support, not with an area fallback.
- A zero-valued fragment is still real geometry and remains visible on the
  fragment map even though its allocation bar has zero width.
- The notebook reads accepted Parquet artifacts without overwriting them.
- The data remain local pending a redistribution-terms review.

## Validation

`tests/test_data_explorer.py` covers independent source totals, both chamber
reconciliations, split counts, allocation weights, and real corrected-fragment
geometry. `POC034` passes Ruff, all 66 active tests, the marimo static checker,
an executed 245 KiB HTML render, and a live selector check that changes the
state table to 10,353,548 VAP and the split method to
`published_fragment_p003`. The executed render is 552 KiB after adding both
impacted-district context maps. Machine-readable evidence is in
`artifacts/poc034/explorer_qa.json`.
