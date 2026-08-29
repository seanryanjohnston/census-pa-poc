# Project scope and goal decomposition

## High-level goal

Produce validated estimates of standard total population for selected
Census/ACS reference periods on one fixed Pennsylvania precinct geography and
the State Senate plan applicable to each even-year general election from 1990
through 2026. The fixed target is the 2021 LRC Data Set 1 precinct geography.
The 2026 general election is the current prediction target; earlier cycles
supply training observations on a comparable precinct geography.

Every output must identify the population product and period, source geography
and vintage, product release/availability date, general-election date, fixed
precinct target, applicable Senate plan, allocation method/version, and QA
result. These are constant-geography/counterfactual estimates; they do not claim
to reproduce the precincts actually used in historical elections.

## Lower-level goals

### G1 — Define the output contract

- Register every even-year Pennsylvania general election from 1990 through
  2026 and link it to the fixed 2021 LRC precinct target and applicable official
  State Senate plan.
- Freeze and validate the 2021 LRC Data Set 1 precinct target statewide.
- Inventory rather than preselect all usable population products. Decennial
  years are 1990, 2000, 2010, and 2020; mid-decade products form a separate
  catalog and processing path.
- Use standard total population only. Do not mix in Pennsylvania's
  prisoner-adjusted redistricting universe.

Pennsylvania precincts (statutory "election districts") are common election
administration units, not separate House and Senate precinct systems. House and
Senate district assignments and whether a Senate contest is on the ballot are
separate attributes. All House seats run in each even-year cycle; Senate seats
have four-year staggered terms. The POC reports every fixed precinct in every
cycle, including precinct/Senate fragments with no regular Senate contest that
year.

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

### G4 — Establish the fixed precinct target and period Senate plans

- Use the 2021 LRC Data Set 1 precinct geography as the fixed target for every
  POC cycle; never relabel it as contemporaneous 1990–2026 precinct geography.
- Prove that the published corrected-fragment assignments cover the full 2020
  Pennsylvania block universe and every fixed precinct target.
- Register the official 1981, 1991, 2001, 2012 Revised Final, and 2021 Final
  State Senate plans against the election cycles in which each was used.
- Intersect source units, fixed precincts, and the applicable Senate polygons.
  A fixed precinct may cross a historical Senate boundary, so preserve
  split-allocation rows instead of forcing one precinct-to-district label.
- Preserve regular-contest eligibility separately from geographic assignment.
- Keep actual 2026 and historical precinct source inventories as deferred
  production-fidelity research, not as prerequisites for the POC.

The fixed-target proof (`POC021`) and all five period Senate overlays (`POC022`)
passed on 2026-08-09. The overlay retains historical crossings, records source
repairs and zero-population topology exceptions, and uses no nearest assignment.

### G5 — Add historical decennial years

For each of 2010, 2000, and 1990:

- Confirm the exact official population table and compatible block geometry.
- Test direct geometric allocation from source-year blocks to the fixed LRC
  precinct target and each applicable Senate plan.
- Test official block relationship files as a topology/comparability aid.
- Compare with a modeled population-weighted crosswalk if one is available and
  its terms permit the intended use.
- Never treat land-area intersections in official relationship files as
  population weights without explicit modeling and validation.

Add one vintage at a time, newest to oldest, because formats and uncertainty
increase as the data get older.

`POC011` completed the 2010 proof on 2026-08-29. Both direct atomic area and
official relationship-assisted atomic area routes conserve 12,702,379 people
across all fixed precincts and the 2001 Final Senate plan. The official
relationship-assisted route is the POC baseline under `PD018`; it does not use
2020 population as a historical weight. The measured method deltas remain
uncertainty evidence. The next decennial vintage is 2000 (`POC012`).

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
- Map each selected block-group product to the fixed precinct target and the
  applicable Senate plan, preserving estimates and MOEs separately.

There is no comparable block-group ACS observation in the 1990s. A requested
1990s mid-decade value would therefore require a different product or an
explicit interpolation/modeling decision.

`POC014` completed the inventory on 2026-08-29. It retains all 16 overlapping
five-year releases from 2005–2009 through 2020–2024, with exact release dates,
block-group product identities, `B01003_001E` estimates, `B01003_001M` MOEs,
and checksum-frozen metadata. Allocation remains `POC015`.

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
- Building the forecast model.
- Selecting model features or fitting a model. The POC does preserve release
  dates and election dates so downstream training can avoid future-data leakage.
- Publishing raw or derived data before licensing terms are settled.
