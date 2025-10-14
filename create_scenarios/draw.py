# Drawing function

import matplotlib.pyplot as plt
from commonroad.visualization.mp_renderer import MPRenderer


def draw(scenario, planning_problem_set):
    plt.figure(figsize=(25, 10))
    rnd = MPRenderer()
    rnd.clear()
    scenario.draw(rnd)
    planning_problem_set.draw(rnd)
    rnd.render(show=True)
    plt.show()