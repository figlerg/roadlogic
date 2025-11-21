#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP=experiments_src/exp_002_c
N=50

run_variability_experiment "$EXP" "$N"