#!/usr/bin/env bash
set -euo pipefail
source "experiments_src/common.sh"

# EXP=experiments_src/exp_002
EXP=paper/02_trajectory_vis/02_fake_overtake
N=1
STEP_LENGTH=60

CONSTANTS=paper/02_trajectory_vis/02_fake_overtake/constants.lp

run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH" "CONSTANTS_OVERRIDE=$CONSTANTS"


bash $EXP/animate.sh