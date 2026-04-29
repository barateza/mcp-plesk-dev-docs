# MCP Components Reference

Detailed reference for Model Context Protocol (MCP) components exposed by `mcp-plesk-unified`.

---

## Tools

### Search & Indexing
- **`search_plesk_unified`**: Primary semantic search across all sources.
  - *Args*: `query` (string), `category` (optional: `guide`, `api`, `cli`, `php-stubs`, `js-sdk`).
  - *Behavior*: Hybrid Search -> Rerank (top 50) -> Neighbor Retrieval -> Optional Sampling.
- **`refresh_knowledge`**: Synchronous index sync. Skips unchanged files via fingerprinting.
  - *Args*: `target_category` (default: `"all"`), `reset_db` (bool).
- **`trigger_index_sync`**: Asynchronous version of `refresh_knowledge`. Returns `job_id`.
- **`check_sync_status`**: Polls status of a background job via `job_id`.

### Management
- **`warmup_server`**: Preloads models and LanceDB into VRAM/RAM to eliminate first-search latency.
- **`daemon_health`**: Returns status, hardware acceleration (CUDA/MPS/CPU), and index availability.
- **`list_model_profiles`**: Lists `local`, `pro`, `sandbox` and indicates the active profile.

---

## Prompts

Instruction templates for common Plesk development workflows.

| Prompt | Arguments | Description |
|--------|-----------|-------------|
| `plesk-extension-dev` | `name`, `lang` | Roadmap for new extensions via SDK/architectural patterns. |
| `plesk-api-integration`| `operation` | Exact specs and examples for REST API calls (e.g., `domain.get`). |
| `plesk-cli-reference` | `command` | Summary, options, and practical examples for CLI tools. |

---

## Resources

Structured data access via URI.

- **`plesk://toc/{category}`**: Markdown Table of Contents for a specific category.
  - *HTML sources*: Includes deep links to official online docs.
  - *Code sources*: Hierarchical view of classes and modules.

---

## Environment Configuration

| Variable | Default | Impact |
|----------|---------|--------|
| `PLESK_ENABLE_SAMPLING` | `false` | Enable/disable AI-synthesized answers in search. |
| `PLESK_MIN_RELEVANCE_THRESHOLD` | `0.55` | Minimum score required to return a result. |
| `PLESK_RERANK_CANDIDATES` | `50` | Pool size for cross-encoder reranking. |
| `PLESK_INDEX_SUMMARIES` | `false` | Enable LLM-generated file summaries during indexing. |
