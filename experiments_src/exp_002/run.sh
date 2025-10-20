EXP=experiments_src/exp_002

gio trash $EXP/out/; # reset things
mkdir $EXP/out/

N=30
STEP_LENGTH=20

make generate-osc-scenarios \
    OSC_N=$N \
	OSC_FILE=$EXP/in/spec.osc \
	OUTPUT_FOLDER=$EXP/out/cr_simulations \
	SCENARIOS_FOLDER=$EXP/out \
	STEP_LENGTH=$STEP_LENGTH \
    RULE_INJECTION=$EXP/in/rule_injection.lp


make execute-all-scenarios \
	SCENARIOS_FOLDER=$EXP/out/osc2/cr_scenarios \
	OUTPUT_FOLDER=$EXP/out/osc2/cr_simulations


make generate-summary \
	SCENARIOS_FOLDER=$EXP/out/osc2/cr_scenarios \
	OUTPUT_FOLDER=$EXP/out/osc2/cr_simulations
