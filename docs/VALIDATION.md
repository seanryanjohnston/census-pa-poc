# POC validation gates

Each experiment emits machine-readable checks plus a short Markdown report.

## Input gate

- URL, retrieval timestamp, size, and SHA-256 match the manifest.
- Product, reference period, release/effective date, population universe,
  access terms, CRS, and schema are explicit.
- Each target precinct snapshot has a general-election date, effective/as-of
  date, source, and evidence for reuse if shared by multiple elections.
- Required IDs are strings, preserve leading zeros, and are unique at the
  stated grain.
- Geometries are present, valid or repaired by a recorded rule, and comparable
  in a suitable projected CRS for area operations.

## Crosswalk gate

- Each in-scope source feature has one or more allocations or a typed exception.
- Weights are finite and in `[0, 1]`.
- Weights sum to one per source within a declared tolerance.
- Every target precinct has support or a reviewed zero-population exception.
- Method, version, source vintage, target vintage, weighting universe, and
  diagnostics are columns in the artifact—not notebook prose.
- State House district, State Senate district, and regular-contest eligibility
  are separate from precinct identity. Any split assignment is a typed finding.

## Result gate

- Source and allocated state/county totals agree within the method's explicit
  rounding tolerance.
- Result grain is unique by population product, source vintage, target snapshot,
  general election, crosswalk version, precinct, metric, and universe.
- Population-product release date is retained so availability relative to the
  election cutoff can be evaluated without reconstructing provenance.
- Direct/published and independently spatial results are diffed where both
  exist.
- ACS estimates and margins of error are kept separate; no MOE is summed as if
  it were a count.

## Reproducibility gate

- Identical inputs and config produce identical logically sorted crosswalk and
  result hashes.
- Tests include at least a split source, boundary-coincident representative
  point, multipart target, water-only feature, and invalid polygon.
- A rerun never overwrites an accepted crosswalk; a changed input or method
  creates a new version.
