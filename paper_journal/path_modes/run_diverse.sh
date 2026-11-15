#!/bin/bash
# Every diversity method on the paper's vanilla specs, 50 plans each, 4 jobs at a time, every run kept.
# From the repository root, venv active: bash paper_journal/path_modes/run_diverse.sh <out.jsonl> [extras...]
OUT=${1:-paper_journal/path_modes/diverse.jsonl}
shift
EXTRAS=${@:-2 6}
: > "$OUT"
jobs=()
for exp in exp_001 exp_002 exp_003 exp_005 exp_006 exp_007; do
  for extra in $EXTRAS; do
    for m in step1 step60 basic strict iou1 iou0.9 iou0.8 rise0.5 rise0.7; do
      jobs+=("$exp $m $extra")
    done
  done
done
printf '%s\n' "${jobs[@]}" | xargs -P 4 -L 1 bash -c '
  exp=$0; m=$1; extra=$2
  line=$(DIVERSE_EXTRA=$extra timeout 1800 python -u paper_journal/path_modes/diverse.py \
    experiments_src/$exp/in/spec.osc $m 50 experiments_src/$exp/in/rule_injection.lp 2>/dev/null | grep "^{")
  [ -n "$line" ] && echo "$line" >> '"$OUT"' || echo "{\"spec\": \"$exp\", \"method\": \"$m\", \"extra\": $extra, \"failed\": \"timeout (1800 s) or error\"}" >> '"$OUT"'
'
echo DIVERSE_DONE
