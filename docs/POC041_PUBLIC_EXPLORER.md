# POC041 public V2 explorer release

Status: **done — deployed and verified**

`PD043` authorizes a public explorer over the accepted `POC039` V2 House and
Senate panels. This bounded release publishes district-level tabular results
and validation evidence, but no source, crosswalk, or district geometry.

## Product paradigm

Use immutable, versioned release directories rather than a mutable `latest`
dataset. The explorer may default to the newest election year inside a release,
but it must keep the release identity visible and let visitors inspect every
supported year. A future successor gets a new directory and compatibility note;
it never silently replaces V2.

The POC039 V2 explorer therefore opens on 2026 and retains all 18 even-year
elections from 1992 through 2026. This combines a useful current first view with
the historical context that makes the panel valuable.

## Published artifacts

| Artifact | Rows | SHA-256 |
|---|---:|---|
| House district-election panel | 3,654 | `46d7260b42bd52b45c3d271f28ca1d45a0e0b9a99c48d8bf87a3a857a9bc2e55` |
| Senate district-election panel | 900 | `59641c43353ed1a295119428a4b62f75af4269be97e13dfa3a6341aaedbdbe58` |
| Data dictionary | 95 fields | `18c56238eb041f12649f3d6080efad4ab9b5068d64d0ea84f4dc8553e40ae34a` |
| Source selections | 72 records | `1c0e525e25b3691ab930660d8b6f5c8c0dcdbdadbdbf5fd2db3fa1b2e21be2b9` |
| Model-export QA | 20 passing checks | `4681c9aae1ec1728e2a4dd81c224c8e22f66e347034807d6425013e1fce61600` |

The release also includes its usage notes, metric calculations, manifest, and
`SHA256SUMS`. The two panel hashes match the accepted POC039 evidence and the
companion generator replay at commit
`a564ffefb017277caed7fe6e775ab92b1b4bd246`.

## Included fields and sensitivity

The 95-column panels include district and election identifiers, plan identity,
cutoff-safe source identity and periods, total population, education,
employment, poverty, derived rates, typed margin-of-error status, total polygon
area, and density. The public files contain aggregate district statistics only:
no person, household, respondent, confidential, credential, or database record
is present.

The uncompressed public site is limited to 6 MiB for this increment; the
checked release is approximately 5 MiB.

## Sources, attribution, and terms

- Demographic inputs are U.S. Census Bureau 1990 Census, Census 2000, decennial
  population, and 2009–2024 ACS five-year products. They are public federal
  statistical data. Cite the U.S. Census Bureau and retain the product, period,
  universe, and uncertainty fields.
- District identity and total polygon area derive from official 1991, 2001,
  2012 Revised Final, and 2021 Final Pennsylvania Legislative Reapportionment
  Commission plans. Cite the Commission and the applicable plan.
- The Commission provides official GIS downloads publicly, but an explicit
  redistribution license was not found. This increment therefore does not copy
  or derive a redistributable geometry layer, block equivalency, or source file.
- The repository has not yet selected a project-level code or data license.
  Public availability supports inspection and download but must not be described
  as an open-data license grant. Source materials retain their own terms.

This scoped authorization does not resolve the broader geometry, crosswalk,
corrected-fragment, raw-source, or third-party map-asset release boundary.

## Explorer behavior

The browser loads one chamber panel at a time and provides election, measure,
district, and comparison-year controls. It shows district history with breaks
at plan changes, chamber rankings, source periods, plan identity, uncertainty
status, and direct downloads. It uses no database, server API, external script,
analytics, cookie, or credential.

GitHub Actions deploys only `site/`. Every third-party action is pinned to an
immutable commit SHA; the workflow verifies release hashes and JavaScript syntax
before uploading the Pages artifact.

## Deployment evidence

- Public site: <https://seanryanjohnston.github.io/census-pa-poc/>
- First successful workflow run: <https://github.com/seanryanjohnston/census-pa-poc/actions/runs/33714567011>
- Local verification: all release hashes, Node syntax, Ruff, the marimo static
  check, and all 81 tests pass.
- Live verification: the deployed site loads the selected chamber, election,
  metric, district, comparison, 18-point history, plan legend, rankings,
  provenance, and versioned download links from the public URL.
