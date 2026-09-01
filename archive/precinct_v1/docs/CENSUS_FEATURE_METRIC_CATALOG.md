# Census feature metric catalog

`POC025` establishes the candidate Census-derived feature space for a later
Pennsylvania State Senate election model. It does not select features, fit a
model, or prove any metric beyond the accepted total-population products.
The executable planning list is
[`mappings/feature_metric_catalog_v1.csv`](../mappings/feature_metric_catalog_v1.csv).

## Scope boundary

This repository owns Census and ACS measures plus closely related U.S. Census
Bureau supplements. Election results, registration, candidates, campaign
finance, BLS/BEA macroeconomic series, Michigan consumer sentiment,
Pennsylvania UCC reporting, CPI, energy prices, and GDP belong to a separate
project.

The distinction matters because Census/ACS products describe local population,
household, housing, and economic composition. They are generally annual
five-year period estimates, not current monthly economic shocks. A county,
Pennsylvania, or national ACS value can be included as context, but it cannot
substitute for a contemporaneous labor-market, price, sentiment, or GDP series.

## Priority definitions

- `P0`: first source inventory and allocation proof. These metrics have the
  clearest election relevance or define the eligible population.
- `P1`: next expansion after the `P0` person-count path is generic and tested.
- `P2`: useful candidates that have shorter history, coarser geography,
  changing classifications, or require a different support universe.

Priority means implementation order, not proven predictive importance.
Feature selection must later use election-cutoff-safe, time-split validation.

## Recommended first Census bundle

| Metric family | Preferred representation | Main source family | Why it is first |
|---|---|---|---|
| Total population | Additive count | Decennial `P0010001`; ACS `B01003` | Existing proven denominator and support surface |
| Voting-age population | Additive age-18+ count | Decennial voting-age tables; ACS `B01001` | Better electorate denominator than total population |
| Citizen voting-age population | Additive CVAP count and CVAP/VAP | ACS CVAP special tabulation | Best available public eligible-electorate approximation |
| Age | Counts for 18–29, 30–44, 45–64, and 65+ | ACS `B01001` | Preserves an additive distribution instead of a median |
| Race and ethnicity | Mutually exclusive counts | Decennial tables; ACS `B03002`; CVAP | Core demographic composition with an explicit category bridge |
| Education | Counts below high school, high school, some college, and bachelor's+ among age 25+ | ACS `B15003` | Stable additive socioeconomic composition |
| Employment | Employed, unemployed, labor force, and population 16+ counts | ACS `B23025` | Supports employment-population, unemployment, and participation rates |
| Poverty | Counts by poverty-ratio band | ACS `B17001` or `C17002` | More robust than a single economic median |
| Household income | Household counts by income band | ACS `B19001` | Supports shares and a derived approximate median |
| Immigration/citizenship | Native, foreign-born, naturalized, and noncitizen counts | ACS `B05001`/`B05003` | Separates community composition from eligible electorate |
| Housing tenure | Owner and renter household counts | ACS `B25003` | Core housing and residential-rootedness measure |
| Population density | Population divided by projected land area | Accepted population plus geometry | Reproducible urbanization gradient on the fixed target |

## Full candidate families

The machine-readable catalog expands the first bundle into the following
families:

| Category | Candidate measures |
|---|---|
| Demographic | total population; VAP; CVAP; age; race/ethnicity; sex; household/family type; marital status; group quarters |
| Education | educational attainment; school and college enrollment |
| Immigration | foreign-born, naturalized, and noncitizen population; voting-age citizenship; entry period; broad origin; language and English proficiency; ancestry |
| Migration | residence one year ago; residential stability; moves within county, across counties/states, and from abroad; Census county/MCD flow files; Population Estimates Program domestic/international migration |
| Employment | employment-population ratio; unemployment; labor-force participation; occupation; industry; commuting mode; work from home; travel time |
| Income and hardship | household income bands; earnings; inflation-adjusted change between eligible ACS products; poverty-ratio bands; SNAP receipt |
| Housing | units; occupancy/vacancy; tenure; rent and home-value distributions; housing-cost burden; heating fuel; vehicles; internet access |
| Social | health insurance; disability; veteran status |
| Urbanization | population density; decennial urban/rural classification; Census Building Permits Survey as an optional Census Bureau supplement |

## Requested economy categories: Census answer and gap

| Requested category | What this repository can provide | What remains outside this repository |
|---|---|---|
| Employment rate at local, county, Pennsylvania, and national levels | `B23025` counts and derived employment-population, unemployment, and participation rates. Use allocated block-group values locally and direct published ACS county/state/national values for context. | Monthly/current-cycle BLS labor conditions and payroll shocks |
| Education | `B15003` additive attainment bands; optionally school enrollment | None for the structural composition measure |
| Perceptions of national economic conditions | No Census/ACS equivalent | Michigan consumer sentiment, expectations, or polling |
| Demographic composition | Population, VAP, CVAP, age, race/ethnicity, sex, household/family, citizenship, language, disability, veteran, and group-quarters measures | Religion, party identification, and other non-Census attitudes |
| Cost of goods, energy, and food | Housing-cost burden, rent/value distributions, heating-fuel exposure, commuting, and vehicle availability are household-cost or exposure proxies | CPI/inflation and actual food or energy price series |
| Income and income growth | Income-band counts, aggregate income/earnings where published, poverty, and change between cutoff-eligible ACS periods | GDP growth, quarterly personal income, and current wage shocks |
| Urbanization and permitting | Density and decennial urban/rural classifications. Census Building Permits Survey can supply a separate county/place construction signal. | Pennsylvania UCC filings and other state-law permit systems |
| Immigration and emigration | Nativity, citizenship, year of entry, language, residence one year ago, ACS migration flows, and Census Population Estimates migration components | Legal-status categories and non-Census administrative immigration data |

