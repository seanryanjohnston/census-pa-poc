# POC033 additive-metric inventory

Status: **done — inventory and transformation contract frozen**

`POC033` freezes the remaining P0 metric sources without treating published
aggregates as person- or household-level records. The executable definitions
are in `mappings/additive_metric_definitions_v1.csv`; the separate CVAP release
series is in `mappings/cvap_products_v1.csv`. The accepted ACS product dates and
plan applicability remain in `mappings/acs5_products.csv` and
`mappings/legislative_population_partitions_v1.csv`.

## Transformation rule

The source tables are aggregate estimates. The POC may perform only these
declared operations:

1. select a directly published aggregate when it already matches the desired
   numerator, denominator, or category;
2. sum mutually exclusive published cells into a broader additive category;
3. allocate those counts to a district with a separately declared support
   surface;
4. derive a share, rate, density, or approximate median only after compatible
   additive counts have been allocated; and
5. retain estimates and 90% MOEs as separate values.

It must not sum a parent with its descendants, reconstruct microdata, average
published medians, allocate a percentage or rate, or describe a subgroup proxy
weight as observed subgroup distribution. A sum of ACS cells uses root-sum-
square (RSS) MOE as an approximation because covariance is unavailable. The
district allocation then uses the accepted weighted-source RSS approximation;
source covariance and allocation-weight uncertainty remain omitted.

## Frozen families

| Group | Exact source | Frozen additive output | Transformation boundary |
|---|---|---|---|
| VAP | 1990 PL P003; 2000 PL003; 2010/2020 P3; ACS `B01001` | population 18+ | 1990 alone requires an exact sum of five mutually exclusive P003 race cells; later decennial totals are selected directly; ACS sums age/sex cells. |
| CVAP | 2005–2009 through 2020–2024 ACS CVAP special tabulations, BlockGr line 1 | `CVAP_EST`, `CVAP_MOE` | Select the direct line-1 CVAP aggregate. Never substitute all-age `CIT_EST`. |
| Age | ACS `B01001` | 18–29, 30–44, 45–64, 65+ | Sum the declared mutually exclusive age/sex cells. The four bands sum exactly to ACS VAP. |
| Race/ethnicity | 1990 P004; 2000+ PL P2; ACS `B03002` | Hispanic; non-Hispanic White, Black, AIAN, Asian/Pacific Islander, other/multiracial | Select Hispanic and single-race parents directly, then collapse Asian+NHPI and other+multiracial. The 1990 response model is a documented conceptual break. |
| Nativity/citizenship | ACS `B05001` | native; foreign-born naturalized; foreign-born noncitizen | Native is the exact sum of three birthplace/citizenship cells. Noncitizen must not be labeled undocumented. |
| Education | ACS `B15002` for 2009–2024 | below high school; high school; some college/associate; bachelor's+ | Collapse sex and detailed attainment cells into four bands for every product. `B15003` is an overlap-validation reference only; this is an aggregate category bridge, not a record-level recode. |
| Employment | ACS tract-level `B23001` for 2009–2024 | employed; unemployed; Armed Forces; not in labor force | Sum mutually exclusive age/sex/status leaves for every product. Legacy sequence files contain zero-filled block-group placeholders, not observations. Allocate the consistently published tract estimates with same-product block-group population support and validate point estimates against tract-aggregated `B23025` where available. |
| Poverty | ACS `C17002` | its seven published poverty-ratio bands | `C17002` is already collapsed. Preserve its bands; do not claim the detail available in a B table. |
| Household income | ACS `B19001` | its 16 published household bands | Allocate counts, never `B19013` medians. Dollar bins remain nominal to each product; real-dollar rebucketing would require an external price index and a within-bin assumption. |
| Tenure | ACS `B25003` | owner- and renter-occupied units | Select the two direct aggregates; their sum must equal the published occupied-unit parent. |
| Density | accepted total population plus normalized plan geometry and 2020 TIGER/Line areawater | population, land km², density, log density | Derive after allocation. Land is EPSG:5070 area of each plan polygon after subtraction of Census areawater polygons; zero land fails and zero density has no log value. |

Every exact variable expression, including all age and education cells, is
stored in the mapping rather than abbreviated in this narrative.

## Vintages, cutoffs, and plan applicability

- The ACS detailed-table scope is all 16 five-year products from 2005–2009
  through 2020–2024. Canonical education uses block-group `B15002` throughout.
  Employment uses tract-level `B23001` throughout; no block-group `B23001` row
  is treated as observed. Exact period bounds and release dates come from
  `mappings/acs5_products.csv`.
- CVAP is a separate product family with separate release dates. All 16 files
  are block-group products and are enumerated in
  `mappings/cvap_products_v1.csv`. The 2005–2009 file has no all-age citizen
  columns at block-group grain, but it does publish direct CVAP and its MOE.
- A product is eligible only after its own release date and only for a plan
  effective for that election. CVAP inherits the matching ACS estimate year's
  plan-vintage rows only after applying the later CVAP release cutoff.
- The 1990 PL source uses March 8, 1991, the conservative latest statewide
  delivery bound, because an exact Pennsylvania delivery day is not frozen.
  That still precedes the first applicable 1992 general election.
- The 2017 CVAP row conservatively uses the official archive timestamp until
  an original publication-day page is frozen. This does not change its first
  eligible even-year election.

Official Census sources include the [ACS detailed-table API metadata](https://api.census.gov/data/2024/acs/acs5/groups.html),
the [CVAP release series](https://www.census.gov/programs-surveys/decennial-census/about/voting-rights/cvap.html),
the [1990 PL 94-171 dataset](https://www.census.gov/data/datasets/1990/dec/redistricting-data-pl-94-171.html),
and the [current redistricting summary-file documentation](https://www.census.gov/programs-surveys/decennial-census/about/rdo/summary-files.html).

## Support is not accepted by inventory

The inventory names candidates; it does not approve them:

- decennial metrics need metric-specific fragment support when published and
  otherwise an explicitly modeled geometry split;
- ACS person universes may test the existing product-vintage person support,
  but must state subgroup-homogeneity error and may not call P1 or P3 weights
  metric truth;
- household income and tenure require occupied-housing-unit support and cannot
  inherit person weights; and
- density requires a new, checksum-frozen Census areawater source inventory.

The currently downloaded ACS files contain `B01003` only. `POC035`–`POC037`
therefore must freeze and download the exact new table inputs before allocation;
the inventory does not pretend those inputs already exist locally.

## Evidence

`python -m census_pa_poc.additive_metric_inventory --root .` validates 19
definitions, 16 CVAP products, all required families, product ranges, cutoffs,
plan-policy references, MOE declarations, continuous `B15002` education and
tract-level `B23001` employment, the no-median rule, and the density land definition. All 19 checks pass
in `artifacts/poc033/inventory_qa.json` and are covered by
`tests/test_additive_metric_inventory.py`.
