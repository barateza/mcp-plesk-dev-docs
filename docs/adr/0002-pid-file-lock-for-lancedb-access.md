# 2. A PID-file lock guards concurrent LanceDB access

- **Status:** Accepted

## Context

LanceDB does not tolerate concurrent writers. This project writes from two
directions: indexing (which appends in parallel via `ThreadPoolExecutor`) and the
running server (which answers search requests). Two processes opening the same
database concurrently can corrupt state or fail unpredictably.

## Decision

A **PID-file lock** (`server/lock.py`) is acquired before touching LanceDB.

## Consequences

- Only one process may hold the database at a time; others fail fast instead of
  corrupting state.
- A stale lock file left behind by a crashed process prevents the server from
  starting. When the server won't start, check `storage/` for a stale lock first.
- Parallel indexing inside the holding process is still permitted — LanceDB handles
  concurrent appends safely; the lock is across processes, not within one.

_Provenance: migrated from the repo's earlier `CONTEXT.md` "Key Decisions"._
