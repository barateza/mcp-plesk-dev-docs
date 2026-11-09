# Agent Workflow

How a working session runs in this repo. The non-negotiable parts are duplicated in
`AGENTS.md`; this file carries the detail.

## 1. Session start (dual-sync rule)

MUST run on session initialization: `git pull --rebase`. Then use `git status` and
`gh issue list` to confirm the latest state.

## 2. Long-running tasks (heartbeat rule)

NO silent sleeps. Polling background tasks (indexing, benchmarks) MUST:

1. Poll status: `while kill -0 $PID 2>/dev/null; do ... done`
2. Print a heartbeat + timestamp every 60s.
3. `tail -n 5` the relevant log in each loop for verifiable progress.

```bash
while kill -0 $PID 2>/dev/null; do
  echo "[$(date +%T)] Still running..."
  tail -n 5 output.log
  sleep 60
done
```

## 3. Quality and benchmarking (hard restriction)

**Gate prerequisites.** The gate benchmarks a *local* index. On a fresh checkout
`knowledge_base/` and `storage/` are gitignored, so build one first (~15 min for the
full corpus on a CPU box; weights land in `.cache/hf`):

```bash
uv run python scripts/bootstrap_index.py --profile light   # prints rows=... and the indexes
```

- **No speculative pushing**: `git push` is FORBIDDEN until the gate passes:
  `uv run python scripts/benchmark_profiles.py --profile light --baseline-file benchmarks/baselines/light.json --fail-on-gate`.
  Without `--baseline-file` the script resolves `benchmarks/baselines/<suite>.json`,
  and the gate **fails** when no baseline run matches the profile/suite that ran —
  it no longer passes silently on a mismatch.
- **Latency is gated only against a baseline measured on the same machine.**
  `--capture-baseline` records a `machine` fingerprint; a baseline from another
  platform gates quality only, and the report says so under Warnings.
- **Evidence-based**: include `MRR@5` and Hit Rate in the final session summary.
- **Retrieval integrity**: verify FTS keyword-exact results after any indexing.
- **Verification over inference**: never assume a logic change improved metrics.
  Always rerun the `control` suite and inspect the database directly.
- **Regression recovery**: if a gate fails, revert the logic change or tune
  parameters until metrics match or exceed the baseline.
- **Hooks**: the `pre-commit` stage runs ruff, ruff-format, mypy, bandit and pytest;
  the `pre-push` stage runs the quality-gate benchmark. Install with
  `pre-commit install` and `pre-commit install --hook-type pre-push`.

Golden baseline (`benchmarks/baselines/control.json`, captured on Apple Silicon/MPS):

| Profile | Hit Rate | MRR | Avg latency |
|---|---|---|---|
| Light | 100% | 0.917 | ~1.007s |
| Medium | 100% | 0.95 | ~2.6s |

Latency numbers are machine-specific; quality numbers are not.

## 4. Session completion

Work is NOT complete until pushed. Steps:

1. **File issues**: create GitHub issues for remaining/follow-up work.
2. **Quality check**: verify `context_recall` and `faithfulness` meet minimums.
3. **Update issues**: close finished, update in-progress.
4. **Push all**: `git pull --rebase && git push`
5. **Verify**: `git status` MUST show "up to date with origin".
6. **Clean up**: clear stashes, prune remote branches.

**Critical rules:**

- Work is NOT complete until `git push` succeeds.
- NEVER stop before pushing — that leaves work stranded locally.
- NEVER say "ready to push when you are" — YOU must push.
- If push fails, resolve and retry until it succeeds.
