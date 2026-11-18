#!/bin/bash
# Overnight runs on an idle machine, one thing at a time, so the times are comparable.
#   1. planning time of the seven paper specs under clingo settings (about 2 to 3 hours)
#   2. rise0.7 diversity, one run at a time: the recorded times ran 2 to 4 jobs at once (about 1 hour)
#   3. exp_004 with a conflict budget per horizon, the recorded run was under load (about 15 minutes)
#   4. the benchmark: the paper's settings against the current defaults, with the new showcases (hours)
# Run from the repository root:  nohup bash paper_journal/overnight.sh > overnight.log 2>&1 &
cd "$(dirname "$0")/.." || exit 1
source venv/bin/activate || exit 1
DAY=$(date +%F)
OUT=paper_journal/profiling/time_plans_$DAY.jsonl

for args in "" "--configuration=trendy" "--configuration=handy" \
            "--parallel-mode=4,compete" "--configuration=trendy --parallel-mode=4,compete"; do
    for k in 1 2 3 4 5 6 7; do
        spec=paper_journal/benchmark/specs_paper/exp_00$k.osc
        echo "$(date +%T) $spec [$args]"
        ROADLOGIC_CLASP_ARGS="$args" timeout 3600 python paper_journal/profiling/time_plans.py "$spec" 10 2>/dev/null \
            | grep '^{' >> "$OUT" \
            || echo "{\"spec\": \"$spec\", \"clasp_args\": \"$args\", \"failed\": \"timeout or error\"}" >> "$OUT"
    done
done
echo "$(date +%T) settings done, $OUT"

DIV=paper_journal/path_modes/conflicts_idle_$DAY.jsonl
for exp in exp_001 exp_002 exp_003 exp_004 exp_005 exp_006 exp_007; do
    echo "$(date +%T) rise0.7 $exp"
    line=$(DIVERSE_CONFLICTS=10000 timeout 3600 python -u paper_journal/path_modes/diverse.py \
        experiments_src/$exp/in/spec.osc rise0.7 50 experiments_src/$exp/in/rule_injection.lp 2>/dev/null | grep '^{')
    [ -n "$line" ] && echo "$line" >> "$DIV" || echo "{\"spec\": \"$exp\", \"failed\": \"timeout or error\"}" >> "$DIV"
done

echo "$(date +%T) budget profile"
python paper_journal/profiling/profile_horizons.py experiments_src/exp_004/in/spec.osc \
    experiments_src/exp_004/in/rule_injection.lp --budget 20000 \
    > paper_journal/profiling/profile_exp_004_budget_idle_$DAY.txt 2>/dev/null

python paper_journal/benchmark/run_benchmark.py --workers 3 --sim-jobs 3
python paper_journal/benchmark/report.py > /dev/null 2>&1  # writes results.md
echo "$(date +%T) benchmark done"
