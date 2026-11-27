#!/usr/bin/env bash
set -euo pipefail

THIS_FOLDER_NAME=$(basename "$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )")
THIS_FOLDER_PARENT_NAME=$(basename $(dirname "$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"))

EXP="$THIS_FOLDER_PARENT_NAME/$THIS_FOLDER_NAME"
SIMULATOR="commonroad"

make \
    SIMULATOR="$SIMULATOR" \
    SCENARIOS_FOLDER="$EXP/out/$SIMULATOR/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/$SIMULATOR/cr_simulations" \
        animate-all-scenarios 