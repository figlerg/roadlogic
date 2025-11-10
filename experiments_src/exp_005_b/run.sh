#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP=experiments_src/exp_005_b
N=20
# seed 1 also was good
# seed 42 is the default one
run_variability_experiment "$EXP" "$N" "--random-seed" "1"