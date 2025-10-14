from commonroad.common.file_reader import CommonRoadFileReader
from commonroad.scenario.lanelet import Lanelet, LineMarking, LaneletType
from commonroad.scenario.trajectory import State
from commonroad.geometry.shape import Polygon
from commonroad.scenario.scenario import Scenario
from commonroad.common.file_writer import CommonRoadFileWriter
import numpy as np
from copy import deepcopy


from draw import draw


# Load scenario
scenario, planning_problem_set = CommonRoadFileReader("scenarios_old/twolanes.xml").open()

# Define lateral offset
lane_width = 3.0  # meters

# --- Create a third lanelet (straight version) ---
straight_scenario = deepcopy(scenario)

# now I want to extend the lanelets to the left a bit (the cars don't do well if placed at the border)
def extend_lanelet_start_fixed(lanelet, extension_length=10.0, num_points=5):
    """
    Extend the start of a lanelet in the fixed negative x-direction.
    :param lanelet: Lanelet object
    :param extension_length: total length to extend
    :param num_points: number of points to add
    """
    def extend_vertices(vertices):
        direction = np.array([-1.0, 0.0])  # Fixed direction: left on x-axis
        distances = np.linspace(extension_length, 0, num_points + 1)[:-1]
        new_points = [vertices[0] + d * direction for d in distances]
        return np.vstack((new_points, vertices))

    lanelet.left_vertices = extend_vertices(lanelet.left_vertices)
    lanelet.center_vertices = extend_vertices(lanelet.center_vertices)
    lanelet.right_vertices = extend_vertices(lanelet.right_vertices)


# Use left bound of lanelet 2 to ensure perfect alignment
existing_upper_lanelet = straight_scenario.lanelet_network.find_lanelet_by_id(2)
new_right = existing_upper_lanelet.left_vertices.copy()

def shift_vertices(vertices, dy):
    return np.array([[x, y + dy] for x, y in vertices])

new_left = shift_vertices(new_right, lane_width)
new_center = (new_left + new_right) / 2
new_id = 1  # leftmost
new_lanelet = Lanelet(
    left_vertices=new_left,
    center_vertices=new_center,
    right_vertices=new_right,
    lanelet_id=new_id,
    lanelet_type={LaneletType.URBAN},
    adjacent_right=2,
    adjacent_right_same_direction=True
)
existing_upper_lanelet.adj_left = 1
existing_upper_lanelet.adj_left_same_direction = True
straight_scenario.add_objects(new_lanelet)

for lanelet in straight_scenario.lanelet_network.lanelets:
    extend_lanelet_start_fixed(lanelet, extension_length=10.0, num_points=5)


# # Get dict of lanelet_id -> lanelet object from the network
# lanelet_dict = {l.lanelet_id: l for l in straight_scenario.lanelet_network.lanelets}

# # Sort lanelet IDs by vertical center position
# lanelet_ids_sorted = sorted(
#     lanelet_dict,
#     key=lambda lid: np.mean(lanelet_dict[lid].center_vertices[:, 1])
# )

# for i, lanelet_id in enumerate(lanelet_ids_sorted):
#     lanelet = lanelet_dict[lanelet_id]
#     if i > 0:
#         left_id = lanelet_ids_sorted[i - 1]
#         lanelet.adjacent_left = left_id
#         lanelet.adjacent_left_same_direction = True
#     if i < len(lanelet_ids_sorted) - 1:
#         right_id = lanelet_ids_sorted[i + 1]
#         lanelet.adjacent_right = right_id
#         lanelet.adjacent_right_same_direction = True





# draw(straight_scenario,planning_problem_set)

# Save straight three-lane scenario
writer = CommonRoadFileWriter(straight_scenario, planning_problem_set, 'Felix Gigler', 'AIT')
writer.write_to_file("scenarios_old/threelanes.xml")

# --- Create curved version ---
# Move planning problem goal state in curved version
for pp in planning_problem_set.planning_problem_dict.values():
    goal = pp.goal.state_list[0]
    if goal.position:
        goal.position.center[0] = 52.5
        goal.position.center[1] = 53.0


curved_scenario = deepcopy(straight_scenario)


def apply_curve(total_angle=np.pi/2, base_radius=50, radial_offset=0.0):
    """
    Generate lanelet boundaries using arcs from concentric circles.
    This version ignores input vertices and purely generates arc points.
    """
    n = 20  # fixed number of points for each arc
    radius = base_radius + radial_offset
    angles = np.linspace(0, total_angle, n)
    curved = [[radius * np.cos(a+3/2*np.pi), base_radius + 6 + radius * np.sin(a+3/2*np.pi)] for a in angles]
    return np.array(curved)

for i, lanelet in enumerate(curved_scenario.lanelet_network.lanelets):
    lanelet.left_vertices = apply_curve(radial_offset=lane_width / 2 + i*lane_width)
    lanelet.center_vertices = apply_curve(radial_offset=0.0 + i*lane_width)
    lanelet.right_vertices = apply_curve(radial_offset=-lane_width / 2 + i*lane_width)
    
    extend_lanelet_start_fixed(lanelet, extension_length=10.0, num_points=5)

# draw(curved_scenario, planning_problem_set)

# Save curved three-lane scenario
writer = CommonRoadFileWriter(curved_scenario, planning_problem_set, 'Felix Gigler', 'AIT')

# Optionally draw the curved scenario
# draw(curved_scenario, planning_problem_set)
writer.write_to_file("scenarios/threelanes_curved.xml")
