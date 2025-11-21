EXP="experiments_src/exp_001_b"

python commonroad_extensions/simulation_analysis/similarity.py \
    --plans-folder $EXP/out/serialized_models \
    --output-folder $EXP/out/similarity