# MCP Components Reference

This document provides a detailed reference for all Model Context Protocol (MCP) components exposed by the `mcp-plesk-dev-docs` server.

---

## Tools

Tools allow the AI client (e.g., Claude) to perform actions or retrieve data from the Plesk knowledge base.

### `search_plesk_unified`
**Description:** The primary tool for semantic search across all five Plesk documentation sources.
**Arguments:**
- `query` (string, required): The search query in plain English.
- `category` (string, optional): Filter results by category (`guide`, `api`, `cli`, `php-stubs`, `js-sdk`).
**Behavior:**
1. Performs Hybrid Search (Vector + FTS).
2. Reranks top 50 candidates using a cross-encoder.
3. Automatically expands context for the top 5 results by fetching adjacent chunks (neighbor retrieval).
4. If `PLESK_ENABLE_SAMPLING` is enabled, it synthesizes a concise answer before returning result cards.

### `refresh_knowledge`
**Description:** Synchronizes the local vector index with the documentation sources.
**Arguments:**
- `target_category` (string, default: `"all"`): Specific category to index.
- `reset_db` (boolean, default: `false`): If true, wipes the database before starting.
**Behavior:** Uses chunk-level fingerprinting to skip unchanged files. Rebuilds FTS and TurboQuant indices upon completion.

### `trigger_index_sync`
**Description:** Triggers an asynchronous indexing job.
**Arguments:** Same as `refresh_knowledge`.
**Returns:** A `job_id` that can be used to track progress. Useful for long-running indexing tasks without blocking the server.

### `check_sync_status`
**Description:** Checks the status of a background indexing job.
**Arguments:**
- `job_id` (string, required): The ID returned by `trigger_index_sync`.

### `warmup_server`
**Description:** Preloads models and the database table into memory.
**Use Case:** Use this if the server was started without auto-warmup to avoid latency on the first search.

### `daemon_health`
**Description:** Returns readiness status, hardware acceleration details (CUDA/MPS/CPU), and index availability.

### `list_model_profiles`
**Description:** Lists available profiles (`light`, `medium`, `full`, `full-tq`) and indicates which one is currently active.

---

## Prompts

Prompts provide pre-configured instructions and search strategies for common Plesk development tasks.

### `plesk-extension-dev-guide`
**Arguments:**
- `extension_name` (string): Name of the new extension.
- `target_language` (string): Language (`php` or `javascript`).
**Description:** Guides the AI to search for architectural patterns and SDK hooks to provide a complete roadmap for a new extension.

### `plesk-api-integration`
**Arguments:**
- `api_operation` (string): The name of the API call (e.g., `domain.get`).
**Description:** Instructs the AI to find exact API specifications and provide request/response examples.

### `plesk-cli-reference`
**Arguments:**
- `command_name` (string): The Plesk CLI command (e.g., `plesk bin domain`).
**Description:** Helps the user get a comprehensive summary, options, and practical examples for any CLI command.

---

## Resources

Resources provide direct access to structured data, such as Tables of Contents.

### `plesk://toc/{category}`
**Available categories:** `api`, `cli`, `guide`, `php-stubs`, `js-sdk`.
**Description:** Returns a Markdown-formatted Table of Contents for the specified category.
**Behavior:**
- For HTML sources (`api`, `cli`, `guide`), it includes direct links to the official online documentation.
- For code sources (`php-stubs`, `js-sdk`), it provides a hierarchical view of the available classes and modules.

---

## Environment Configuration

Key environment variables that affect MCP behavior:

- `PLESK_ENABLE_SAMPLING`: Enable/disable AI-synthesized answers in `search_plesk_unified`.
- `PLESK_MIN_RELEVANCE_THRESHOLD`: Minimum relevance score (0-1) required for a result to be returned.
- `PLESK_RERANK_CANDIDATES`: Number of candidates passed from vector search to the reranker (default: 50).
- `PLESK_INDEX_SUMMARIES`: Enable LLM-generated file summaries during indexing.
