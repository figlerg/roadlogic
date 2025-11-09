#!/usr/bin/env bash
# Common helper: logs timing info as JSON in $EXP/out/times.jsonl

time_step() {
  local label="$1"; shift
  local start end dur start_iso end_iso status rc log_json
  log_json="$EXP/out/times.jsonl"
  mkdir -p "$(dirname "$log_json")"

  start=$(date +%s); start_iso=$(date -Iseconds)
  echo "[START] $label"
  "$@"; rc=$?
  end=$(date +%s); end_iso=$(date -Iseconds)
  dur=$((end - start))
  if (( rc == 0 )); then status="ok"; else status="error"; fi

  printf '[DONE ] %-35s %3dm%02ds (%s)\n' "$label" $((dur/60)) $((dur%60)) "$status"
  printf '{"step":"%s","seconds":%d,"status":"%s","started_at":"%s","finished_at":"%s"}\n' \
         "$label" "$dur" "$status" "$start_iso" "$end_iso" >> "$log_json"

  return "$rc"  # <-- propagate success/failure to caller
}


# --- Utility: reset an experiment's out folder ---
exp_reset_out() {
local dir="$1/out"
if command -v gio >/dev/null 2>&1; then
gio trash "$dir" 2>/dev/null || true
else
rm -rf "$dir" 2>/dev/null || true
fi
mkdir -p "$dir"
}


# --- VANILLA PIPELINE -------------------------------------------------------
run_vanilla_experiment() {
  EXP="$1"; N="$2"; STEP_LENGTH="$3"
  exp_reset_out "$EXP"

  time_step "generate-osc-scenarios" \
  make generate-osc-scenarios \
    OSC_N="$N" \
    OSC_FILE="$EXP/in/spec.osc" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations" \
    SCENARIOS_FOLDER="$EXP/out" \
    STEP_LENGTH="$STEP_LENGTH" \
    RULE_INJECTION="$EXP/in/rule_injection.lp"

  time_step "execute-all-scenarios" \
  make execute-all-scenarios \
    SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations"

  time_step "compute-metrics" \
  make -j 8 \
    SCENARIOS_FOLDER=$EXP/out/cr_scenarios \
    OUTPUT_FOLDER=$EXP/out/cr_simulations \
    compute-selected-metrics-for-all-scenarios

  time_step "generate-summary" \
  make generate-summary \
    SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations" \
    OSC_FILE="$EXP/in/spec.osc"
}

# --- PARTITIONING PIPELINE --------------------------------------------------
run_variability_experiment() {
  EXP="$1"
  N="$2"

  # Optional 3rd positional: CR_SCENARIO
  if [[ $# -ge 3 && "$3" != --* ]]; then
    CR_SCENARIO="$3"
    shift 3
  else
    CR_SCENARIO="cr_scenarios/threelanes.xml"
    shift 2
  fi

  EXTRA_ARGS=("$@")   # e.g. --init-interval 10 20

  exp_reset_out "$EXP"

  time_step "create_variability_instances" \
  python create_scenarios/create_variability_instances.py \
    --output-folder "$EXP/out/partitions/" \
    --n "$N" \
    "${EXTRA_ARGS[@]}"

  time_step "variability_experiments" \
  python create_scenarios/variability_experiments.py \
    --output-folder "$EXP/out" \
    --input-folder "$EXP/out/partitions/" \
    --osc-file "$EXP/in/spec.osc" \
    --cr-scenario "$CR_SCENARIO" \
    --rule-injection "$EXP/in/rule_injection.lp" \
    --time-limit 150

  time_step "execute-all-scenarios" \
  make execute-all-scenarios \
    SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations"

  time_step "compute-metrics" \
  make -j 8 \
    SCENARIOS_FOLDER=$EXP/out/cr_scenarios \
    OUTPUT_FOLDER=$EXP/out/cr_simulations \
    compute-selected-metrics-for-all-scenarios

  time_step "generate-summary" \
  make generate-summary \
    SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations" \
    OSC_FILE="$EXP/in/spec.osc"
}

# --- HEURISTIC PIPELINE -----------------------------------------------------
# Uses dynamic_feedback to synthesize/expand scenarios via a chosen heuristic,
# then executes and summarizes.
# Usage: run_heuristic_experiment <EXP_DIR> <N> [HEURISTIC] [CR_SCENARIO] [RULE_INJECTION]
# HEURISTIC default: BASIC
# CR_SCENARIO default: cr_scenarios/threelanes.xml
# RULE_INJECTION optional: path to rule_injection.lp (omit to disable)
run_heuristic_experiment() {
EXP="$1"; N="$2"; HEURISTIC="${3:-BASIC}"; CR_SCENARIO="${4:-cr_scenarios/threelanes.xml}"; RULE_INJECTION="${5:-}"
exp_reset_out "$EXP"


# Build the dynamic_feedback command with optional rule injection
cmd=(python create_scenarios/dynamic_feedback.py
--output-folder "$EXP/out"
--heuristic "$HEURISTIC"
--osc-file "$EXP/in/spec.osc"
--n "$N"
--cr-scenario "$CR_SCENARIO")
if [[ -n "$RULE_INJECTION" ]]; then
cmd+=(--rule-injection "$RULE_INJECTION")
fi


time_step "dynamic_feedback" "${cmd[@]}"

time_step "execute-all-scenarios" \
make execute-all-scenarios \
SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
OUTPUT_FOLDER="$EXP/out/cr_simulations"

time_step "compute-metrics" \
  make -j 8 \
    SCENARIOS_FOLDER=$EXP/out/cr_scenarios \
    OUTPUT_FOLDER=$EXP/out/cr_simulations \
    compute-selected-metrics-for-all-scenarios

time_step "generate-summary" \
make generate-summary \
  SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
  OUTPUT_FOLDER="$EXP/out/cr_simulations" \
  OSC_FILE="$EXP/in/spec.osc"
}
