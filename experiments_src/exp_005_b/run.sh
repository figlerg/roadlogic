#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP=experiments_src/exp_005_b
N=20

run_variability_experiment "$EXP" "$N"