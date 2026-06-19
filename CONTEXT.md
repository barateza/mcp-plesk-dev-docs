# CONTEXT — mcp-plesk-dev-docs

An MCP (Model Context Protocol) server that provides semantic search over Plesk developer documentation, powered by hybrid vector+FTS retrieval, cross-encoder reranking, and 4-bit TurboQuant quantization.

## Domain Glossary

| Term | Definition |
|------|-----------|
| **Source** | A category of documentation (`api-rpc`, `cli-linux`, `extensions-guide`, `sdk`, `stubs`) with its own acquisition strategy (git clone or zip fetch) |
| **Chunk** | A segment of a source document, content-hashed and embedded as a vector. The chunking pipeline produces records with metadata (title, category, breadcrumb, doctype) |
| **Profile** | A pre-configured model pipeline (`light`, `medium`, `full`, `full-tq`) trading off RAM, latency, and quality |
| **RRF** | Reciprocal Rank Fusion — merges vector and FTS result lists into a single ranking |
| **TurboQuant** | 4-bit vector quantization using Lloyd-Max + QJL residual correction, applied to corpus vectors while queries stay full-precision |
| **Relevance Gate** | A profile-specific minimum `_relevance` threshold applied after reranking |
| **Neighbor Expansion** | Fetching adjacent chunks (window=1) for top-5 results to provide surrounding context |
| **Sampling** | MCP sampling protocol — the server asks the client's LLM to synthesize an answer from retrieved chunks with inline citations |

## Key Decisions

- **FTS via Tantivy** on `text` and `filename` columns, not a separate engine
- **PID-file lock** prevents concurrent LanceDB access
- **Chunk versioning** (`CHUNK_VERSION = "v15"`) forces re-embedding when chunking logic changes
- **Off-the-shelf models**, no custom fine-tuning — embeddings from BAAI/bge series, reranker from sentence-transformers
