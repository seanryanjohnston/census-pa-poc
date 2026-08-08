# Census PA Python proof of concept

This repository answers one narrow question before production architecture is
resumed:

> Can selected Census and ACS total-population products be reproducibly
> allocated to the Pennsylvania precinct snapshot used for each even-year
> general election from 1990 through 2026, with understandable error and
> conserved totals?

The first repository (`census-pa-map`) proved that the required 2020 Census and
2021 Pennsylvania LRC files exist and are mutually usable for Cumberland
County. This repository has now saved and verified the Cumberland mechanics
proof and the Philadelphia split-block method comparison. The current boundary
of the proof is recorded in [docs/PROOF_STATUS.md](docs/PROOF_STATUS.md).

## Approach

1. Reproduce the existing Cumberland source checks in saved Python code.
2. Test the apparent direct 2020-block-to-2021-precinct assignment in the LRC
   data and compare it with an independently computed spatial assignment.
3. Aggregate 2020 total population and prove coverage and conservation.
4. Repeat on a difficult county, choose the evidence-backed baseline, then go
   statewide after the election-specific target is frozen.
5. Freeze/reconcile the actual November 3, 2026 general-election target.
6. Inventory the distinct precinct snapshots used by every two-year general
   election cycle back through 1990.
7. Add 2010, 2000, and 1990 one at a time and make each source allocatable to
   the relevant election snapshot.
8. Inventory available mid-decade products, then implement their coarser
   block-group allocation as a separate method family.

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
