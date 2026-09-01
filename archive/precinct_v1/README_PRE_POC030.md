# Census PA Python proof of concept

This repository now answers one narrow replacement question before production
architecture is resumed:

> Can selected Census and ACS products be reproducibly allocated directly to
> the Pennsylvania State House and State Senate plans applicable to each
> even-year general election from 1992 through 2026, with explicit weighting,
> understandable error, and conserved totals?

The first repository (`census-pa-map`) proved that the required 2020 Census and
2021 Pennsylvania LRC files exist and are mutually usable for Cumberland
County. This repository has now saved and verified the Cumberland mechanics
proof and the Philadelphia split-block method comparison. Those precinct-based
products are frozen evidence, not inputs to the active direct legislative-plan
path. The current boundary of the proof is recorded in
[docs/PROOF_STATUS.md](docs/PROOF_STATUS.md).

## Approach

1. Prove a direct, chamber-neutral 2020 Census path to both 2021 Final plans.
2. Keep atomic district assignment separate from metric-specific allocation
   weights and record the support universe and fallback on every weight.
3. Compare official block equivalencies with an independent plan-polygon
   diagnostic and require statewide conservation.
4. Extend the accepted contract across the historical House/Senate plans and
   accepted decennial and ACS source families.
5. Archive precinct-only code, tasks, mappings, and ignored data only after the
   direct legislative products reach documented parity.

This ordering is intentional: no catalog service, database schema, web app, or
workflow engine is needed to answer the POC question.

## Repository map

- [docs/PROJECT.md](docs/PROJECT.md): scope and lower-level goals.
- [docs/TASKS.md](docs/TASKS.md): authoritative experiment backlog.
- [docs/PROOF_STATUS.md](docs/PROOF_STATUS.md): what is and is not proven.
- [docs/DECISIONS.md](docs/DECISIONS.md): accepted and open choices.
- [docs/VALIDATION.md](docs/VALIDATION.md): evidence required for each proof.
- [docs/CUMBERLAND_2020_PROOF.md](docs/CUMBERLAND_2020_PROOF.md): accepted
  evidence for `POC001`–`POC005`.
- [docs/PHILADELPHIA_2020_PROOF.md](docs/PHILADELPHIA_2020_PROOF.md): accepted
  source and method evidence for `POC006`–`POC007`.
- [docs/VISUAL_REVIEW.md](docs/VISUAL_REVIEW.md): accepted reusable coverage
  and population-map evidence for `POC023`.
- [docs/ELECTION_POPULATION_REVIEW.md](docs/ELECTION_POPULATION_REVIEW.md):
  accepted election-year precinct and Senate rollup evidence for `POC024`.
- [docs/CENSUS_FEATURE_METRIC_CATALOG.md](docs/CENSUS_FEATURE_METRIC_CATALOG.md):
  candidate Census-derived forecasting metrics and their implementation limits.
- [docs/DATA_EXPLORER.md](docs/DATA_EXPLORER.md): local interactive inspection
  workflow and QGIS geometry-audit path for `POC026`.
- [docs/TRUSTED_TOTAL_RECONCILIATION.md](docs/TRUSTED_TOTAL_RECONCILIATION.md):
  trusted Census county/state comparisons and observed fixed-target deltas for
  `POC027`.
- [docs/DIRECT_LEGISLATIVE_CROSSWALK_PROOF.md](docs/DIRECT_LEGISLATIVE_CROSSWALK_PROOF.md):
  accepted direct 2020 Census-to-2021 Final House/Senate evidence for `POC028`.
- [mappings/README.md](mappings/README.md): machine-readable planning maps.
- `.agents/private/`: local AI working memory; never canonical.

## Intended Python shape

Exploratory notebooks may visualize or inspect results, but reusable work moves
into small functions under `src/census_pa_poc/` and is exercised by tests.
Generated crosswalks, data, and reports remain uncommitted until their source
terms and release policy are decided.

## Run the Cumberland proof

The raw archives and generated products are intentionally ignored. After the
three exact archives in `src/census_pa_poc/cumberland.py` have been placed at
their documented `data/raw/` paths:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m census_pa_poc.cumberland --root .
.venv/bin/ruff format --check src tests
.venv/bin/ruff check src tests
.venv/bin/pytest -q
```

The run verifies source checksums before parsing. Versioned crosswalks are
created once; a rerun reuses an identical artifact and refuses to overwrite a
different artifact at the same method-version path.

Run the Philadelphia source and complex-county proof after also placing the
checksum-frozen City Political Divisions GeoJSON at the path recorded in
`src/census_pa_poc/philadelphia.py`:

```bash
.venv/bin/python -m census_pa_poc.philadelphia --root .
```

Regenerate the accepted coverage and fixed-precinct population visuals after
the accepted statewide artifacts are present:

```bash
.venv/bin/python -m census_pa_poc.visual_review --root .
```

Regenerate the complete election-year precinct tables, applicable-plan Senate
rollups, coverage overview, and per-election charts with:

```bash
.venv/bin/python -m census_pa_poc.election_population_review --root .
.venv/bin/python -m census_pa_poc.source_reconciliation --root .
```

Install the optional explorer dependencies and open the accepted population
products in a reactive notebook:

```bash
.venv/bin/python -m pip install -e '.[dev,explore]'
.venv/bin/marimo edit notebooks/explore_population.py
```

For a read-only local interface, replace `edit` with `run`.

## Run the direct legislative proof

After placing the checksum-frozen Census, LRC geography, House, and Senate
inputs at the paths recorded by the module, run:

```bash
.venv/bin/python -m census_pa_poc.direct_legislative --root .
```

The command creates versioned chamber-neutral assignment, `P0010001`
crosswalk, result, and comparison products. A rerun reuses byte-identical
logical artifacts and refuses to overwrite a different artifact at the same
versioned path.
