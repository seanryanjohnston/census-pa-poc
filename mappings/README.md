# Planning mappings

These tracked CSV files turn the current plan into inputs Python can read:

- `population_periods.csv` maps requested observations to candidate official
  products, availability, and allocation routes.
- `acs5_products.csv` inventories all 16 ACS five-year products from 2005–2009
  through 2020–2024 with exact release dates, block-group identity,
  estimate/MOE fields, access route, and per-vintage API metadata checksums.
- `election_cycles.csv` enumerates all 19 even-year general-election cycles,
  assigns the fixed 2021 LRC precinct target, and records the applicable Senate
  plan and staggered regular Senate class.
- `senate_plans.csv` records the five official LRC plan sources needed for
  1990–2026. All five are checksum-frozen and passed the `POC022` source and
  split-aware overlay gates; topology normalization remains explicit under
  `PD017` and area weights are not population weights.
- `precinct_sources_2026.csv` is the 67-county `POC008` resolution ledger. It
  keeps source qualification, election-effective dates, checksums, legislative
  assignments, contest eligibility, and the operational cutoff separate.
- `source_catalog.csv` records confirmed sources and research candidates.
- `crosswalk_methods.csv` defines distinct method families and proof status.

`POC011` adds the frozen 2010 PL, block geometry, and 2010→2020 relationship
sources. `relationship_atomic_area_2010_v1` is the accepted 2010 POC baseline
under `PD018`; `direct_atomic_area_2010_v1` is its diagnostic. Both are area
methods and neither may be described as a population-informed crosswalk.

`candidate` and `research` rows are not approved data. Missing checksums,
licenses, vintages, or schemas must be filled from an actual retrieval manifest
before an input passes `POC001` or later source gates.

For `precinct_sources_2026.csv`, `candidate` means a source has been retrieved
and frozen but has not met every 2026 target gate. `qualified` requires a
published effective date, verified schema and House/Senate/contest assignments,
and a met cutoff. `reviewed_gap` requires dated review notes. `unreviewed` never
counts as a gap resolution.

`fixed_poc_baseline` means every cycle intentionally reuses the 2021 LRC
precinct geography under `PD014`; it is not a claim about the precinct snapshot
actually in force for that election.

`proven_cumberland` means the method passed the accepted Cumberland experiment;
it does not approve the method for Philadelphia, statewide use, historical
source units, Senate overlays, or coarser ACS inputs.
