bash experiments_src/exp_001_c/run.sh 
bash experiments_src/exp_002_c/run.sh 
bash experiments_src/exp_003_c/run.sh 
bash experiments_src/exp_004_c/run.sh 
bash experiments_src/exp_005_c/run.sh 
bash experiments_src/exp_006_c/run.sh 

bash experiments_src/extract_summaries.sh # get the summaries out and gather them in the logs folder

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




