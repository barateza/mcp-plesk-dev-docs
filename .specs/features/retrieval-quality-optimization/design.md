# Design: Retrieval Quality Optimization

## 1. Technical Strategy

### Task A: Hybrid Search (LanceDB FTS)
*   **FTS Index:** Enable Tantivy-based FTS on `text` and `filename` columns during ingestion.
*   **Querying:** Run both `table.search(vec)` and `table.search(text)`.
*   **RRF Merger:** Combine results using Reciprocal Rank Fusion: $Score = \sum \frac{1}{k + rank}$.

### Task B: Metadata Injection
*   **Implementation:** In `plesk_unified/chunking.py`, update `create_chunks` to accept `title` and `breadcrumb`.
*   **Format:** Prepend to the text: `[Title: {title} | Path: {breadcrumb}] \n\n {content}`.
*   **Impact:** This increases the "relevance signal" for smaller models like BGE-Small.

### Task C: Sentinel Window (5 sentences)
*   **Change:** Adjust `sentence_window` parameter in `plesk_unified/chunking.py` for HTML sources.
*   **Storage:** Ensure adjacency IDs remain valid for 5-sentence chunks.

### Task D: Neighborhood Retrieval
*   **Retrieval Logic:** In `server.py`, for the top-3 ranked results, fetch records where `chunk_id` is `id-1` or `id+1` from the same file.
*   **Merging:** Concatenate neighbors to the main chunk text before sending to formatting/LLM.

### Task E: API Metadata
*   **Regex:** `(GET|POST|PUT|DELETE|PATCH) \/api\/v2\/[a-z0-9\/\-\_{}]+`.
*   **Storage:** New optional column `endpoint` in LanceDB schema.
*   **Querying:** Use `WHERE endpoint = ...` as a pre-filter if the query contains a slash.

### Task F: Structural Parsers
*   **PHP:** Use a simplified recursive regex or simple state machine to detect `class { ... }` and `function name() { ... }` blocks.
*   **JS:** Use a similar approach for ES6 modules and exports.

## 2. Infrastructure Changes
*   **LanceDB Schema:** Update `CHUNK_SCHEMA` in `plesk_unified/chunking.py` to include `endpoint` and ensure `id` is searchable.
*   **Indexing:** Re-indexing (`--refresh`) is mandatory for Tasks A, B, C, and E.
