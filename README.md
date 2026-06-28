# RoadLogic

**RoadLogic** is a logic-based planning and simulation framework for road and traffic scenarios.
It synthesizes high-level driving plans using **Answer Set Programming (ASP)** and supports scenario specifications in **OpenSCENARIO 2.1 DSL**.
The generated plans can be executed and evaluated through **CommonRoad** and the **Frenetix Motion Planner**.

---

## Reproducibility Evaluation
See [REPRODUCIBILITY.md](REPRODUCIBILITY.md) and the PDF version [REPRODUCIBILITY.pdf](REPRODUCIBILITY.pdf).

## Overview

RoadLogic provides:

* Declarative reasoning for scenario-based planning
* Automatic plan synthesis from OpenSCENARIO 2.1 descriptions
* Execution interface for CommonRoad simulations
* Integration with the Frenetix motion-planning library

> **Status:** This branch is frozen for reproducibility. Active development continues on the [main branch](https://github.com/figlerg/roadlogic).

---

## Installation
### Docker
To reproduce the figures in the paper, just use the Dockerfile. The experiments run for about 10h in total on my Dell Latitude with a 12th Gen Intel(R) Core(TM) i7-1265U. Your mileage may vary (and the computation time with it).

- Inside this folder, run
````docker build -t roadlogic-artifact .````

- Run the container. 
````docker run --rm -it --name roadlogic-artifact roadlogic-artifact````
**Be careful:** remove ``--rm`` if you want the container to persist after usage.

- Run the script to reproduce the Figures from the paper
````bash paper/reproduce_experiments.sh````

- This part takes about 10h.
- Find the results under ````paper/figures````


### Set up locally


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

### Test

```bash
python -m planning.Planner plans --osc2_file tests/overtake.osc -n 3 -a # run planning engine standalone
bash experiments_src/exp_001/run.sh # run the experiments with their shell script. see shell script for some make examples
```

---

## Authors & Acknowledgments

- Ezio Bartocci
- Alessio Gambi
- Felix Gigler
- Cristinel Mateis
- Dejan Nickovic

This repository is maintained by Felix Gigler and Alessio Gambi.

---

## Citation

If you use RoadLogic in academic work, please cite our forthcoming paper:

````bibtex
@inproceedings{bartocci2026roadlogic,
  title     = {Declarative Scenario-based Testing with RoadLogic},
  author    = {Bartocci, Ezio and Gambi, Alessio and Gigler, Felix and Mateis, Cristinel and Ni\v{c}kovi\'{c}, Dejan},
  booktitle = {Proceedings of the 29th ACM International Conference on Hybrid Systems: Computation and Control (HSCC)},
  year      = {2026},
  note      = {To appear}
}
````
Read the preprint [here](https://arxiv.org/pdf/2603.09455). Will be updated once the HSCC proceedings are available. 

---

## License

* **RoadLogic core:** BSD 3-Clause License
* **OpenSCENARIO 2 grammar and generated parser:** MPL-2.0
* **Frenetix integration:** uses components under LGPL-3.0
* See `THIRD_PARTY_NOTICES.md` for detailed attributions.

---

*© 2025 The RoadLogic Developers. Under construction.*
