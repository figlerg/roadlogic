#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP=experiments_src/exp_006_c
N=100

run_variability_experiment "$EXP" "$N"