# Planning mappings

These tracked CSV files turn the current plan into inputs Python can read:

- `population_periods.csv` maps requested observations to candidate official
  products, availability, and allocation routes.
- `election_cycles.csv` enumerates all 19 even-year general-election targets,
  their House coverage, and their staggered regular Senate class.
- `source_catalog.csv` records confirmed sources and research candidates.
- `crosswalk_methods.csv` defines distinct method families and proof status.

`candidate` and `research` rows are not approved data. Missing checksums,
licenses, vintages, or schemas must be filled from an actual retrieval manifest
before an input passes `POC001` or later source gates.

`proven_cumberland` means the method passed the accepted Cumberland experiment;
it does not approve the method for Philadelphia, statewide use, historical
precinct snapshots, or coarser ACS inputs.
