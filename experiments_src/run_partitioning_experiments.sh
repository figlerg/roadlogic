bash experiments_src/exp_001_b/run.sh 
bash experiments_src/exp_002_b/run.sh 
bash experiments_src/exp_003_b/run.sh 
bash experiments_src/exp_004_b/run.sh 
bash experiments_src/exp_005_b/run.sh 
bash experiments_src/exp_006_b/run.sh 
bash experiments_src/exp_007_b/run.sh 

bash experiments_src/extract_summaries.sh # get the summaries out and gather them in the logs folder

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

