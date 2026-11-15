#!/bin/bash
# The IoU bound against the paper's variability runs, at the paper's plan counts.
# From the repository root, venv active: bash paper_journal/path_modes/run_iou.sh <out.jsonl>
OUT=${1:-paper_journal/path_modes/iou.jsonl}
: > "$OUT"
for case in "exp_002 50" "exp_005 36" "exp_007 39"; do set -- $case
  for theta in 1 0.9 0.8 0.7; do
    line=$(timeout 1800 python -u paper_journal/path_modes/diverse_iou.py experiments_src/$1/in/spec.osc $theta $2 experiments_src/$1/in/rule_injection.lp 2>/dev/null | grep '^{')
    [ -n "$line" ] && echo "$line" >> "$OUT" || echo "{\"spec\": \"$1\", \"theta\": $theta, \"failed\": true}" >> "$OUT"
  done
done
echo IOU_DONE
