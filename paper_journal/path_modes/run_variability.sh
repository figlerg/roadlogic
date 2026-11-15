#!/bin/bash
# The planning part of the paper's variability experiments (experiments_src/exp_00*_b), on the current
# code, into paper_journal/path_modes/out/<exp>. Same instances (same sampling arguments and seeds),
# same 100 s limit per instance. Then the paper's similarity matrix over the plans found.
# From the repository root, venv active: bash paper_journal/path_modes/run_variability.sh exp_002_b ...
export PYTHONPATH=$PWD:$PWD/monitoring/syma-arv:$PWD/monitoring/syma
for EXP in "$@"; do
  SRC=experiments_src/$EXP
  OUT=paper_journal/path_modes/out/$EXP
  mkdir -p "$OUT"
  ARGS=$(grep -h "run_variability_experiment" $SRC/run.sh | sed 's/.*"\$N"//' | tr -d '"')
  python create_scenarios/create_variability_instances.py --output-folder "$OUT/partitions/" --n 50 $ARGS > "$OUT/instances.log" 2>&1
  start=$(date +%s)
  python create_scenarios/variability_experiments.py --output-folder "$OUT" --input-folder "$OUT/partitions/" \
    --osc-file "$SRC/in/spec.osc" --cr-scenario cr_scenarios/threelanes.xml \
    --rule-injection "$SRC/in/rule_injection.lp" --time-limit 100 > "$OUT/planning.log" 2>&1
  echo "{\"exp\": \"$EXP\", \"planning_seconds\": $(( $(date +%s) - start ))}" > "$OUT/times.json"
  python commonroad_extensions/simulation_analysis/similarity.py --plans-folder "$OUT/serialized_models" \
    --output-folder "$OUT/similarity" > "$OUT/similarity.log" 2>&1
  echo "$EXP done: $(cat $OUT/times.json), $(ls $OUT/serialized_models 2>/dev/null | wc -l) plans"
done
echo VAR_DONE
