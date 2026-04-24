#!/bin/bash
export BEADS_SKIP_IDENTITY_CHECK=1

M1_IDS=("mcp-plesk-unified-0tf" "mcp-plesk-unified-ffz" "mcp-plesk-unified-931" "mcp-plesk-unified-j8y")
M2_IDS=("mcp-plesk-unified-6rw" "mcp-plesk-unified-3pe")
M3_IDS=("mcp-plesk-unified-lby" "mcp-plesk-unified-ajj" "mcp-plesk-unified-beh" "mcp-plesk-unified-y6q")

for m1 in "${M1_IDS[@]}"; do
  for m2 in "${M2_IDS[@]}"; do
    bd dep $m1 --blocks $m2 --json > /dev/null
  done
done

for m2 in "${M2_IDS[@]}"; do
  for m3 in "${M3_IDS[@]}"; do
    bd dep $m2 --blocks $m3 --json > /dev/null
  done
done

echo "Dependencies set."

# Get the unblocked ready queue
bd ready --json
