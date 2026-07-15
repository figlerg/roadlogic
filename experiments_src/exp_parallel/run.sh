#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP=experiments_src/exp_parallel
N=2
STEP_LENGTH=1

run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH"