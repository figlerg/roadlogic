#!/usr/bin/env bash
set -euo pipefail
source "experiments_src/common.sh"

EXP=tests/overtake
N=3
STEP_LENGTH=1

run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH"