#!/bin/bash
# rise0.7 with a deterministic conflict budget on the six paper specs, 50 plans. Each job:
# <spec> <conflicts> <repetition>. Repetitions must give identical plans (only times differ).
# From the repository root, venv active: bash paper_journal/path_modes/run_conflicts.sh <out.jsonl>
OUT=${1:-paper_journal/path_modes/conflicts.jsonl}
: > "$OUT"
for exp in exp_001 exp_002 exp_003 exp_005 exp_006 exp_007; do
  echo "$exp 10000 1"; echo "$exp 10000 2"; echo "$exp 2000 1"
done | xargs -P 4 -L 1 bash -c '
  line=$(DIVERSE_CONFLICTS=$1 timeout 3600 python -u paper_journal/path_modes/diverse.py \
    experiments_src/$0/in/spec.osc rise0.7 50 experiments_src/$0/in/rule_injection.lp 2>/dev/null | grep "^{")
  [ -n "$line" ] && echo "${line%\}}, \"repetition\": $2}" >> '"$OUT"' || echo "{\"spec\": \"$0\", \"conflicts\": $1, \"repetition\": $2, \"failed\": \"timeout (3600 s) or error\"}" >> '"$OUT"'
'
echo CONFLICTS_DONE
