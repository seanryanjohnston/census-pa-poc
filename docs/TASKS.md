# Maintenance record

The proof of concept closed with `POC039`. Accepted outcomes and limitations
are recorded in `PROOF_STATUS.md`, and the decisions that produced them remain
in `DECISIONS.md`. There is no active experiment backlog.

Status values are `in-progress` and `done`.

| ID | Status | Work | Done when |
|---|---|---|---|
| `POC040` | done | Remove obsolete archive and artifact surfaces; condense the closed POC history and separate canonical replay inputs from generated evidence. | The checkout contains only direct-route code and four current QA artifacts; required replay manifests live with canonical mappings; obsolete references are gone; Ruff, all 78 active tests, the marimo check, and manifest verification pass. |
| `POC041` | in-progress | Publish the accepted `POC039` V2 aggregate panels through a static public data explorer in this POC repository. | A versioned, checksum-verified release and browser-only explorer are committed; GitHub Actions deploys only the bounded site artifact; the public URL is verified for loading, filtering, comparisons, downloads, accessibility, responsive layout, and absence of secrets or excluded geometry. |
