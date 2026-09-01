# POC030 direct-route archive and explorer pivot

Status: **PASS**

`POC030` preserves the abandoned precinct route at `archive/precinct_v1/` and
makes the accepted direct House/Senate products the only active workflow.
Nothing was deleted; ignored generated data moved on the same filesystem and
can be recovered from the archive.

## Archive contract

The machine-readable inventory is
`mappings/poc030_archive_manifest_v1.csv`. It records each original path,
archive path, disposition, category, and reason. It covers:

- precinct-only source modules and tests;
- the pre-pivot notebook and stale marimo session state;
- precinct-target mappings and the full pre-`POC030` task/decision snapshots;
- accepted precinct-era proof documents and artifacts; and
- ignored fixed-precinct crosswalks, results, overlays, and visuals.

## Deliberately retained shared material

Some legacy-named files remain under `src/census_pa_poc/` because the direct
pipeline imports their Census parsers, source constants, relationship builders,
LRC corrected-block loader, plan constants, or deterministic geometry hash.
The manifest identifies each retained file and its direct dependency reason.
Their old precinct result commands are not listed in the active README.

The `POC011`–`POC014` source manifests also remain active because the direct
historical and ACS stages use them as frozen provenance. Their precinct results
have moved to the archive.

## Active replacements

- `mappings/legislative_population_partitions_v1.csv` replaces the
  fixed-precinct election availability/execution mappings.
- `mappings/legislative_plans_v1.csv` replaces the Senate-only plan registry.
- `mappings/crosswalk_methods.csv` now contains only direct methods.
- `notebooks/explore_population.py` loads direct House and Senate results,
  official plan geometry, estimates, MOEs, methods, and limitations.
- `src/census_pa_poc/data_explorer.py` rejects precinct columns and validates
  all 78 accepted direct partitions.

The direct ACS manifest builder now re-verifies the already accepted raw source
list from `artifacts/poc029/acs_input_manifest.json`; it no longer reads the
archived `POC016` manifest or precinct-era availability matrix.

## Acceptance evidence

`python -m census_pa_poc.archive_validation --root .` verifies archive and
retained paths, absence of old active originals, direct-only selector mappings,
20 products, both chambers, all 78 partitions, and the explorer schema. Its
machine-readable evidence is `artifacts/poc030/archive_qa.json`.

The final acceptance run also includes direct plan/decennial/ACS replay, the
`POC029` final gate, the complete active test suite, Ruff, marimo static checks,
and an executed HTML notebook render.
