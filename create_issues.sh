#!/bin/bash
set -e

export BEADS_SKIP_IDENTITY_CHECK=1

# M1
M1_1=$(bd create "PleskSettings pydantic-settings" -p 1 -t task --description="Replace raw os.environ.get() in server.py and model_config.py" --json | jq -r '.id')
M1_2=$(bd create "CategoryEnum strict contracts" -p 1 -t task --description="CategoryEnum on search_plesk_unified and refresh_knowledge tool parameters" --json | jq -r '.id')
M1_3=$(bd create "tool_error_boundary decorator" -p 1 -t task --description="tool_error_boundary decorator on all MCP tool functions" --json | jq -r '.id')
M1_4=$(bd create "Hardware degradation WARNING" -p 2 -t task --description="Hardware degradation WARNING log on CUDA/MPS fallback" --json | jq -r '.id')

# M2
M2_1=$(bd create "Async tool handlers (run_in_executor)" -p 2 -t task --description="All tool handlers are async def and CPU-bound ML calls wrapped in run_in_executor" --json | jq -r '.id')
M2_2=$(bd create "JobRegistry + trigger_index_sync" -p 2 -t task --description="JobRegistry + trigger_index_sync + check_sync_status tools" --json | jq -r '.id')

# M3
M3_1=$(bd create "MCP Resources (TOC endpoints)" -p 2 -t feature --description="MCP Resources: plesk://toc/{category} endpoints" --json | jq -r '.id')
M3_2=$(bd create "MCP Prompts (3 templates)" -p 2 -t feature --description="MCP Prompts: plesk-extension-dev-guide, plesk-api-integration, plesk-cli-reference" --json | jq -r '.id')
M3_3=$(bd create "Progress notifications ctx.report_progress" -p 3 -t feature --description="Progress notifications via ctx.report_progress during long operations" --json | jq -r '.id')
M3_4=$(bd create "LLM Sampling ctx.sample" -p 3 -t feature --description="LLM Sampling via ctx.sample (gated by PLESK_ENABLE_SAMPLING)" --json | jq -r '.id')

# M4
M4_1=$(bd create "Search telemetry logging" -p 3 -t chore --description="Per-query search telemetry logged to OS logger" --json | jq -r '.id')
M4_2=$(bd create "Rich markdown result cards" -p 3 -t task --description="Rich markdown result cards instead of plain text output" --json | jq -r '.id')
M4_3=$(bd create "VRAM auto-tuning" -p 3 -t task --description="VRAM auto-tuning based on available GPU memory" --json | jq -r '.id')

# M5
M5_1=$(bd create "Dockerfile" -p 2 -t chore --description="Dockerfile present at repo root" --json | jq -r '.id')
M5_2=$(bd create "docs-drift.yml CI workflow" -p 3 -t chore --description=".github/workflows/docs-drift.yml CI workflow" --json | jq -r '.id')
M5_3=$(bd create "benchmark-regression.yml CI workflow" -p 3 -t chore --description=".github/workflows/benchmark-regression.yml CI workflow" --json | jq -r '.id')

echo "M1 tasks: $M1_1 $M1_2 $M1_3 $M1_4"
echo "M2 tasks: $M2_1 $M2_2"
echo "M3 tasks: $M3_1 $M3_2 $M3_3 $M3_4"

for m1 in $M1_1 $M1_2 $M1_3 $M1_4; do
  for m2 in $M2_1 $M2_2; do
    bd deps add $m1 --blocks $m2 --json > /dev/null
  done
done

for m2 in $M2_1 $M2_2; do
  for m3 in $M3_1 $M3_2 $M3_3 $M3_4; do
    bd deps add $m2 --blocks $m3 --json > /dev/null
  done
done

echo "Done dependencies."

# Run ready to output the unblocked work queue
bd ready --json
