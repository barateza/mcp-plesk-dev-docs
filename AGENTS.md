# Agent Instructions

Workflow mandates for AI agents. Uses **bd** (beads) for issue tracking.

## 1. Session Start (Dual-Sync Rule)
MUST run on session initialization to prevent split-brain:
`git pull --rebase && bd dolt pull && bd prime`

## 2. Long-Running Tasks (Heartbeat Rule)
NO silent sleeps. Polling background tasks (indexing, benchmarks) MUST:
1. Poll status: `while kill -0 $PID 2>/dev/null; do ... done`
2. Print heartbeat + timestamp every 60s.
3. `tail -n 5` relevant logs in each loop for verifiable progress.

## 3. Quality & Benchmarking (Hard Restriction)
- **No Speculative Pushing**: Execution of `git push` or `bd close` is FORBIDDEN until `python scripts/benchmark_profiles.py --fail-on-gate` passes.
- **Evidence-Based**: Include `MRR@5` and `Hit Rate` in final session summary.
- **Retrieval Integrity**: Verify FTS keyword-exact results after any indexing.

## 4. Session Completion
Work is NOT complete until pushed. Steps:
1. **File Issues**: `bd` for remaining/follow-up work.
2. **Quality Check**: Verify `context_recall` and `faithfulness` meet minimums.
3. **Update beads**: Close finished, update in-progress.
4. **Push All**: `git pull --rebase && bd dolt push && git push`

## 5. Environment
- **Non-Interactive**: ALWAYS use non-interactive flags (e.g., `cp -f`, `rm -rf`, `ssh -o BatchMode=yes`).

## Quick Reference
- `bd ready`: Find work
- `bd show <id>`: Details
- `bd update <id> --claim`: Start work
- `bd close <id>`: Finish work
- `bd remember`: Store persistent discovery
