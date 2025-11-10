#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP=experiments_src/exp_006_b
N=20

run_variability_experiment "$EXP" "$N"