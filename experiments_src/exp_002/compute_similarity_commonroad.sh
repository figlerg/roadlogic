##################################################################################
#
# TODO: This does not work because it invokes the wrong python! Use Make instead!
#
##################################################################################

#!/usr/bin/env bash
set -euo pipefail

THIS_FOLDER_NAME=$(basename "$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )")
THIS_FOLDER_PARENT_NAME=$(basename $(dirname "$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"))

EXP="$THIS_FOLDER_PARENT_NAME/$THIS_FOLDER_NAME"
SIMULATOR="commonroad"

python commonroad_extensions/simulation_analysis/similarity.py \
    --plans-folder $EXP/out/$SIMULATOR/serialized_models \
    --output-folder $EXP/out/$SIMULATOR/similarity