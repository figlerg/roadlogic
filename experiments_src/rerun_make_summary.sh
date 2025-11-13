#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/common.sh"

echo "=== Recomputing metrics for all experiments ==="

# list of names to skip exactly
SKIP_LIST=("exp_001_copy" "exp_001_d")

for dir in experiments_src/exp_*_b/; do
    exp_name=$(basename "$dir")

    # skip exact matches
    if [[ " ${SKIP_LIST[*]} " == *" $exp_name "* ]]; then
        echo "Skipping $exp_name (explicit skip)"
        continue
    fi

    EXP="${dir%/}"
    exp_name=$(basename "$EXP")

    echo ">>> Processing $exp_name"

    summary_file="$EXP/out/cr_simulations/summary_log.json"

    # remove existing summary
    if [[ -f "$summary_file" ]]; then
        gio trash "$summary_file" 2>/dev/null || rm -f "$summary_file"
    fi



    # GPT this part for the _b and _c experiments

    # summary regeneration
    # time_step "generate-summary ($exp_name)" \ # this does weird things, but there is no reason this should change for the minor change I changed
    make generate-summary \
        SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
        OUTPUT_FOLDER="$EXP/out/cr_simulations" \
        OSC_FILE="$EXP/in/spec.osc" \
        BLUEPRINT_FOLDER="$EXP/out/aux_asp"

    echo
done

echo "=== Done recomputing all summaries ==="
