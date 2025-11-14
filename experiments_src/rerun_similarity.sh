#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

echo "=== Recomputing similarity_matrix for all experiments ==="

# list of names to skip exactly
SKIP_LIST=("exp_002_c" "exp_002_e" "exp_003_c" "exp_005_c" "exp_006_c" "exp_007_c")

for dir in experiments_src/exp_*/; do
    exp_name=$(basename "$dir")

    # skip exact matches
    if [[ " ${SKIP_LIST[*]} " == *" $exp_name "* ]]; then
        echo "Skipping $exp_name (explicit skip)"
        continue
    fi

    EXP="${dir%/}"
    exp_name=$(basename "$EXP")

    echo ">>> Processing $exp_name"


    python commonroad_extensions/simulation_analysis/similarity.py \
        --plans-folder $EXP/out/serialized_models \
        --output-folder $EXP/out/similarity

    echo

    cp $EXP/out/similarity/similarity_matrix.png experiments_src/vis/similarities/$(basename "$dir").png





done

echo "=== Done recomputing all summaries ==="