## Source findings

- ACS five-year Detailed Tables publish the most detailed estimates and MOEs,
  with many tables available down to block groups. Availability is table- and
  vintage-specific and must be verified rather than inferred from the overall
  product. See the Census Bureau's
  [ACS table guide](https://www.census.gov/programs-surveys/acs/data/data-tables.html)
  and
  [Summary File guide](https://www.census.gov/programs-surveys/acs/data/summary-file.html).
- `B23025` contains the age-16+ total, labor force, civilian labor force,
  employed, unemployed, armed-forces, and not-in-labor-force counts. The Census
  Bureau documented block-group publication beginning with the 2007–2011
  five-year product. See the
  [2011 table-change documentation](https://www.census.gov/programs-surveys/acs/technical-documentation/table-and-geography-changes/2011/5-year.html).
- The CVAP special tabulation is available at block-group geography and has
  recurring five-year releases beginning with 2005–2009. See the
  [2020–2024 CVAP documentation](https://www2.census.gov/programs-surveys/decennial/rdo/technical-documentation/special-tabulation/CVAP_2020-2024_ACS_documentation_v1.pdf).
- Census foreign-born data cover citizenship, place of birth, and year of
  entry. They do not identify unauthorized residents or other legal-status
  categories separately. See the Census Bureau's
  [foreign-born definition](https://www.census.gov/topics/population/foreign-born/about.html).
- ACS asks residence one year ago and supports both local mobility tables and
  coarser origin/destination flow files. See the
  [migration question documentation](https://www.census.gov/acs/www/about/why-we-ask-each-question/migration/)
  and
  [ACS migration-flow documentation](https://www.census.gov/data/developers/data-sets/acs-migration-flows.html).
- The Population Estimates Program publishes annual state/county domestic and
  international migration components, but each vintage revises the complete
  post-decennial series. See the
  [program description](https://www.census.gov/programs-surveys/popest/about.html).
- Census urban/rural classification is decennial and its criteria changed
  materially between 2010 and 2020. Census does not define a separate
  "suburban" category. See
  [Urban and Rural](https://www.census.gov/programs-surveys/geography/guidance/geo-areas/urban-rural.html).
- The Census Building Permits Survey provides residential permits at national,
  state, county, and permit-issuing-place levels. It is a Census Bureau
  supplement, not an ACS crosswalk metric, and its substate coverage and
  reported/imputed status must be retained. See the
  [Building Permits Survey](https://www.census.gov/construction/bps/index.html).

## Allocation and derivation rules

1. Allocate additive counts, not published percentages, rates, or medians.
2. Derive a rate only after its numerator and denominator have been allocated
   with the same geography, vintage, method, and universe.
3. Derive medians from allocated distribution bands. Keep the directly
   published source median only as a comparison; never average medians.
4. Preserve each estimate and 90% MOE separately. Derived MOEs must state the
   covariance and crosswalk-weight limitations already accepted for `POC015`.
5. Person metrics may reuse the accepted ACS person-population crosswalk as a
   candidate method, with subgroup-homogeneity error stated explicitly.
6. Household and housing metrics need a separately proven household- or
   housing-informed support surface. Total-population weights cannot be
   silently relabeled as household weights.
7. Tract-only or otherwise restricted tables require a new source-geography
   crosswalk; block-group availability must be tested for every table/vintage.
8. Direct county, Pennsylvania, and national ACS values are context features;
   do not reconstruct them by summing modeled precinct values when an official
   direct estimate exists.
9. Every product must retain its release date and pass the same election-cutoff
   mapping used by `POC019`. Adjacent five-year ACS releases overlap and their
   changes are not independent annual growth rates.

## Known historical limits

- The current accepted ACS window is 2005–2009 through 2020–2024. There is no
  comparable ACS feature observation for the 1990s.
- Census 1990 and 2000 long-form products may supply historical socioeconomic
  measures, but they are not yet inventoried and are not automatically
  comparable with modern ACS tables.
- The 2010 and 2020 decennial censuses do not replace ACS socioeconomic tables.
- Race, urban/rural, occupation/industry, income bands, and some question
  concepts change across vintages and require explicit bridges.
- Census/ACS structural conditions should not be described as perceptions or
  current macroeconomic shocks.

## Status

This catalog establishes source families, expected transformations, priority,
and known gaps. Except for total population and derived density, every listed
metric remains `inventory_pending`, `source_table_inventory_pending`, or
`derivation_ready` in the CSV. A later experiment must freeze exact variables,
geographies, releases, checksums, universes, and MOEs before claiming that a
metric is available or allocated.
