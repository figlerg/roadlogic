make generate-osc-scenarios OSC_FILE=./experiments_src/exp_001/in/spec.osc OUTPUT_FOLDER=./experiments_src/exp_001/out/cr_simulations SCENARIOS_FOLDER=./experiments_src/exp_001/out


SCENARIOS_FOLDER=experiments_src/exp_001/out/osc2/cr_scenarios
OUTPUT_FOLDER=experiments_src/exp_001/out/osc2/cr_simulations

make execute-all-scenarios SCENARIOS_FOLDER=$SCENARIOS_FOLDER OUTPUT_FOLDER=$OUTPUT_FOLDER

make generate-summary OUTPUT_FOLDER=$OUTPUT_FOLDER SCENARIOS_FOLDER=$SCENARIOS_FOLDER