# Replay source manifests

These files are canonical inputs, not generated QA artifacts. They preserve the
exact raw files, checksums, provenance, vintages, schemas, licenses, and
geographic universes needed to replay the maintained population and v2 export
pipelines.

- `decennial_1990_v1.json`, `decennial_2000_v1.json`, and
  `decennial_2010_v1.json` cover historical population inputs.
- `direct_2020_v1.json` covers the current-plan P1/P3 notebook inputs.
- `acs5_raw_files_v1.json` covers the ACS files used by the population and
  socioeconomic export paths.

Per-run observations and QA reports belong under ignored `artifacts/work/` and
may be deleted after the retained final acceptance evidence is refreshed.
