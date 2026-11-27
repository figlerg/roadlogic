#!/usr/bin/env bash
set -euo pipefail

THIS_FOLDER_NAME=$(basename "$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )")
THIS_FOLDER_PARENT_NAME=$(basename $(dirname "$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"))

source "$(dirname "$0")/../common.sh"

# Avoid to rerun all the steps unless needed
WIPE_OUT=0
if [[ $# -gt 1 ]]; then
    echo "Wipe out results" >&2
    WIPE_OUT=1 
fi
  
EXP="$THIS_FOLDER_PARENT_NAME/$THIS_FOLDER_NAME"
N=10
STEP_LENGTH=60
SIMULATOR=beamng

run_vanilla_experiment "$EXP" "$N" "$STEP_LENGTH" "$SIMULATOR" "$WIPE_OUT"
