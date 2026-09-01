# Accepted representative ACS block-group method result

`POC015` passed on 2026-08-29. It proves an explicit estimate and margin-of-error
allocation path for the 2011–2015 ACS five-year total-population product on the
fixed 2021 LRC precinct target and 2012 Revised Final State Senate plan.

## Frozen inputs

| Input | Exact product / vintage | SHA-256 |
|---|---|---|
| Geography records | 2011–2015 ACS five-year Pennsylvania Summary File geography, summary level 150 | `74bcf0e2ae5c2591aaf82470c6b71e45618877e19db005f3053a714cba8e5748` |
| Estimate/MOE records | 2011–2015 ACS five-year Pennsylvania Summary File sequence 0003 | `fb438d716f48b89fa2721ea60a74c2cea1d11ca9b33c99d0cde2500770e18334` |
| Sequence lookup | 2015 ACS five-year sequence/table-number lookup | `263983853a1bb1a35a5ba7ec7d910cdcf052233e569bc7aa9a78517cc4a5c5dc` |
| Geography layout | 2015 ACS five-year geography templates | `b2ce924dd7f81b84e0da856e88e70567616c2d252da7db088af0d37df5b52f84` |
| Source geometry | 2015 TIGER/Line Pennsylvania block groups | `c0196af49134903a652ded0b050045654a3cbdb8d4f4e4811180ac964e36af3a` |
| Population support | 2010 Census Pennsylvania PL 94-171 | `3cf2460ea17d1be087d9b12700e45962b164f6233f8c1071ddc67ab55392951a` |
| Support relationship | Official 2010-to-2020 Pennsylvania block relationship file | `6e8ac323b98bf7259dac59ae7000c14fa72ce38207f77648d08645bbea29a323` |
| Fixed-target geometry | 2021 LRC Data Release 1b Data Set 1 | `14187001c627c6a16bf967415059408c4ef7007d366fd9105b5be30763250e3b` |
| Senate atomic target | Accepted `pa_senate_2012_revised_final_fixed_precinct_overlay_v3` | logical `97a0c5c2f382174363de8ca7506dbe73f27f73901b4c495f2a2cf1ee4a74bc2b` |

The sequence lookup places table B01003 in sequence `0003` at one-based start
position 130. Summary level `150` yields 9,740 unique Pennsylvania block groups
and joins exactly to all 9,740 TIGER geometries. `B01003_001E` totals
12,779,559; all `B01003_001M` values are present and nonnegative. The product
covers 2011–2015 and was released December 8, 2016.

## Compared methods

`simple_atomic_area_acs5_2015_v1` directly intersects the 2015 block-group
geometry with:

`fixed 2021 LRC precinct ∩ 2012 Revised Final Senate district`

in EPSG:5070 and normalizes over covered area.

`census2010_population_atomic_acs5_2015_v1` uses 2010 Census block population
as a pre-period support surface. Each block reaches the atomic target through
the accepted official 2010-to-2020 relationship-area and geometry-only 2020
atomic bridge. The method sums block support by 2015 block group and target,
then normalizes within each block group. Nine block groups have zero 2010
population and use an explicit simple-area fallback. Their ACS estimate is also
zero; their source MOEs sum to 90 linearly.

Under `PD021`, the population-informed route is the accepted representative
method because it uses a population support surface that predates the ACS
reference period. The simple-area route remains the required diagnostic. This
choice is not automatically valid for earlier ACS products for which 2010
support would postdate part or all of the reference period.

## Estimate and margin-of-error paths

The source estimate and its 90% MOE use the same fixed crosswalk weight but
remain separate fields:

- allocated estimate = source estimate × weight;
- allocated source MOE component = source MOE × weight; and
- target MOE = square root of the sum of squared source MOE components.

The root-sum-square rule is the Census Bureau approximation for sums when
covariance is unavailable. The derived target MOEs also omit uncertainty in the
modeled allocation weights. They are approximate and are never summed or
described as population counts. Every source estimate and source MOE
reconstructs after allocation within the declared numerical tolerance.

## Results and QA

- Both methods cover all 9,740 source block groups, 9,178 fixed precincts, 67
  source counties, and all 50 Senate districts.
- Both conserve the 12,779,559 estimate at state and source-county levels.
- The simple route emits 53,928 allocation rows. All source representative
  points are covered. Four sources are below 99% geometric coverage, none is
  below 90%, and the minimum is 97.5813%; normalization remains explicit.
- The population-informed route emits 32,365 allocation rows, with nine typed
  zero-support area fallbacks and no nearest assignment.
- The estimate methods differ in 8,896 precincts by 2,123,664.219 total
  absolute persons; the largest precinct difference is 7,614.012.
- Precinct MOEs differ by 267,267.437 total absolute units; the largest
  difference is 616.443.
- All 50 Senate districts have estimate differences totaling 13,447.865 in
  absolute value; the largest district difference is 1,822.347.
- Senate MOEs differ by 1,814.680 total absolute units; the largest difference
  is 136.639.
- No nearest-boundary assignment is used.

All 41 QA checks pass. A second complete run reused all five immutable
artifacts identically. Logical SHA-256 values are:

| Artifact | Logical SHA-256 |
|---|---|
| Atomic crosswalks | `6a9b42c3d08223fb40329c6b196a08f7cb3c0f1b59bae2ecc4faeafbfde9d593` |
| Fixed-precinct results | `e0254aefaad6510dcfbe180895821e5ea37140be4ed0ff53479c59b2152e6b10` |
| Senate results | `28eab1dc4c77696e6abc79e5614036c4bfe346320e7a8e7b88fcdac1d9dd9262` |
| Precinct method comparison | `2024a60513bbce187f6fc3827bb4ff37a771a4997008f2884e104626b442f4c3` |
| Senate method comparison | `43b309895e50394d2f007b29290b40d0b6e55fe7ca4d2ef0467abcd7267f0e14` |

Machine-readable evidence is under ignored `artifacts/poc015/`; derived data
remain ignored under `data/processed/statewide_acs5_2015/` pending a publication
and source-terms decision.

## Limits

- The support surface describes 2010 population location, not the unknown
  within-block-group distribution during 2011–2015.
- The target MOEs are approximations that exclude covariance and allocation-
  weight uncertainty. Variance replicate estimates would be a stronger future
  comparison if available for the required table/geography.
- The fixed precinct target is counterfactual for the ACS period.
- This task proves one representative product and a reusable method family.
  `POC019` subsequently established availability and `POC016` ran every
  accepted pairing under the support regimes recorded in `PD023`.
