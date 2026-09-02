# Direct legislative validation gates

Every accepted partition must pass:

1. Exact source files and plan inputs match frozen SHA-256 checksums.
2. Product, source grain, metric, chamber, plan vintage, and applicable
   elections are explicit.
3. Every supported source has weights summing to one within tolerance, except
   an explicitly typed zero-estimate exception.
4. The expected 203 House or 50 Senate districts are present.
5. The allocated statewide estimate conserves the source total.
6. ACS estimates and 90% MOEs remain separate; the MOE aggregation method and
   omitted uncertainty are declared.
7. No precinct identity or precinct artifact is consumed.
8. No nearest-boundary assignment is used.
9. Crosswalk and result logical hashes are immutable and replay identically.

`POC031` adds metric-specific gates:

- the selected field is exactly PL 94-171 P3 `P0030001`, universe Total
  population 18 years and over;
- LRC fragment P3 sums equal Census File 02 P3 for every parent block;
- VAP never exceeds total population on any fragment;
- the allocation methods and weighting-universe declarations name P3 rather
  than P1;
- both current chambers conserve 10,353,548 VAP and equal the direct fragment
  sums; and
- MOE is explicitly not applicable to the exact decennial count.

`POC034` adds notebook audit gates:

- the Census P1 and P3 Pennsylvania benchmarks are read independently from the
  official block files rather than copied from either chamber result;
- all 203 House and 50 Senate districts are present and each chamber sum has
  zero difference from its state benchmark for both metrics;
- split blocks are discovered from the accepted P1 and P3 crosswalk rows and
  their weights sum to one;
- current-plan P1 and P3 each report one House-split block and no Senate-split
  blocks, with block `421010257002008` assigned to House districts 194 and 200;
- one bounded context map is rendered for each impacted district; both maps
  include the complete impacted pair, label districts 194 and 200 directly,
  and mark the split block on their shared boundary;
- the notebook uses bounded charts and a selected-block fragment map instead
  of a statewide 203-bar or full-plan polygon display; and
- static checks, the full test suite, a live metric-selector check, and an
  executed HTML render pass.
