#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"   # import shared helpers

EXP=experiments_src/exp_008
LOG="$EXP/out/times.log"

gio trash "$EXP/out/" || true
mkdir -p "$EXP/out/"

N=3
STEP_LENGTH=200


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
make -n generate-summary \
  SCENARIOS_FOLDER=$EXP/out/cr_scenarios \
  OUTPUT_FOLDER=$EXP/out/cr_simulations \
  OSC_FILE=$EXP/in/spec.osc

