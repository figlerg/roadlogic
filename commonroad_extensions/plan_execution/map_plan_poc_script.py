"""
TODOs:

1) load the scenario (curved or linear)
2) load the pickled planning
3) fix a curvilinear coordinate system
4) map the planning to the coordinate system ---> do in a more structured way later
"""

from commonroad.common.file_reader import CommonRoadFileReader
import numpy as np
from create_scenarios.draw import draw

# ad 1
scenario, planning_problem_set = CommonRoadFileReader("scenarios/threelanes_curved.xml").open()

# draw(scenario,planning_problem_set)

# ad 2
from plans.load_plans import df_by_time  # I use dataframes for now


for t, frame in df_by_time.items():
    print(f"Time {t}:")
    for agent, row in frame.iterrows():
        x, y = row["lon_pos"], row["lat_pos"]
        print(f"  Agent {agent} is at position ({x}, {y})")
    print()


# ad 3: take the center lane as anchor
anchor_lane = scenario._lanelet_network.lanelets[1].center_vertices
left_lane = scenario._lanelet_network.lanelets[0].center_vertices
right_lane = scenario._lanelet_network.lanelets[2].center_vertices
anchor_point = 0.1  # the longitudinal coordinate (not 0 because the road starts there)


from cr_scenario_handler.utils.utils_coordinate_system import CoordinateSystem



# TODO do I need a config_sim?
# config_sim.visualization.ref_path_debug  # THIS IS ONLY REFERENCE

# create a dummy variable so it doesn't scream AttributeError
from types import SimpleNamespace
config_sim = SimpleNamespace(
    visualization=SimpleNamespace(ref_path_debug=False)
)

coordinate_system = CoordinateSystem(reference=anchor_lane, config_sim=config_sim)


segment = 30
lane = -1  # 1 to right

lanes = {-1:left_lane, 0:anchor_lane, 1:right_lane}

from commonroad_extensions.plan_execution.project_to_polyline import project_to_polyline


long_xy = coordinate_system.convert_to_cartesian_coords(segment,0)
xy, idx = project_to_polyline(long_xy, lanes[lane])

for pp in planning_problem_set.planning_problem_dict.values():
    goal = pp.goal.state_list[0]
    if goal.position:
        goal.position.center = xy

draw(scenario, planning_problem_set)





