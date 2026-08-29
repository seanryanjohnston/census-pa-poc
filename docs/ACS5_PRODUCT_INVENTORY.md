# Accepted ACS five-year product inventory

`POC014` passed on 2026-08-29. The inventory retains every overlapping ACS
five-year release from 2005–2009 through 2020–2024 rather than preselecting a
single midpoint or model feature.

## Product coverage

`mappings/acs5_products.csv` records 16 products. Every row preserves:

- exact five-year reference start and end dates;
- official release date and release-page URL;
- product-year block-group geography identity;
- total-population estimate `B01003_001E` and margin of error `B01003_001M`;
- total-population universe;
- API dataset, variables-metadata, and geography-metadata URLs;
- per-vintage metadata checksums;
- official Summary File URL and the viable extraction route; and
- availability, processing status, API-key requirement, and typed notes.

The first product covers January 1, 2005 through December 31, 2009 and was
released December 14, 2010. The latest covers January 1, 2020 through December
31, 2024 and was released January 29, 2026. The latest date is the actual
revised release, not the superseded December 11, 2025 schedule.

Official release history:
https://www.census.gov/programs-surveys/acs/news/data-releases.html

Official five-year API documentation:
https://www.census.gov/data/developers/data-sets/acs-5year.html

## Access-route finding

The checksum-frozen Census API geography manifests expose block groups for 12
products, 2013 through 2024. The 2009–2012 API geography manifests omit block
groups even though the ACS five-year detailed products publish block-group
data. Those four rows therefore select the official Summary File route rather
than falsely claiming a uniform API path.

As observed on 2026-08-29, Census requires a valid API key with every data API
request. No key or credential is stored. This does not block the metadata
inventory; `POC015` can use a user-supplied key at runtime or the official
Summary Files.

## Explicit gaps and policy

There is no comparable block-group ACS five-year product in the 1990s. The gap
remains explicit in `mappings/population_periods.csv`; this inventory does not
manufacture an interpolation. It also does not decide which overlapping ACS
release should be used for a training observation. `POC019` will compare each
product's release date with election cutoffs, and downstream modeling decides
feature selection.

## Reproducibility

Run:

```sh
.venv/bin/python -m census_pa_poc.acs_inventory --root .
```

The command validates 19 inventory and metadata gates across 32 frozen public
metadata files. The inventory logical SHA-256 is
`6c369aad01b2ecf58a81fb3ff4824c169a4ce53c070b692d956a8afa864c9525`.
Machine-readable evidence is under `artifacts/poc014/`; downloaded metadata is
ignored under `data/raw/acs5_api_metadata/`.
