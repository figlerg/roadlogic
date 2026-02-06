# Reproducibility Evaluation: Declarative Scenario-based Testing with RoadLogic (ICCPS26)

# Running the artifact


## Quickstart
This is the **bare minimum** fastest way to rerun the experiments. For an in-depth installation guide, see the README file.

### Prerequisites
- Docker

### Reproducing the figures
To reproduce the figures in the paper, just use the Dockerfile. The experiments run for about 10h in total on my Dell Latitude with a 12th Gen Intel(R) Core(TM) i7-1265U. Your mileage may vary (and the computation time with it).

- Inside this folder, run
````docker build -t roadlogic-artifact .````

- Run the container. 
````docker run --rm -it --name roadlogic-artifact roadlogic-artifact````
**Be careful:** remove ``--rm`` if you want the container to persist after usage.

- Run the script to reproduce the Figures from the paper
````bash paper/reproduce_experiments.sh````

- This part takes about 10h.
- Find the results under ````paper/figures```` **inside the container**.
- After completion, copy the generated figures to the host system at ``<PATH>`` with: ````docker cp roadlogic-artifact:/artifact/paper/figures <PATH> ````


## Expected Reproducibility Outcomes
This artifact includes the source code for our tool RoadLogic that comes with the paper "Declarative Scenario-based Testing with RoadLogic" (ICCPS26).

It features the complete tool with an easy-to-use entry-point to reproduce our experiments in the paper in a [runnable bash script](paper/reproduce_experiments.sh). Figures 1, 4, 5, 7, 8 and 9 are reproduced in this script. It generates the corresponding pdf/png files in the folder ````paper/figures```` inside the container. Most plots are identical to the original figures, or similar when some minor stochasticity makes the experiments not perfectly reproducible. The details are below.

## Experiment Structure
Typically our experiment folder have this structure:
````text
EXP_FOLDER/
├─ in/
│  ├─ spec.osc
│  └─ rule_injection.lp
├─ out/
│  ├─ animations/
│  ├─ asp/
│  └─ …
├─ run.sh
└─ animate.sh
````

In run.sh, one of two experiment modes are used: the vanilla (called base in the paper) variant and the partitioning (called refined in the paper) variant. This is the  common code that is used across experiments (without the time keeping code, to reduce complexity in this document). 

````bash
run_vanilla_experiment() {
  EXP="$1"; N="$2"

  exp_reset_out "$EXP"

  make generate-osc-scenarios \
    OSC_N="$N" \
    OSC_FILE="$EXP/in/spec.osc" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations" \
    SCENARIOS_FOLDER="$EXP/out" \
    RULE_INJECTION="$EXP/in/rule_injection.lp"

  make execute-all-scenarios \
    SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations"

  make -j 8 \
    SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations" \
    compute-selected-metrics-for-all-scenarios

  make generate-summary \
    SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations" \
    OSC_FILE="$EXP/in/spec.osc"

  python commonroad_extensions/simulation_analysis/similarity.py \
    --plans-folder "$EXP/out/serialized_models" \
    --output-folder "$EXP/out/similarity"
}
````

````bash
run_variability_experiment() {
  EXP="$1"; N="$2"

  exp_reset_out "$EXP"

  python create_scenarios/create_variability_instances.py \
    --output-folder "$EXP/out/partitions" \
    --n "$N"

  python create_scenarios/variability_experiments.py \
    --output-folder "$EXP/out" \
    --input-folder "$EXP/out/partitions" \
    --osc-file "$EXP/in/spec.osc" \
    --cr-scenario "cr_scenarios/threelanes.xml" \
    --rule-injection "$EXP/in/rule_injection.lp"

  make execute-all-scenarios \
    SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations"

  make -j 8 \
    SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations" \
    compute-selected-metrics-for-all-scenarios

  make generate-summary \
    SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations" \
    OSC_FILE="$EXP/in/spec.osc" \
    BLUEPRINT_FOLDER="$EXP/out/aux_asp"

  python commonroad_extensions/simulation_analysis/similarity.py \
    --plans-folder "$EXP/out/serialized_models" \
    --output-folder "$EXP/out/similarity"
}

````

## Example Usage
For example, running the experiment 2 of our benchmark in the refined mode is as simple as running 
````bash experiments_src/exp_002_b/run.sh````
It will
- vary parameters of the ASP automatically
- run the ASP planner, generating asp instance files, plans, plan animations, etc. in ````experiments_src/exp_002_b/out````
- simulate in commonroad using Frenetix, generating simulation traces in ``experiments_src/exp_002/out/cr_simulations``
- optionally we can call ``bash experiments_src/exp_002/animate.sh`` to create gif animations like ``experiments_src/exp_002/out/cr_simulations/scenario_0001/simulation_00001/simlation.gif``

## Experiment Suite

The artifact contains the following experiment folders:

**Benchmark experiments (Figures 5,6,8)**
- `experiments_src/exp_00X` for X = 1..7 (base mode)
- `experiments_src/exp_00X_b` for X = 1..7 (refined mode)

**Visualization experiments (Figures 1,4,7,9)**
- `paper/01_model_vis/overtake`
- `paper/02_trajectory_vis/01_overtake`
- `paper/02_trajectory_vis/02_fake_overtake`
- `paper/02_trajectory_vis/03_similarity`

## Paper Outcomes vs. Artifact Outputs
The following list assumes that the quickstart instructions have completed (i.e., the script
`paper/reproduce_experiments.sh` has finished).

All generated figures are written to `paper/figures` **inside the Docker container**.
To access them from the host system, either:

- copy them out using `docker cp`, or
- attach to the container and browse the filesystem.

**Tip:** Attaching the Docker container with VS Code makes viewing the output much easier.




- [F1] Figure 1 in the paper can be recreated with 
  ````bash
  bash paper/02_trajectory_vis/01_overtake/run.sh
  
  ````
  Find it under paper/figures/Fig_1_alt.pdf. **Note:** In the paper the plan depicted is slightly different. The ASP solving engine Clingo is sensitive to minor changes in the encoding. The order of plans it returns can change if the input varies. A bug fix changed this ASP input and we get this minor stochasticity. In the camera ready version this Figure wil be updated to be completely reproducible. 
- [F2] 


**Note:** The script ``paper/reproduce_experiments.sh`` does all of the above.