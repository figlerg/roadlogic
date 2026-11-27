#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

# Why not using:
# echo "$(dirname "$0")"
EXP=experiments_src/exp_001
N=3
STEP_LENGTH=200

run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH"