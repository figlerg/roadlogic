#!/bin/bash
# The candidate list, fixed before running, on the paper's six vanilla specs, 50 plans, every run kept.
# Each job: <spec> <method> <extra> <cap> <controller: plain|params>.
# From the repository root, venv active: bash paper_journal/path_modes/run_final.sh <out.jsonl>
OUT=${1:-paper_journal/path_modes/final.jsonl}
: > "$OUT"
for exp in exp_001 exp_002 exp_003 exp_005 exp_006 exp_007; do
  echo "$exp step60 2 1 plain"
  echo "$exp basic 2 1 plain"
  echo "$exp combo 2 1 params"
  echo "$exp iou0.9 2 1 plain"
  echo "$exp rise0.7 2 1 plain"
  echo "$exp rise0.7 6 0.9 plain"
  echo "$exp rise0.7 6 0.9 params"
done | xargs -P 4 -L 1 bash -c '
  exp=$0; m=$1; extra=$2; cap=$3; ctrl=$4
  controller=create_scenarios/controller.lp
  [ "$ctrl" = params ] && controller=paper_journal/path_modes/controller_params.lp
  line=$(DIVERSE_EXTRA=$extra DIVERSE_CAP=$cap DIVERSE_CONTROLLER=$controller timeout 2400 python -u \
    paper_journal/path_modes/diverse.py experiments_src/$exp/in/spec.osc $m 50 experiments_src/$exp/in/rule_injection.lp 2>/dev/null | grep "^{")
  [ -n "$line" ] && echo "$line" >> '"$OUT"' || echo "{\"spec\": \"$exp\", \"method\": \"$m\", \"extra\": $extra, \"cap\": $cap, \"controller\": \"$ctrl\", \"failed\": \"timeout (2400 s) or error\"}" >> '"$OUT"'
'
echo FINAL_DONE
