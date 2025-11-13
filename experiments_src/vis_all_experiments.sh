# vanilla pics
python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_00[0-9].json" \
  --out "experiments_src/vis/vis_vanilla_combined.pdf"

python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_00[0-9].json" \
  --out "experiments_src/vis/vis_vanilla_timing.pdf" \
  --mode timing \

python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_00[0-9].json" \
  --out "experiments_src/vis/vis_vanilla_success.pdf" \
  --mode success \


# parameter variation pics
python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_*_b.json" \
  --mode timing \
  --out experiments_src/vis/vis_partitioning_timing.pdf

python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_*_b.json" \
  --mode success \
  --out experiments_src/vis/vis_partitioning_success.pdf

python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_*_b.json" \
  --out "experiments_src/vis/vis_partitioning_combined.pdf"


# parameter variation plus fixed car1
python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_*_c.json" \
  --out "experiments_src/vis/vis_partitioning_fixedcar1_combined.pdf"

python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_*_c.json" \
  --mode success \
  --out experiments_src/vis/vis_partitioning_fixedcar1_success.pdf

python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_*_c.json" \
  --mode timing \
  --out experiments_src/vis/vis_partitioning_fixedcar1_timing.pdf