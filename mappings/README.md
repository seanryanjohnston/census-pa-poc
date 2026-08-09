# Planning mappings

These tracked CSV files turn the current plan into inputs Python can read:

- `population_periods.csv` maps requested observations to candidate official
  products, availability, and allocation routes.
- `election_cycles.csv` enumerates all 19 even-year general-election targets,
  their House coverage, and their staggered regular Senate class.
- `precinct_sources_2026.csv` is the 67-county `POC008` resolution ledger. It
  keeps source qualification, election-effective dates, checksums, legislative
  assignments, contest eligibility, and the operational cutoff separate.
- `source_catalog.csv` records confirmed sources and research candidates.
- `crosswalk_methods.csv` defines distinct method families and proof status.

`candidate` and `research` rows are not approved data. Missing checksums,
licenses, vintages, or schemas must be filled from an actual retrieval manifest
before an input passes `POC001` or later source gates.

For `precinct_sources_2026.csv`, `candidate` means a source has been retrieved
and frozen but has not met every 2026 target gate. `qualified` requires a
published effective date, verified schema and House/Senate/contest assignments,
and a met cutoff. `reviewed_gap` requires dated review notes. `unreviewed` never
counts as a gap resolution.

`proven_cumberland` means the method passed the accepted Cumberland experiment;
it does not approve the method for Philadelphia, statewide use, historical
precinct snapshots, or coarser ACS inputs.
