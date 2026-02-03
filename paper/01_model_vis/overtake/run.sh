#!/usr/bin/env bash
set -euo pipefail
source "experiments_src/common.sh"

EXP=paper/01_model_vis/overtake
N=3
STEP_LENGTH=20

CONSTANTS=paper/01_model_vis/constants.lp

run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH" "CONSTANTS_OVERRIDE=$CONSTANTS"

bash $EXP/animate.sh

cp paper/01_model_vis/overtake/out/serialized_models/0001.pkl paper/01_model_vis/predicates.pkl