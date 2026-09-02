# Decision register

Superseded precinct-era decisions remain available from Git history.

| ID | Date | Decision | Consequence |
|---|---|---|---|
| `PD028` | 2026-08-30 | Replace the active precinct target with direct Census/ACS-to-State-House-and-State-Senate crosswalks. | No direct partition may consume precinct identity or a precinct artifact. |
| `PD029` | 2026-08-30 | Accept all 78 direct total-population partitions across 20 products and applicable 1991–2021 plans. | Preserve source grain, plan applicability, weighting, fallback, uncertainty, QA, and immutable hashes per partition. |
| `PD030` | 2026-08-31 | Isolate the precinct route and make direct legislative artifacts the only active explorer and command targets. | Direct-required parsers and source manifests stay active even when they originated in precinct experiments. The temporary archive created by this decision was later removed under `PD042`. |
| `PD031` | 2026-08-31 | Accept 2020 PL 94-171 P3 `P0030001` voting-age population as the first additive metric beyond total population. | Use published LRC fragment P3 support in a separately versioned crosswalk; never relabel P001 weights. No ACS MOE applies to this exact decennial count. |
| `PD032` | 2026-08-31 | Make metric universe part of the explorer's partition identity and controls. | Total-population products and 2020 VAP cannot collide; VAP is offered only for the two accepted current-plan partitions and exposes its P3 universe and no-MOE treatment. |
| `PD034` | 2026-08-31 | Make the primary notebook a compact audit of the direct route for the 2021 Final plans used in 2026. | Read the P1 and P3 Pennsylvania benchmarks independently from the Census PL block files; show House and Senate reconciliation together; derive split blocks only from accepted metric-specific crosswalks; replace the large statewide map and hundreds-of-bars chart with compact distributions, paginated tables, and a one-block fragment map. Historical accepted products remain available as generated data and tested helpers, not as primary notebook controls. |
| `PD036` | 2026-08-31 | Use a stable detailed-table basis for longitudinal education and employment comparisons across the full 2009–2024 ACS five-year series. | `B15002` supplies education for every product; `B23001` supplies four mutually exclusive employment-status categories for every product. `B15003` and `B23025` remain overlap-validation references, not canonical inputs. Summed-cell MOEs use RSS and may differ from the MOEs of the directly published comparison aggregates because covariance is unavailable. |
| `PD037` | 2026-08-31 | Preserve the continuous employment concept with an explicit publication-grain/table bridge after bulk-file validation disproved a single block-group table route. | Use tract-level `B23001` in 2009, block-group `B23001` in 2010, and direct block-group `B23025` from 2011 onward. The four categories are equivalent; validate `B23001` against `B23025` where both are published. Retain direct `B23025` MOEs rather than replacing them with RSS-derived `B23001` MOEs. This supersedes the single-table employment consequence of `PD036`; its full-series `B15002` education decision remains accepted. |
| `PD038` | 2026-08-31 | Use the consistently published tract grain—not zero-filled legacy block-group placeholders—for the full `B23001` employment series. | Allocate tract estimates in every 2009–2024 product using same-product `B01003` block-group population composed with the accepted block-group/plan support. Validate `B23001` point estimates against `B23025` after aggregating its block groups to tract; retain `B23001` RSS MOEs for the canonical series. This supersedes the erroneous 2010 block-group and 2011+ source switch in `PD037`; the stable `B15002` education decision remains accepted. |
| `PD039` | 2026-08-31 | Accept `C17002` as the stable 2009–2024 poverty-ratio source and accept all 168 cutoff-eligible socioeconomic metric/product/plan/chamber partitions under `POC036`. | Preserve the seven directly published `C17002` bands and their MOEs; use cell 1 only as the parent; derive below-100% and below-200% shares after allocation by summing compatible bands. Education and poverty use accepted block-group/plan support; employment uses the tract bridge in `PD038`. All district values remain modeled allocations. |
| `PD040` | 2026-09-01 | Close the POC with complete model-ready CSV panels rather than requiring every inventoried P0 family. | Export one wide row per House or Senate district and 1992–2026 election year. Use the latest source released by the election when possible; when no socioeconomic source yet existed, use the earliest ACS five-year product as an explicitly typed future backfill on the election's actual plan. Include only complete, defensible metrics; defer incomplete demographic and household/housing families. Preserve Parquet proof artifacts as upstream evidence. Total-polygon-area density is allowed only under that exact label and must not be presented as Census land-area density. |
| `PD041` | 2026-09-01 | Prohibit post-election reference periods in the model panel. | Supersede the future-backfill allowance in `PD040`. Every included source period must end on or before the election; product release must also precede the election. Use prior decennial long-form anchors where their concepts bridge cleanly, otherwise omit the unsupported metric rather than leak future information. Audit population and geometry-derived features under the same temporal rule. |
| `PD042` | 2026-09-02 | Reduce the closed POC to the direct population proof, QA totals, current notebook, and v2 exports. | Rely on Git history for superseded experiments; keep required source manifests as canonical mappings rather than generated artifacts; retain only final population, notebook, and v2 export QA evidence. |

## Accepted limitations

- Official inter-decennial relationship files provide geographic relationships,
  not population weights.
- Historical split-source results using area support are modeled allocations.
- ACS target MOEs use weighted source components combined by root-sum-square;
  covariance and allocation-weight uncertainty are unavailable.
- 1990 STF3A and Census 2000 SF3 long-form values are sample estimates whose
  cell-level MOEs were not published; v2 leaves those MOEs blank and types the
  limitation rather than using zero.
- Two zero-estimate, water-only 2010 block groups outside the official 2001
  House polygons remain typed unassigned exceptions.
- Publication remains blocked on a redistribution-terms review, not on the
  analytical proof.
