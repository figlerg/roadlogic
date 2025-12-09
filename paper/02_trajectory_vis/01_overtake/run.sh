#!/usr/bin/env bash
set -euo pipefail
source "$experiments_src/common.sh"

EXP=paper/02_trajectory_vis/exp_002_e
N=3
STEP_LENGTH=20

run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH"

bash $EXP/animate.sh