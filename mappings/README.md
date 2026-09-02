# Active planning mappings

- `legislative_plans_v1.csv` freezes the eight official House/Senate plan
  sources, checksums, district fields, vintages, and election applicability.
- `legislative_population_partitions_v1.csv` lists the 39 accepted
  product/plan-vintage combinations. The direct code expands these to 78 House
  and Senate partitions without precinct identity.
- `acs5_products.csv` inventories the 16 accepted ACS five-year releases,
  exact B01003 estimate/MOE fields, release dates, access routes, and metadata
  hashes.
- `population_periods.csv` summarizes the implemented total-population source
  families and direct legislative routes.
- `legislative_metrics_v1.csv` identifies the separately proven 2020 P3 VAP
  partition, exact universe, current-plan applicability, and no-MOE treatment.
- `socioeconomic_metric_definitions_v1.csv` freezes the three aggregate
  definitions used by the v2 exports. Education uses full-series block-group
  `B15002`; employment uses
  full-series tract `B23001` and never treats its zero-filled legacy
  block-group placeholders as observations; poverty preserves the seven
  directly published block-group `C17002` bands and uses its parent only for
  conservation and post-allocation shares.
- `model_election_years_v1.csv` is the active 18-cycle House/Senate panel
  spine. It records exact general-election dates, the plan used by each
  chamber, and the alternating regular State Senate contest class without
  reintroducing archived precinct fields.
- `crosswalk_methods.csv` lists only active direct method families.
- `source_manifests/` contains immutable raw-input provenance needed to replay
  the direct population and export pipelines. Generated QA belongs under
  `artifacts/`, never here.

Mappings are executable planning inputs, not replacements for source manifests
or partition QA. No active mapping contains a precinct target or selects a
precinct-derived product.
