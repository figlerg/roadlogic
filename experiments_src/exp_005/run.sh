#!/usr/bin/env bash
set -euo pipefail

EXP=experiments_src/exp_005
LOG="$EXP/out/times.log"

gio trash "$EXP/out/" || true
mkdir -p "$EXP/out/"
: > "$LOG"

N=3
STEP_LENGTH=200

time_step () {
  local label="$1"; shift
  local start end dur
  start=$(date +%s)
  echo "[START] $label" | tee -a "$LOG"
  "$@"
  end=$(date +%s)
  dur=$((end - start))
  printf "[DONE ] %-35s %3dm%02ds\n" "$label" $((dur/60)) $((dur%60)) | tee -a "$LOG"
}

time_step "generate-osc-scenarios" \
make generate-osc-scenarios \
  OSC_N=$N \
  OSC_FILE=$EXP/in/spec.osc \
  OUTPUT_FOLDER=$EXP/out/cr_simulations \
  SCENARIOS_FOLDER=$EXP/out \
  STEP_LENGTH=$STEP_LENGTH \
  RULE_INJECTION=$EXP/in/rule_injection.lp

time_step "execute-all-scenarios" \
make execute-all-scenarios \
  SCENARIOS_FOLDER=$EXP/out/cr_scenarios \
  OUTPUT_FOLDER=$EXP/out/cr_simulations

time_step "generate-summary" \
make generate-summary \
  SCENARIOS_FOLDER=$EXP/out/cr_scenarios \
  OUTPUT_FOLDER=$EXP/out/cr_simulations \
  OSC_FILE=$EXP/in/spec.osc

echo "Timing summary written to $LOG"
