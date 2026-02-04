#!/usr/bin/env bash
set -euo pipefail
source "experiments_src/common.sh"

EXP=paper/02_trajectory_vis/01_overtake
N=3
STEP_LENGTH=20

CONSTANTS=paper/01_model_vis/constants.lp

run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH" "CONSTANTS_OVERRIDE=$CONSTANTS"


bash $EXP/animate.sh