# RoadLogic

**RoadLogic** is a logic-based planning and simulation framework for road and traffic scenarios.
It synthesizes high-level driving plans using **Answer Set Programming (ASP)** and supports scenario specifications in **OpenSCENARIO 2.1 DSL**.
The generated plans can be executed and evaluated through **CommonRoad** and the **Frenetix Motion Planner**.

---

## Overview

RoadLogic provides:

* Declarative reasoning for scenario-based planning
* Automatic plan synthesis from OpenSCENARIO 2.1 descriptions
* Execution interface for CommonRoad simulations
* Integration with the Frenetix motion-planning library

> **Status:** Active development — interfaces and APIs may change before the first stable release.

---

## Installation

### Prerequisites
- Ubuntu 22.04.5 LTS (or WSL on Windows)
- make
- git
- pyenv


### Setup
```bash
git clone https://github.com/figlerg/roadlogic.git
cd roadlogic

# using pyenv
pyenv install 3.10.16
pyenv local 3.10.16
python -m venv venv
source venv/bin/activate

# check
python --version
which python

# pip install
pip install -U pip wheel setuptools
pip install -e ./Frenetix-Motion-Planner   # local submodule
pip install -e .                           # roadlogic itself
```

---

## Quick Start


```bash
python -m planning.Planner plans --osc2_file examples/my_overtake.osc -n 3 -a # run planning engine standalone
bash experiments_src/exp_001/run.sh # run the experiments with their shell script. see shell script for some make examples
```


The experiments in the paper are carried out like this: Assume there is an experiment folder EXP with folders EXP/in and EXP/out. Assume further a specification EXP/in/spec.os2. Then you can generate plans, plots, animations, etc like this:

````bash
N="$2";                 # number of plans
STEP_LENGTH=1;          # number of discarded plans before selecting the next. has minor impact on model diversity


#  exp_reset_out "$EXP" -> reset the folder by deleting files in EXP/out/

make generate-osc-scenarios \
    OSC_N="$N" \
    OSC_FILE="$EXP/in/spec.osc" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations" \
    SCENARIOS_FOLDER="$EXP/out" \
    STEP_LENGTH="$STEP_LENGTH" \
    RULE_INJECTION="$EXP/in/rule_injection.lp"

make execute-all-scenarios \
    SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations"

make -j 8 \
    SCENARIOS_FOLDER=$EXP/out/cr_scenarios \
    OUTPUT_FOLDER=$EXP/out/cr_simulations \
    compute-selected-metrics-for-all-scenarios

make generate-summary \
    SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
    OUTPUT_FOLDER="$EXP/out/cr_simulations" \
    OSC_FILE="$EXP/in/spec.osc"

# just builds a similarity matrix for the generated plans
python commonroad_extensions/simulation_analysis/similarity.py \
    --plans-folder $EXP/out/serialized_models \
    --output-folder $EXP/out/similarity
````


---

## Authors & Acknowledgments

- Felix Gigler
- Alessio Gambi
- Dejan Nickovic
- Cristinel Mateis
- Ezio Bartocci

This repository is maintained by Felix Gigler and Alessio Gambi.

---

## Citation

If you use RoadLogic in academic work, please cite our forthcoming paper:

> *To be added after acceptance.*

---

## License

* **RoadLogic core:** BSD 3-Clause License
* **OpenSCENARIO 2 grammar and generated parser:** MPL-2.0
* **Frenetix integration:** uses components under LGPL-3.0
* See `THIRD_PARTY_NOTICES.md` for detailed attributions.

---

*© 2025 The RoadLogic Developers. Under construction.*
