#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/../common.sh"   # import shared helpers

EXP=experiments_src/exp_002_c
LOG="$EXP/out/times.log"

gio trash $EXP/out/; # reset things
mkdir $EXP/out/

N=100


time_step "create_variability_instances" \
python create_scenarios/create_variability_instances.py \
	--output-folder $EXP/out/partitions/ \
	--n $N

time_step "variability_experiments" \
python create_scenarios/variability_experiments.py \
	--output-folder $EXP/out \
	--input-folder $EXP/out/partitions/ \
	--osc-file $EXP/in/spec.osc \
	--cr-scenario cr_scenarios/threelanes.xml \
	--rule-injection $EXP/in/rule_injection.lp


time_step "execute-all-scenarios" \
make execute-all-scenarios \
	SCENARIOS_FOLDER=$EXP/out/cr_scenarios \
	OUTPUT_FOLDER=$EXP/out/cr_simulations

time_step "generate-summary" \
make generate-summary \
	SCENARIOS_FOLDER=$EXP/out/cr_scenarios \
	OUTPUT_FOLDER=$EXP/out/cr_simulations

