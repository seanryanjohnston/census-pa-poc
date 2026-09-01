# POC035 demographic person-count status

Status: **deferred after accepted 2020 P2 stage**

`POC035` covers remaining decennial and ACS VAP, CVAP, age, race/ethnicity,
and foreign-born/citizenship. The completed substage is the 2020 PL
94-171 P2 race/ethnicity bridge on both 2021 Final plans.

## Completed: current-plan 2020 P2

The substage allocates six mutually exclusive categories:

- Hispanic or Latino of any race;
- non-Hispanic White;
- non-Hispanic Black;
- non-Hispanic American Indian and Alaska Native;
- non-Hispanic Asian plus Native Hawaiian and Other Pacific Islander; and
- non-Hispanic some-other-race plus multiracial.

Directly published P2 parents are selected where they match a category. Only
Asian+NHPI and other+multiracial are exact sums. The categories conserve the
13,002,700 P2 total; they are aggregates and are never interpreted as records.

The LRC corrected fragments publish every selected P2 cell. Their sums match
the official Census block P2 cells for every parent and category. The only
split parent is House block `421010257002008`. Eight nonzero parent/category
rows use their own published fragment P2 support. Four categories are zero on
the entire parent; their two geometric rows use a typed atomic-area fallback,
but the allocated estimate remains zero. The Senate has no split parent.

| Check | House | Senate |
|---|---:|---:|
| Districts | 203 | 50 |
| Crosswalk rows (block × category × district) | 2,021,916 | 2,021,910 |
| Split parent/category rows | 12 | 0 |
| Published nonzero fragment-support rows | 8 | 0 |
| Zero-category area-fallback rows | 4 | 0 |
| Sum of six statewide categories | 13,002,700 | 13,002,700 |

There is no sampling MOE for these decennial counts. Disclosure-avoidance and
nonsampling limitations remain. The crosswalk explicitly declares that it uses
neither P1 nor P3 weights.

Two complete executions replayed identically:

| Artifact | Logical SHA-256 |
|---|---|
| Category-specific crosswalk | `319b11213752c2cf5502086969e710baece2fe13a36ddbeb5a3b1efa0bdf0256` |
| District results | `86fbca77e1fb3b3303df6924ce95df3da6323f58bf49c01b4786e72279ee4962` |
| Direct fragment comparison | `6e14cc4780f01430afcf8d3a651488aa1d4959049281beeef50d1aee73a152f4` |

Machine-readable evidence is in `artifacts/poc035/race_2020_qa.json`.

## Remaining

These stages are deferred and do not block the complete `POC039` model export:

- 1990, 2000, and 2010 decennial VAP;
- all cutoff-eligible ACS `B01001` VAP and age products;
- the 16 CVAP special-tabulation products;
- decennial and ACS race/ethnicity outside the completed 2020 stage; and
- ACS `B05001` nativity/citizenship.

The currently local ACS extracts contain only `B01003`; the exact additional
tables must be downloaded and checksum-frozen before those stages can run.
