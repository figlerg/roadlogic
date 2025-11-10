#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP=experiments_src/exp_005_b
N=3

run_variability_experiment "$EXP" "$N" "--random-seed" "2"