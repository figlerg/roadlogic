#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"   # import shared helpers

EXP=experiments_src/exp_007
LOG="$EXP/out/times.log"

gio trash "$EXP/out/" || true
mkdir -p "$EXP/out/"

N=200

time_step () {
  local label="$1"; shift
  local start end dur
  start=$(date +%s)
  echo "[START] $label" | tee -a "$LOG"
  "$@"
  end=$(date +%s)
  dur=$((end - start))
  printf "[DONE ] %-30s %3dm%02ds\n" "$label" $((dur/60)) $((dur%60)) | tee -a "$LOG"
}

time_step "dynamic_feedback.py" \
python create_scenarios/dynamic_feedback.py \
  --output-folder "$EXP/out" \
  --heuristic BASIC \
  --osc-file "$EXP/in/spec.osc" \
  --n "$N" \
  --cr-scenario cr_scenarios/threelanes.xml \
  --rule-injection "$EXP/in/rule_injection.lp"

time_step "execute-all-scenarios" \
make execute-all-scenarios \
  SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
  OUTPUT_FOLDER="$EXP/out/cr_simulations"

time_step "generate-summary" \
make generate-summary \
  SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
  OUTPUT_FOLDER="$EXP/out/cr_simulations"

