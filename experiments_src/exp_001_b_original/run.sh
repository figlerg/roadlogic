#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP=experiments_src/exp_001_b
N=10

# This one split the parameters in a grid and samples N of them randomly
# TODO Consider searching for the best parameters based on the monitoring values
run_variability_experiment "$EXP" "$N"