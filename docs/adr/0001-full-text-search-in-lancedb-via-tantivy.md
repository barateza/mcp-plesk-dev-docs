# 1. Full-text search lives in LanceDB via Tantivy

- **Status:** Accepted

## Context

Hybrid retrieval combines vector similarity with keyword search. A standalone FTS
engine would be a second index that has to be kept in sync with every chunk write,
and would need its own backup, recovery and schema-migration story. Terms in
`GLOSSARY.md`: **Chunk**, **RRF**.

## Decision

Full-text search is provided by **Tantivy inside LanceDB**, indexing the `text` and
`filename` columns. There is no separate FTS engine.

## Consequences

- One store owns both the vector and FTS indexes, so a chunk write updates both in
  one place.
- Hybrid (vector + FTS) is the default search path; `RRF` merges the two result lists.
- Any schema change must preserve the Tantivy FTS index, and the FTS index must be
  verified as rebuilt and keyword-exact after every indexing run.

_Provenance: migrated from the repo's earlier `CONTEXT.md` "Key Decisions"._
