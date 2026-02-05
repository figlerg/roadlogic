# Reproducibility Evaluation: Declarative Scenario-based Testing with RoadLogic (ICCPS26)

## Prerequisites
- Docker

## Quickstart
To reproduce the figures in the paper, just use the Dockerfile. The experiments run for about 10h in total on my Dell Latitude with a 12th Gen Intel(R) Core(TM) i7-1265U. Your mileage may vary (and the computation time with it).

- Inside this folder, run
````docker build -t roadlogic-artifact .````

- Run the container:
````docker run --rm -it --name roadlogic-artifact roadlogic-artifact````

- Run the script to reproduce the Figures from the paper
````bash paper/reproduce_experiments.sh````

- This part takes about 10h.
- Find the results under ````paper/figures````

