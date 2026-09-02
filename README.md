# Census PA direct legislative proof of concept

This repository proves that selected Census and ACS total-population products
can be allocated directly to the Pennsylvania State House and State Senate
plans applicable from 1992 through 2026. Precinct geography is neither a target
nor an intermediate in the accepted pipeline.

`POC029` accepts 78 immutable product/plan/chamber partitions across 20
population products, eight official legislative plans, 203 House districts,
and 50 Senate districts. `POC031` separately accepts 2020 PL 94-171 P3 voting-age
population on both 2021 Final plans without reusing total-population weights.
`POC032` adds those two partitions to the explorer behind a distinct metric
selector. `POC036` proves continuous education, employment, and poverty
aggregates. `POC039` closes the POC with complete model-ready House and Senate
CSV panels for every general-election year from 1992 through 2026.

## Repository map

- `docs/POC029_STATUS.md`: accepted direct historical result and limitations.
- `docs/DIRECT_LEGISLATIVE_CROSSWALK_PROOF.md`: accepted 2020 baseline.
- `docs/POC031_VAP_PROOF.md`: accepted current-plan voting-age population proof.
- `docs/POC039_STATUS.md`: accepted district/election CSV contract, source
  timing, transformations, limitations, and hashes.
- `data/exports/model_features/v2/`: corrected cutoff-safe model-facing CSVs,
  source-selection table, data dictionary, and usage README.
- `artifacts/poc029/final_acceptance_qa.json`: retained population acceptance
  and statewide QA evidence.
- `artifacts/poc034/explorer_qa.json`: retained current-notebook P1/P3 QA.
- `artifacts/poc039/`: retained v2 export QA.
- `docs/TASKS.md`: closed POC maintenance record.
- `mappings/legislative_plans_v1.csv`: official House/Senate plan registry.
- `mappings/legislative_population_partitions_v1.csv`: accepted product/plan
  applicability without precinct identity.
- `notebooks/explore_population.py`: read-only direct House/Senate explorer.

## Replay the accepted direct proof

After placing checksum-frozen raw inputs at the paths recorded by the modules:

```bash
.venv/bin/python -m census_pa_poc.legislative_plans --root .
.venv/bin/python -m census_pa_poc.direct_legislative_decennial --root .
.venv/bin/python -m census_pa_poc.direct_legislative_acs --root .
.venv/bin/python -m census_pa_poc.direct_legislative_acceptance --root .
.venv/bin/python -m census_pa_poc.direct_legislative_vap --root .
.venv/bin/python -m census_pa_poc.decennial_socioeconomic --root .
.venv/bin/python -m census_pa_poc.model_export --root .
```

The commands reuse identical immutable data products and reject changed content
at an accepted versioned path. Required raw-input manifests live under
`mappings/source_manifests/`; `artifacts/` contains generated QA only. Stage
outputs go under `artifacts/work/` and may be removed after acceptance.

## Explore the results

```bash
.venv/bin/python -m pip install -e '.[dev,explore]'
.venv/bin/marimo run notebooks/explore_population.py
```

The primary explorer is a compact audit of the 2021 Final House and Senate
plans used in 2026. It independently reconciles both chambers to the Census
state total for P1 total population and P3 voting-age population, then exposes
the accepted split-block allocation, one context map per impacted district,
and corrected-fragment geometry. Historical and ACS results remain available
in the accepted direct data products rather than being crowded into the primary
notebook.

## Validate

```bash
.venv/bin/ruff check .
.venv/bin/pytest -q
.venv/bin/marimo check notebooks/explore_population.py
```

Raw data, generated data, and QA artifacts remain ignored pending a licensing
and redistribution decision. Only final population, notebook, and v2 export QA
artifacts are retained locally; intermediate run reports are disposable.
Superseded work is recoverable from Git history instead of being duplicated in
the working tree.
