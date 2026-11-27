EXP="experiments_src/exp_001"
SIMULATOR="commonroad"

make \
    SIMULATOR="$SIMULATOR" \
    SCENARIOS_FOLDER="$EXP/out/$SIMULATOR/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/$SIMULATOR/cr_simulations" \
        animate-all-scenarios 