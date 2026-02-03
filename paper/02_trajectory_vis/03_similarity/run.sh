#!/usr/bin/env bash
set -euo pipefail
source "experiments_src/common.sh"

# EXP=experiments_src/exp_005_b
EXP=paper/02_trajectory_vis/03_similarity
N=50
# seed 1 also was good
# seed 42 is the default one
run_variability_experiment "$EXP" "$N" "--random-seed" "1"