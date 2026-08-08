# Repository agent guidance

Before changing the POC, read:

1. `docs/README.md`
2. `docs/PROJECT.md`
3. `docs/PROOF_STATUS.md`
4. `docs/DECISIONS.md`
5. `docs/TASKS.md`
6. `.agents/private/knowledge/ASSUMPTIONS.md`
7. relevant notes under `.agents/private/research/`

The `docs/` tree is canonical. `.agents/private/` is working memory and must not
override accepted decisions or task evidence. Use `POC###` task IDs in plans and
completion notes. Mark an experiment `done` only when its "Done when" evidence
is saved.

Keep this a proof of concept. Add only the machinery needed to test a current
hypothesis. Prefer transparent Python functions and inspectable Parquet/CSV/JSON
artifacts over services, databases, orchestration frameworks, or UI work.

Never commit downloaded Census, boundary, interim, or generated result data
without an explicit data-versioning and licensing decision. Do not store
secrets or API keys in the repository.

Every input record must preserve producer, exact product, retrieval timestamp,
reference/effective vintage, URL, SHA-256 checksum, access/license terms, CRS,
schema, and geographic universe. A download date is not a boundary vintage.

Every crosswalk must preserve source and target dataset/vintage, method/version,
weighting universe, allocation rows, diagnostics, and validation results. Never
overwrite a previously accepted crosswalk.

