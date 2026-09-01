# Next steps

`POC034` is complete. The primary notebook now focuses on the 2021 Final plans
used in 2026. For both P1 total population and P3 voting-age population, its
203 House and 50 Senate district sums reconcile exactly to a Pennsylvania
benchmark read independently from the official Census PL block files. The one
House-split parent block is exposed through a compact allocation bar, table,
and corrected-fragment map; the Senate has no split parent block. The accepted
historical products remain in their immutable artifacts and tested helpers.

`POC033` froze the exact tables, variables, universes, vintages, release
cutoffs, support candidates, aggregate transformations, and MOE treatment for
the larger candidate bundle. `POC036` is complete; the unfinished portions of
`POC035`, `POC037`, and `POC038` are now documented production extensions. P1
and P3 weights still cannot be assumed valid for another universe.

The remaining `POC035` demographic stages and `POC037` household/housing proof
are deferred. The current-plan 2020 P2 race/ethnicity substage remains accepted
and reusable, but partial families are not forced into the complete model panel.

`POC036` is complete. Continuous block-group `B15002`, tract `B23001`, and
block-group `C17002` sources cover all 16 ACS products. The proof allocates
education, employment, and poverty to all 168 cutoff-eligible
metric/product/plan/chamber partitions, conserves every additive category,
retains estimate/MOE paths separately, and passes all 816 checks plus identical
replay. Statewide and six fixed-current-plan sample trends remain a compact
diagnostic view of the full result.

`POC039` is complete and closes the POC. The corrected handoff is under
`data/exports/model_features/v2/`: 3,654 House rows and 900 Senate rows, each
with 95 columns and one unique district/election key for 1992–2026. Every
source period and product release precedes its election. The 1990 STF3A and
2000 SF3 long-form anchors replace the rejected early ACS future backfill;
their unpublished cell-level MOEs remain blank and explicitly typed. All
acceptance checks and byte-identical replay pass.

Any next work is production hardening rather than a POC gate: resume complete
demographic or household/housing routes, derive Census land-area density,
review source redistribution terms, or continue user-guided explorer/manual
quality checks.

Before external publication, separately review the redistribution terms for
the Pennsylvania LRC plan and corrected-fragment inputs. This does not block
local analytical use or replay.
