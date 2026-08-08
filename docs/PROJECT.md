# Project scope and goal decomposition

## High-level goal

Produce validated estimates of standard total population for selected
Census/ACS reference periods, expressed in the Pennsylvania precinct snapshot
used for each even-year general election from 1990 through 2026. The 2026
general election is the current prediction target; earlier cycles supply
training geographies.

Every output must identify the population product and period, source geography
and vintage, product release/availability date, general-election date, target
precinct snapshot, allocation method/version, and QA result.

## Lower-level goals

### G1 — Define the output contract

- Register every even-year Pennsylvania general election from 1990 through
  2026 and link each election to the precinct snapshot actually in force.
- Freeze the November 3, 2026 general-election precinct target with an explicit
  source, effective/as-of date, and operational cutoff.
- Inventory rather than preselect all usable population products. Decennial
  years are 1990, 2000, 2010, and 2020; mid-decade products form a separate
  catalog and processing path.
- Use standard total population only. Do not mix in Pennsylvania's
  prisoner-adjusted redistricting universe.

Pennsylvania precincts (statutory "election districts") are common election
administration units, not separate House and Senate precinct systems. House and
Senate district assignments and whether a Senate contest is on the ballot are
separate attributes. All House seats run in each even-year cycle; Senate seats
have four-year staggered terms. The POC collects all precincts in every cycle,
including precincts with no regular Senate contest that year.

### G2 — Prove the simplest recent-year path

- Reproduce the already documented 2020 Cumberland source gate in Python.
- Extract a direct 2020 block-to-2021 LRC precinct assignment if the block layer
  actually carries the corrected precinct key.
- Independently compute block representative-point assignment to precinct
  polygons.
- Compare both crosswalks, aggregate `P0010001`, and reconcile the result to the
  LRC precinct and county totals.

This end-to-end Cumberland proof passed on 2026-08-07. Both methods produced
the same assignment for all 5,609 blocks and reconciled exactly to all 119 LRC
precinct totals. The result proves the mechanics, not the final split-aware or
statewide method.

### G3 — Stress the method before scaling

- Select a county with split blocks, multipart precincts, dense boundaries, and
  known post-2021 changes.
- Compare direct/published assignment, representative-point assignment, and
  split-aware allocation.
- Quantify affected blocks, population, and precinct totals. Choose a baseline
  method only from that evidence.

This Philadelphia proof passed on 2026-08-07. Thirteen LRC corrected split
blocks cover 931 people. The published corrected-fragment allocation exactly
reproduces all 1,703 LRC precinct totals; representative points and equal-area
overlay produce measured precinct deltas. `PD013` selects the published route
for the 2020-to-2021 LRC baseline while leaving targets without published split
populations unresolved.

### G4 — Establish election-specific precinct targets

- Inventory state and county sources and freeze one explicit statewide target
  for the 2026 general election.
- Reconcile post-2021 precinct changes; do not call the 2021 LRC file "2026."
- Retain both the 2021 baseline and the 2026 snapshot so their differences are
  inspectable.
- Build the 2020-source-to-2026-target crosswalk and rerun statewide validation.
- Work backward through every even-year general election to 1990, reusing one
  boundary snapshot across cycles only when the evidence says it was unchanged.
- Preserve State House district, State Senate district, and regular-contest
  eligibility separately from precinct identity. Detect and document any
  historical split-precinct or ballot-style exception.

### G5 — Add historical decennial years

For each of 2010, 2000, and 1990:

- Confirm the exact official population table and compatible block geometry.
- Test direct geometric allocation from source-year blocks to each election
  precinct snapshot for which that population product is selected.
- Test official block relationship files as a topology/comparability aid.
- Compare with a modeled population-weighted crosswalk if one is available and
  its terms permit the intended use.
- Never treat land-area intersections in official relationship files as
  population weights without explicit modeling and validation.

Add one vintage at a time, newest to oldest, because formats and uncertainty
increase as the data get older.

### G6 — Add mid-decade estimates as a separate method family

ACS five-year estimates are period estimates available down to block groups,
not decennial block counts. Inventory all usable releases, process them through
a separate allocation path, and retain their margin of error even if the first
displayed metric is the estimate.

- Record every available ACS period and release date; do not force an artificial
  mid-decade observation where no comparable source exists.
- Confirm `B01003_001E`/`B01003_001M` or another explicit table.
- Select source-vintage block-group geometry.
- Compare simple area allocation with a population/housing-informed method.
- Validate estimates and MOEs separately and label their larger uncertainty.
- Map each selected block-group product to each election's own precinct
  snapshot rather than to a single modern target.

There is no comparable block-group ACS observation in the 1990s. A requested
1990s mid-decade value would therefore require a different product or an
explicit interpolation/modeling decision.

### G7 — Preserve proof artifacts

Each experiment saves:

- an input manifest with checksums and provenance;
- a versioned crosswalk as Parquet;
- precinct totals as Parquet/CSV;
- machine-readable QA results;
- a concise Markdown report; and
- deterministic Python code and focused tests.

## Non-goals until the POC passes

- Postgres/PostGIS as a required runtime.
- A catalog service, web application, deployment, or workflow orchestrator.
- Supporting metrics beyond total population.
- Joining the State Senate plan or building the forecast model.
- Selecting model features or fitting a model. The POC does preserve release
  dates and election dates so downstream training can avoid future-data leakage.
- Publishing raw or derived data before licensing terms are settled.
