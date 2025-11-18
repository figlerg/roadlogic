#!/usr/bin/env bash
set -euo pipefail
source "experiments_src/common.sh"

# EXP=experiments_src/exp_002
EXP=paper/02_trajectory_vis/02_fake_overtake
N=1
STEP_LENGTH=60

run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH"

bash $EXP/animate.sh