# Metric calculations

All shares and rates are calculated by us from district-level counts. We do
not copy Census percentage fields or average percentages from smaller areas.
Published Census counts are first grouped where necessary, allocated to the
district, and only then divided.

## Census count construction

- **Education:** Census attainment counts are combined across sex into four
  mutually exclusive groups: below high school, high school, some
  college/associate degree, and bachelor's degree or higher. The tables are
  1990 P057, 2000 P037, and ACS B15002.
- **Employment:** Census counts for men and women are combined into employed,
  unemployed, Armed Forces, and not in the labor force. The tables are 1990
  P070, 2000 P043, and ACS B23001.
- **Poverty:** Published poverty-to-income ratio bands are retained or combined
  into the seven exported bands. The tables are 1990 P121, 2000 P088, and ACS
  C17002.

For decennial data, source block-group counts are allocated with
same-decennial block-population support. For ACS, education and poverty use
block-group support; employment uses tract estimates with same-product
population support. These are modeled district estimates, not individual
records.

## Shares and rates

| Exported field or group | Calculation |
|---|---|
| `education_<category>_share` | District category count ÷ district `education_population_25_plus_estimate` |
| `employment_<category>_share` | District category count ÷ district `employment_population_16_plus_estimate` |
| `employment_to_population_rate` | Employed ÷ population age 16+ |
| `civilian_unemployment_rate` | Unemployed ÷ (employed + unemployed); Armed Forces and people outside the labor force are excluded |
| `labor_force_participation_rate` | (Employed + unemployed + Armed Forces) ÷ population age 16+ |
| `poverty_<band>_share` | District band count ÷ district population for whom poverty status was determined |
| `poverty_below_poverty_line_estimate` | Under 0.50 + 0.50–0.99 poverty-ratio counts |
| `poverty_below_poverty_line_share` | Below-poverty-line estimate ÷ population for whom poverty status was determined |
| `poverty_below_200_percent_estimate` | Sum of all poverty-ratio bands below 2.00 |
| `poverty_below_200_percent_share` | Below-200% estimate ÷ population for whom poverty status was determined |
| `population_statewide_share` | District total population ÷ the chamber's Pennsylvania total for that election year |
| `population_deviation_from_chamber_mean_pct` | 100 × (district population ÷ chamber mean district population − 1) |
| `population_per_total_sq_km` | District population ÷ full district polygon area, including water |
| `log_population_per_total_sq_km` | Natural logarithm of `population_per_total_sq_km` |

For example, `employment_employed_share` is
`employment_employed_estimate ÷ employment_population_16_plus_estimate`.

The four education shares, four employment shares, and seven poverty-band
shares each sum to one apart from floating-point rounding.

ACS count MOEs are 90% margins. When multiple Census cells are combined, their
MOEs are approximated with root-sum-square; covariance and allocation
uncertainty are unavailable. No MOE is reported for derived shares or rates.
Decennial long-form cell MOEs were not published and are left blank.
