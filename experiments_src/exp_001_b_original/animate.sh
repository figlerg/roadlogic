#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"

EXP="experiments_src/exp_001_b"

make -j 8 animate-all-scenarios SCENARIOS_FOLDER="$EXP/out/cr_scenarios" OUTPUT_FOLDER="$EXP/out/cr_simulations" 