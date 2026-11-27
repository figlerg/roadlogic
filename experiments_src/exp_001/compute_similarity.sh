EXP="experiments_src/exp_001"
SIMULATOR="beamng"

python commonroad_extensions/simulation_analysis/similarity.py \
    --plans-folder $EXP/out/$SIMULATOR/serialized_models \
    --output-folder $EXP/out/$SIMULATOR/similarity