#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP=experiments_src/exp_001_d
N=10
HEURISTIC=BASIC
CR_SCENARIO=cr_scenarios/threelanes.xml
RULE_INJECTION="$EXP/in/rule_injection.lp"   # or leave empty to disable

run_heuristic_experiment "$EXP" "$N" "$HEURISTIC" "$CR_SCENARIO" "$RULE_INJECTION"