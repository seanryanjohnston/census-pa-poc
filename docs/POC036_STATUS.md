# POC036 socioeconomic person-count status

Status: **done — 168 cutoff-eligible partitions accepted with identical replay**

`POC036` proves continuous 2009–2024 ACS five-year education, employment,
and poverty-ratio distributions for every accepted product/plan pairing in
both legislative chambers. The immutable full result contains 127,512
district-category rows across 168 metric/product/plan/chamber partitions.

A compact trend view holds the target geography fixed at the 2021 Final plans
so changes are not mixed with redistricting. Its samples are House 68, 87, and
194 and Senate 3, 25, and 31. State rows are directly published; every district
row is a modeled allocation and is labeled as such.

## Source and transformation contract

- Education uses block-group `B15002` in all 16 products. Four bands sum only
  mutually exclusive sex-by-attainment cells. `B15003` is an overlap reference.
- Employment uses tract `B23001` in all 16 products. Four categories sum only
  mutually exclusive age/sex/status leaves. Legacy Summary Files contain
  zero-filled `B23001` block-group placeholders; they are not observations.
- Poverty uses block-group `C17002` in all 16 products. It is already an
  aggregated C table: cells 2–8 and their published MOEs are preserved as the
  seven output bands. Cell 1 is used only as the conservation denominator.
- Below-poverty and below-200%-of-poverty shares are derived after allocation.
  The first sums the first two `C17002` bands; the second sums the first six.
  Neither allocates a published percentage or claims detail beyond `C17002`.
- Education and poverty use the accepted product-vintage block-group/plan
  support. Employment composes same-product `B01003` block-group population
  with that support and normalizes within tract. Zero-population tracts have
  zero `B23001` counts and contribute nothing.
- Summed-cell MOEs use root-sum-square (RSS). District MOEs apply weights and
  RSS again. Covariance and allocation-weight uncertainty are unavailable.
  Shares and rates have no reported MOE.

The overlap gate contains 48 state/small-area comparisons: `B15002` versus
`B15003` for 2015–2024 and tract `B23001` versus tract-aggregated `B23025` for
2011–2024. Every point estimate matches exactly. MOEs are not required to
match; the maximum observed absolute difference is 3,235.082 because one path
uses published aggregate MOEs and the other uses RSS.

## Statewide change

All values are percentages of the compatible universe. Changes compare the
2005–2009 and 2020–2024 products and are percentage points.

| Metric | 2005–2009 | 2020–2024 | Change |
|---|---:|---:|---:|
| Bachelor's degree or higher, population 25+ | 25.97% | 35.16% | +9.19 |
| Below high school, population 25+ | 13.13% | 7.87% | -5.26 |
| Employment-to-population ratio, population 16+ | 58.69% | 59.32% | +0.63 |
| Civilian unemployment rate | 6.76% | 5.26% | -1.50 |
| Labor-force participation, population 16+ | 63.05% | 62.69% | -0.36 |
| Below poverty line, poverty-status-determined population | 12.10% | 11.71% | -0.39 |
| Below 200% of poverty, poverty-status-determined population | 28.87% | 26.59% | -2.28 |

Adjacent ACS five-year estimates overlap by four years and are not independent
annual observations. Read the intermediate points as a smoothed trend, not as
year-over-year changes.

## Sample-district endpoint changes

| Chamber | District | Bachelor's+ | Below high school | Employment/population | Civilian unemployment | Labor-force participation | Below poverty | Below 200% poverty |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| House | 68 | +4.01 | -5.66 | -1.72 | -2.52 | -3.40 | -2.35 | -6.16 |
| House | 87 | +12.66 | -2.73 | -2.58 | -2.09 | -3.86 | +0.54 | +1.06 |
| House | 194 | +17.90 | -7.12 | +5.05 | -1.08 | +4.54 | -1.89 | -3.65 |
| Senate | 3 | +9.79 | -9.47 | +7.31 | -6.68 | +4.01 | -3.67 | -5.14 |
| Senate | 25 | +6.67 | -4.59 | -0.88 | -2.19 | -2.26 | -1.21 | -3.22 |
| Senate | 31 | +7.25 | -5.29 | -0.74 | -1.73 | -2.02 | -1.23 | -2.25 |

These are fixed-2021-plan diagnostics. They inherit tract/block-group
homogeneity limitations and are not published legislative-district estimates.
The full artifact also retains every individual `C17002` band, not just the two
derived thresholds summarized here.

## Acceptance evidence

The run passes 816 checks:

- 48 source-row category/parent conservation checks;
- 48 direct state category/parent conservation checks;
- 672 district coverage, state conservation, within-district conservation,
  and cutoff-provenance checks across 168 partitions; and
- 48 education/employment overlap-reference checks.

The official-source manifest has 136 table/grain records. The QA artifact also
hashes the metric definitions, product/applicability mappings, plan mapping,
source manifest, and all 18 accepted crosswalk files. A second complete run
reported the versioned legislative artifact as `reused_identical`.

| Artifact | Logical SHA-256 |
|---|---|
| Full legislative partitions | `6a0b18245d16be2cb39a7dd4db1bb245ee9e992ff5053e598145ce45d4bceff2` |
| State/sample category counts, MOEs, and shares | `0016e2637fe65814a6ce340260bb1e68f7aae90ff660852c90c541ebe7196420` |
| Derived employment and poverty rates | `775c33194e6bc97d0e0b89814c8cfd5774f2cd6cb145e68de84c0085efafef64` |
| Endpoint change summary | `75384a321dee7aa3ca687d413c0e1e2541876049e8442305362cf3771a8e7287` |

The exact definitions used by the accepted export are in
`mappings/socioeconomic_metric_definitions_v1.csv`. The final v2 export QA is
in `artifacts/poc039/model_export_qa_v2.json`.
