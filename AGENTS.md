# Agent Instructions

This project uses **bd** (beads) for issue tracking. Run `bd prime` for full workflow context.

## Session Initialization (Dual-Sync Rule)

**When starting a work session**, you MUST execute the following to ensure the workspace and issue tracker are perfectly synced across environments (e.g., macOS and WSL):

1. **Pull remote code**: `git pull --rebase`
2. **Pull remote issues**: `bd dolt pull`
3. **Prime environment**: `bd prime`

This ensures that changes from other machines are synchronized before you begin modifying files.

## Long-Running Tasks (Heartbeat Rule)

To prevent tool timeouts and ensure transparency, you **must not** use silent `sleep` commands or infer progress for background tasks.

When waiting for a background process (e.g., re-indexing, benchmarks):
1. Use a `while` loop to poll the process status (e.g., `kill -0 $PID`).
2. Print a "heartbeat" message with a timestamp at least every 60 seconds.
3. `tail` the relevant log file during each iteration to provide exact, verifiable progress.

## Quality & Benchmarking (Hard Restriction)

- **No Speculative Pushing:** You are strictly forbidden from executing `git push` or `bd close` until you have executed `scripts/benchmark_profiles.py` with the `--fail-on-gate` flag.
- **Evidence-Based Completion:** You must include the `MRR@5` and `Hit Rate` results in your final session summary.
- **Retrieval Integrity:** Hybrid search is a core feature. After any indexing operation, verify that the Full-Text Search (FTS) index has been rebuilt and is returning keyword-exact results.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

1. **File issues for remaining work** - Use `bd` to create follow-up issues.
2. **Run quality gates** - Verify that `context_recall` and `faithfulness` meet minimums via `python scripts/benchmark_profiles.py --fail-on-gate`.
3. **Update issue status** - Close finished work, update in-progress items.
4. **PUSH TO REMOTE**:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   ```

## Non-Interactive Shell Commands

**ALWAYS use non-interactive flags** (`cp -f`, `rm -rf`, `ssh -o BatchMode=yes`, etc.) to avoid hanging on confirmation prompts.

## Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
bd remember           # Store persistent knowledge
```
