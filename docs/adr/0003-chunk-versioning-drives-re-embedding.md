# 3. Chunk versioning drives re-embedding

- **Status:** Accepted

## Context

Chunks are content-hashed and embedded as vectors. Incremental refresh
(`reset_db=False`, the default) skips re-embedding identical content, which is what
keeps indexing cheap. But a change to the chunking *logic* — structural HTML
normalization, chunk boundaries, or embedding enrichment — can leave unchanged
source text producing different chunks, so a content hash alone would wrongly report
"nothing to do". Term in `GLOSSARY.md`: **Chunk**.

## Decision

A chunk version (`CHUNK_VERSION = "v15"`) is part of change detection. It is bumped
**only** when structural HTML normalization, chunking boundaries, or embedding
enrichment are modified.

## Consequences

- Bumping the version forces re-embedding of the corpus — a deliberate, expensive act.
- Without a bump, incremental refresh correctly skips unchanged sources; a
  fingerprint change implicitly requires one.
- Editing chunking behaviour carries a re-indexing cost that must be planned for, not
  discovered at query time.

_Provenance: migrated from the repo's earlier `CONTEXT.md` "Key Decisions"._
