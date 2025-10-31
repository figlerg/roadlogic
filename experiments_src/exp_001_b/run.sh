#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP=experiments_src/exp_001_b
N=2

run_variability_experiment "$EXP" "$N"