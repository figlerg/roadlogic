#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP=experiments_src/exp_005
N=3
STEP_LENGTH=200

run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH"