# 1. Full-text search lives in LanceDB, on its native inverted index

- **Status:** Accepted
- **Amended:** 2026-11-09 — engine changed from Tantivy to LanceDB's native FTS

## Context

Hybrid retrieval combines vector similarity with keyword search. A standalone FTS
engine would be a second index that has to be kept in sync with every chunk write,
and would need its own backup, recovery and schema-migration story. Terms in
`GLOSSARY.md`: **Chunk**, **RRF**.

LanceDB 0.40 removed Tantivy-backed FTS — `use_tantivy=True` now raises
`ValueError: Tantivy-based FTS has been removed` — and stops reading legacy
`_indices/fts` directories. The original engine is therefore only reachable by
pinning the whole storage engine to an older release.

## Decision

Full-text search is provided by **LanceDB's native inverted index**, built with
`create_index("text", config=FTS(...))`. Native indexes cover a single column, so
only `text` is indexed: filenames are opaque (`79359.htm`) and carry no
BM25-relevant terms. There is still no separate FTS engine.

Measured on the 13,795-chunk corpus (2026-11-09, CPU-only laptop):

| backend | build | index size | median query |
| --- | --- | --- | --- |
| tantivy-py (standalone) | 0.30 s | 5.3 MB | 1.2 ms |
| SQLite FTS5 | 0.32 s | 13.2 MB | 20.9 ms |
| **Lance native** | **0.80 s** | **~2.2 MB** | **5.4 ms** |

All three returned the same top-1 document for every benchmark query. Tantivy-py is
faster per query, but it is a second index that must be kept in sync, and a few
milliseconds is invisible next to cross-encoder reranking over the candidate set.

## Consequences

- One store owns both the vector and FTS indexes, so a chunk write updates both in
  one place.
- Hybrid (vector + FTS) is the default search path; `RRF` merges the two result lists.
- Queries must pass `query_type="fts"` explicitly. The default `"auto"` embeds the
  string and runs a **vector** search even when an inverted index exists, which
  silently made the merge vector-only.
- The FTS index must be rebuilt after every indexing run, and a build failure must
  fail the job instead of being logged and swallowed.
- Native FTS ranks chunks, so candidates are capped per file before `RRF`.

_Provenance: migrated from the repo's earlier `CONTEXT.md` "Key Decisions";
amended when lancedb 0.40 removed the Tantivy backend._
