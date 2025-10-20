#!/usr/bin/env bash
set -euo pipefail

EXP=experiments_src/exp_004
LOG="$EXP/out/run_times.log"

# --- init
gio trash "$EXP/out/" || true
mkdir -p "$EXP/out/"
: > "$LOG"  # reset log

N=30
STEP_LENGTH=20

# simple timing helper
time_step() {
  local label="$1"; shift
  local start end dur
  start=$(date +%s)
  echo "[$(date -Iseconds)] START  $label" | tee -a "$LOG"
  "$@"
  end=$(date +%s); dur=$((end-start))
  printf "[%s] DONE   %s in %dm%02ds\n" "$(date -Iseconds)" "$label" $((dur/60)) $((dur%60)) | tee -a "$LOG"
  printf "%s\t%d\n" "$label" "$dur" >> "$LOG"
}

# --- steps
time_step "generate-osc-scenarios (dry-run)" \
make generate-osc-scenarios OSC_N="$N" OSC_FILE="$EXP/in/spec.osc" OUTPUT_FOLDER="$EXP/out/cr_simulations" SCENARIOS_FOLDER="$EXP/out" STEP_LENGTH="$STEP_LENGTH" RULE_INJECTION="$EXP/in/rule_injection.lp"

time_step "generate-osc-scenarios" \
make generate-osc-scenarios OSC_N="$N" OSC_FILE="$EXP/in/spec.osc" OUTPUT_FOLDER="$EXP/out/cr_simulations" SCENARIOS_FOLDER="$EXP/out" STEP_LENGTH="$STEP_LENGTH" RULE_INJECTION="$EXP/in/rule_injection.lp"

time_step "execute-all-scenarios" \
make execute-all-scenarios SCENARIOS_FOLDER="$EXP/out/osc2/cr_scenarios" OUTPUT_FOLDER="$EXP/out/osc2/cr_simulations"

time_step "generate-summary" \
make generate-summary SCENARIOS_FOLDER="$EXP/out/osc2/cr_scenarios" OUTPUT_FOLDER="$EXP/out/osc2/cr_simulations"

# optional: total runtime
TOTAL=$(awk '{s+=$2} END{print s+0}' "$LOG")
printf "TOTAL\t%d\n" "$TOTAL" >> "$LOG"
echo "Wrote timings to $LOG"
