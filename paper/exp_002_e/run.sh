#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../../experiments_src/common.sh"

EXP=paper/exp_002_e
N=3
STEP_LENGTH=20

run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH"

bash paper/exp_002_e/animate.sh