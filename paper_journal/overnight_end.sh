#!/bin/bash
# Overnight 2026-11-19: cars keep driving until the simulation ends (ROADLOGIC_FINAL_SLACK=end).
#   1. exp_001 and its spec fixes, 10 scenarios each (about 30 minutes)
#   2. the full benchmark under the new default (about 4 to 5 hours). The previous run's output is
#      kept in paper_journal/benchmark/out_2026-11-18 for comparison.
#   3. results.md and the paper figures from the new output
# Run from the repository root:  nohup bash paper_journal/overnight_end.sh > overnight.log 2>&1 &
cd "$(dirname "$0")/.." || exit 1
source venv/bin/activate || exit 1
DAY=$(date +%F)
B=paper_journal/benchmark
[ -d $B/out ] && [ ! -d $B/out_2026-11-18 ] && mv $B/out $B/out_2026-11-18

echo "$(date +%T) exp_001 variants"
python $B/exp001_variants.py $B/exp001_variants_$DAY.jsonl

echo "$(date +%T) benchmark"
python $B/run_benchmark.py --workers 3 --sim-jobs 3
python $B/report.py > /dev/null 2>&1  # writes results.md
python paper_journal/plots/compare_paper_figures.py
echo "$(date +%T) all done"
