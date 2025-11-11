bash experiments_src/exp_001/run.sh 
bash experiments_src/exp_002/run.sh 
bash experiments_src/exp_003/run.sh 
bash experiments_src/exp_004/run.sh 
bash experiments_src/exp_005/run.sh 
bash experiments_src/exp_006/run.sh 
bash experiments_src/exp_007/run.sh 

bash experiments_src/extract_summaries.sh # get the summaries out and gather them in the logs folder


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


