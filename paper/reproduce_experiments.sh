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



### Figure 5,6,8

# run all experiments. this takes about 9h on my machine (12th Gen Intel(R) Core(TM) i7-1265U)
bash experiments_src/run_vanilla_experiments.sh
bash experiments_src/run_partitioning_experiments.sh

bash experiments_src/extract_summaries.sh # get the summaries out and gather them in the logs folder

bash experiments_src/vis_all_experiments.sh # generate the timing plots


### Copying the rest of the newly figures to the output folder

# Figure 4
cp paper/01_model_vis/model_vis_plots/0004.pdf paper/figures/Fig_4a.pdf
cp paper/01_model_vis/model_vis_plots/0007.pdf paper/figures/Fig_4b.pdf
cp paper/01_model_vis/model_vis_plots/0009.pdf paper/figures/Fig_4c.pdf

# Figure 5
cp experiments_src/vis/vis_vanilla_timing.pdf paper/figures/Fig_5.pdf

# Figure 7
cp experiments_src/exp_001/out/similarity/similarity_matrix.png paper/figures/Fig_7_1b.png
cp experiments_src/exp_001_b/out/similarity/similarity_matrix.png paper/figures/Fig_7_1r.png
cp experiments_src/exp_002/out/similarity/similarity_matrix.png paper/figures/Fig_7_2b.png
cp experiments_src/exp_002_b/out/similarity/similarity_matrix.png paper/figures/Fig_7_2r.png
cp experiments_src/exp_003/out/similarity/similarity_matrix.png paper/figures/Fig_7_3b.png
cp experiments_src/exp_003_b/out/similarity/similarity_matrix.png paper/figures/Fig_7_3r.png
cp experiments_src/exp_004/out/similarity/similarity_matrix.png paper/figures/Fig_7_4b.png
cp experiments_src/exp_004_b/out/similarity/similarity_matrix.png paper/figures/Fig_7_4r.png
cp experiments_src/exp_005/out/similarity/similarity_matrix.png paper/figures/Fig_7_5b.png
cp experiments_src/exp_005_b/out/similarity/similarity_matrix.png paper/figures/Fig_7_5r.png
cp experiments_src/exp_006/out/similarity/similarity_matrix.png paper/figures/Fig_7_6b.png
cp experiments_src/exp_006_b/out/similarity/similarity_matrix.png paper/figures/Fig_7_6r.png
cp experiments_src/exp_007/out/similarity/similarity_matrix.png paper/figures/Fig_7_7b.png
cp experiments_src/exp_007_b/out/similarity/similarity_matrix.png paper/figures/Fig_7_7r.png

# Figure 8
cp experiments_src/vis/vis_partitioning_combined_outcome.pdf paper/figures/Fig_8.pdf

