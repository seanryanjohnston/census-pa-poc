# Direct legislative experiment backlog

Status values are `ready`, `in-progress`, `done`, `blocked`, and `deferred`.
The full precinct-era task ledger is frozen at
`archive/precinct_v1/docs/TASKS_PRE_POC030.md`.

| ID | Status | Experiment | Depends on | Done when |
|---|---|---|---|---|
| `POC028` | done | Prove a chamber-neutral direct 2020 Census crosswalk to both 2021 Final plans. | Accepted Census/LRC source gates | Both chambers cover every source and district, conserve 13,002,700 people, use no precinct identity, and replay identically. |
| `POC029` | done | Extend the direct contract to applicable historical House/Senate plans and all accepted decennial/ACS products. | `POC028` | All 78 partitions declare provenance, applicability, weighting, fallback, uncertainty, QA, and hashes; none uses precinct input. |
| `POC030` | done | Archive precinct-only code, tasks, mappings, and ignored data; pivot the explorer and active workflow. | `POC029` | The archive manifest distinguishes moved and retained-shared material; active mappings and commands select direct products only; the direct notebook and replay checks pass. |
| `POC031` | done | Select and prove the next additive Census/ACS metric on the direct legislative contract. | `POC030` | One exact metric/table/universe is selected; support validity and MOE treatment are explicit; both chambers pass conservation and replay without assuming total-population weights generalize. |
| `POC032` | done | Add the accepted VAP partition to the direct legislative explorer. | `POC031` | Metric and product selectors cannot conflate total population with VAP; both current chambers render P3 VAP with its method and no-MOE treatment visible; notebook checks and tests pass. |
| `POC033` | done | Freeze the exact product and variable inventory for the remaining P0 additive-metric bundle. | `POC032` | Remaining VAP vintages, CVAP, age, race/ethnicity, foreign-born/citizenship, education, employment, poverty, household-income bands, and tenure have exact tables, additive category definitions, universes, source grains, vintages, release cutoffs, plan applicability, support candidates, category bridges, and MOE treatment; density has an exact land-area definition; no P1 or P3 weight is assumed valid for another universe. |
| `POC034` | done | Simplify the current-plan notebook around statewide reconciliation and split-block inspection. | `POC032` | Independent Census state totals reconcile exactly to the 203 House and 50 Senate district sums for each accepted current-plan metric; split blocks come from the accepted metric-specific crosswalks; compact maps/tables show the fragment allocations without an unreadable statewide district visual; notebook checks, tests, and an executed render pass. |
| `POC035` | deferred | Prove the eligible-electorate and demographic person-count bundle: remaining VAP vintages, CVAP, age bands, race/ethnicity, and foreign-born/citizenship. | `POC033` | Each exact product/table/universe is allocated to both applicable chambers and plans with separately justified support, estimate and MOE handling, conserved additive categories, valid parent/subgroup relationships, explicit cross-vintage category bridges, immutable hashes, and identical replay. The accepted 2020 P2 stage remains usable, but unfinished families do not block the model-ready POC export. |
| `POC036` | done | Prove the ACS socioeconomic person-count bundle: education attainment, employment status, and poverty-ratio bands. | `POC033` | Each age- or poverty-defined universe has conserved additive categories for both applicable chambers and plans; rates and shares are derived only after allocation from compatible numerators and denominators; support limitations, MOEs, cutoff eligibility, QA, immutable hashes, and replay are explicit. |
| `POC037` | deferred | Prove the household and occupied-housing bundle: household-income bands and housing tenure. | `POC033` | Household- and occupied-housing-unit support are proven separately from person-population weights; additive bands/categories conserve for both applicable chambers and plans; shares and any approximate median are derived after allocation; MOEs, dollar-year/bin bridges, QA, immutable hashes, and replay are explicit. This production-quality extension no longer blocks the POC export. |
| `POC038` | deferred | Derive Census-land-area population density for every accepted cutoff-eligible total-population partition. | `POC033` | District land area is reproducible in the declared equal-area CRS; population, land area, density, and log-density retain product/plan identity; zero-area and multipart cases are tested; results have immutable hashes and identical replay. The POC export may instead label a readily reproducible total-polygon-area density and must not call it land-area density. |
| `POC039` | done | Produce the model-ready district-by-election CSV bundle and close the POC. | `POC029`, `POC031`, completed `POC035` stage, `POC036` | House and Senate CSVs contain exactly one row per district for every general-election year from 1992 through 2026; every included feature uses a reference period ending on or before the election, provenance and transformations are explicit, keys are unique, district coverage and temporal/conservation smell tests pass, files replay byte-identically, and canonical proof status records the POC complete with deferred metric families. |

## Completion evidence

- `POC028`: `docs/DIRECT_LEGISLATIVE_CROSSWALK_PROOF.md`
- `POC029`: `docs/POC029_STATUS.md` and
  `artifacts/poc029/final_acceptance_qa.json`
- `POC030`: `docs/POC030_ARCHIVE.md` and
  `artifacts/poc030/archive_qa.json`
- `POC031`: `docs/POC031_VAP_PROOF.md` and
  `artifacts/poc031/qa_results.json`
- `POC032`: `docs/DATA_EXPLORER.md` and
  `artifacts/poc032/explorer_qa.json`
- `POC033`: `docs/POC033_METRIC_INVENTORY.md` and
  `artifacts/poc033/inventory_qa.json`
- `POC034`: `docs/DATA_EXPLORER.md` and
  `artifacts/poc034/explorer_qa.json`
- `POC036`: `docs/POC036_STATUS.md` and
  `artifacts/poc036/socioeconomic_trend_qa.json`
- `POC039`: `docs/POC039_STATUS.md` and
  `artifacts/poc039/model_export_qa_v2.json`

## POC completion boundary

`POC039` is the final POC deliverable: a stable, wide CSV contract over all
readily usable accepted metrics, with complete 1992–2026 district/election
coverage. The unfinished demographic, household/housing, and Census-land-area
proofs are deferred rather than filled with weak proxies. Later production
work may resume them, and user-guided explorer or manual quality investigations
remain outside the POC proof boundary.
