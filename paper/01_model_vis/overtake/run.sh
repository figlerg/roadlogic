#!/usr/bin/env bash
set -euo pipefail
source "experiments_src/common.sh"

EXP=paper/01_model_vis/overtake
N=3
STEP_LENGTH=20

run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH"

bash $EXP/animate.sh

cp paper/02_trajectory_vis/01_overtake/out/serialized_models/0001.pkl paper/01_model_vis/predicates.pkl