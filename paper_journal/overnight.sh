#!/bin/bash
# Overnight runs on an idle machine, one thing at a time, so the times are comparable.
#   1. planning time of the seven paper specs under clingo settings (about 2 to 3 hours)
#   2. the benchmark rerun with the current defaults (several hours)
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

python paper_journal/benchmark/run_benchmark.py --workers 3 --sim-jobs 3
echo "$(date +%T) benchmark done"
