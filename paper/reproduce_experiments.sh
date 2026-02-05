export PYTHONWARNINGS="ignore" # less clutter



### Figure 1, 7, 9

bash paper/02_trajectory_vis/01_overtake/run.sh # create plan for the visual aid Figure 1 
# (see notes, it looks slightly different than in the paper due to some changes to the code. the original picture is saved as Fig_1_alt.pdf , so only rerunning the 2nd half of the pipeline with the scenario file)
bash paper/02_trajectory_vis/02_fake_overtake/run.sh # create plan for Figure 9
bash paper/02_trajectory_vis/03_similarity/run.sh # create plans with varied parameters to show three qualitatively different plans in Figure 7

python paper/02_trajectory_vis/plot_working_example.py


### FIGURE 4

# create the plan
bash paper/01_model_vis/overtake/run.sh

# create model frames
python paper/01_model_vis/model_vis.py

# collect to figure folder
cp paper/01_model_vis/model_vis_plots/0004.pdf paper/figures/Fig_4a.pdf
cp paper/01_model_vis/model_vis_plots/0007.pdf paper/figures/Fig_4b.pdf
cp paper/01_model_vis/model_vis_plots/0009.pdf paper/figures/Fig_4c.pdf


### Figure 5,6,8

# run all experiments. this takes about 9h on my machine (12th Gen Intel(R) Core(TM) i7-1265U)
bash experiments_src/run_vanilla_experiments.sh
bash experiments_src/run_partitioning_experiments.sh

bash experiments_src/extract_summaries.sh # get the summaries out and gather them in the logs folder

bash experiments_src/vis_all_experiments.sh # generate the timing plots


