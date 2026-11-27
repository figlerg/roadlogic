#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP=experiments_src/exp_001
N=1
STEP_LENGTH=60

# Apparently this one prevents to break the definition of PYTHONPATH?
set +x
run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH"
