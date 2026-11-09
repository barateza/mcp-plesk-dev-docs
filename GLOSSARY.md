# Glossary

Shared vocabulary for `mcp-plesk-dev-docs`. When naming a domain concept — in an
issue title, a refactor proposal, a hypothesis, a test name, an ADR — use the
term exactly as defined here. See `docs/agents/domain.md` for the consumer rules.

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
