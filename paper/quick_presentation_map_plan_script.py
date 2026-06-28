import pickle
import matplotlib.pyplot as plt
from commonroad.common.file_reader import CommonRoadFileReader
from commonroad.visualization.mp_renderer import MPRenderer
from commonroad_extensions.plan_execution.map_plan import map_plan

base = "paper/02_trajectory_vis/01_overtake/out"

scenario, _ = CommonRoadFileReader(f"{base}/cr_scenarios/scenario_0001.xml").open()

with open(f"{base}/serialized_models/0001.pkl", "rb") as f:
    plan = pickle.load(f)

# anchor lane - check your setup, usually the middle lane id
anchor_lane_idx = 2

pp_set = map_plan(scenario, plan, anchor_lane_idx)
scenario_with_goals = scenario  # use original scenario for drawing
rnd = MPRenderer()
scenario_with_goals.lanelet_network.draw(rnd)
for pp in pp_set.planning_problem_dict.values():
    pp.draw(rnd)
rnd.render()
plt.tight_layout()
plt.savefig("plan_mapping.pdf")
print("saved")