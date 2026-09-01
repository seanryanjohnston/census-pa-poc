# Accepted election-year precinct and Senate population review

`POC024` passed on 2026-08-30. It materializes and visualizes population at two
complete election-year grains:

- 19 elections × 9,178 expected fixed precincts = 174,382 rows; and
- 19 elections × 50 expected State Senate districts = 950 rows.

No expected geography is removed when its population is unavailable. Every
row carries `data_status` and `missing_reason`.

## Display product rule

For a concise election-year view, version 1 selects the population product with
the newest reference-period end that was available by that general-election
day. Release date and product ID break ties deterministically. This is a
display-only default, not a forecast-feature or model-selection decision; the
complete `POC019` availability matrix and all `POC016` allocations remain
available for alternative views.

The selected sequence is:

- 1990: no cataloged product available by the cutoff;
- 1992–2000: 1990 Census;
- 2002–2010: Census 2000;
- 2012: ACS 2006–2010;
- 2014: ACS 2008–2012;
- 2016: ACS 2010–2014;
- 2018: ACS 2012–2016;
- 2020: ACS 2014–2018;
- 2022: ACS 2016–2020;
- 2024: ACS 2018–2022; and
- 2026: ACS 2020–2024.

Each election uses its applicable official Senate-plan partition. Precinct
output remains on the fixed 2021 LRC target; Senate output rolls the selected
product through the applicable plan rather than dissolving or forcing fixed
precinct containment.

## Missingness result

All accepted selected-product partitions from 1992 through 2026 contain all
9,178 precinct estimates and all 50 Senate district estimates. Precinct and
Senate state totals agree exactly for every populated election partition.

The 1990 election contains 9,178 explicit missing precinct rows and 50 explicit
missing Senate rows with reason
`no_cataloged_population_product_available_by_election_day`. Its map and every
district bar are visibly marked missing. Any future partial missingness uses the
same red fill/cross treatment and exact present/expected counts.

## Reusable outputs

The generator saves three immutable data products under
`data/processed/poc024/`:

- `election_population_display_selection_v1.parquet`;
- `election_fixed_precinct_population_v1.parquet`; and
- `election_senate_population_v1.parquet`.

It also generates a coverage overview and one combined precinct-map/Senate-bar
chart for each requested election under `artifacts/poc024/`. The default command
generates all 19 elections:

```bash
.venv/bin/python -m census_pa_poc.election_population_review --root .
```

To regenerate only selected detail charts while still validating the complete
data products:

```bash
.venv/bin/python -m census_pa_poc.election_population_review \
  --root . \
  --election-year 1990 \
  --election-year 2026
```

The selection, complete joins, typed missingness, map, district bars, coverage
overview, manifest, QA report, and CLI are reusable functions in
`src/census_pa_poc/election_population_review.py` with focused tests.

## Validation

All nine integration checks pass:

- the display selection covers all 19 election rows;
- only 1990 has no product available by its cutoff;
- both complete output grains have their exact expected row counts;
- all 9,178 population IDs match the fixed target geometries;
- every missing row has a reason;
- selected products have no unexpected missing rows;
- precinct and Senate state totals agree with a maximum absolute delta of
  `0.0` person; and
- the coverage overview and all 19 detail charts are nonempty.

The second data build reused all three versioned Parquet artifacts identically.
Logical SHA-256 values are recorded in `artifacts/poc024/qa_results.json`.

## Limits

These remain constant-geography/counterfactual results. They do not show the
actual precinct boundaries used in historical elections or prove the actual
2026 snapshot. ACS and historical allocation limitations remain those of their
accepted source methods. External publication remains subject to the LRC
licensing decision.
