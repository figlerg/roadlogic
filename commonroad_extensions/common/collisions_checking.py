# Check whether there's a collision in the input scenario. 
# This can be used to check whether there's a collision in the original scenario (under cr_scenario) and in the one executed
# with the ego vehicle (under experiments)

# The following code has been taken and adapted from: https://commonroad.in.tum.de/tutorials/drivability-checker/05_collision_checks_dynamic_obstacles.html
import sys
import numpy as np
import matplotlib.pyplot as plt
import os
import csv

from time import time
from typing import List, Any, Optional, Tuple
from copy import deepcopy

# commonroad
from commonroad.scenario.scenario import Scenario
from commonroad.scenario.obstacle import DynamicObstacle

from commonroad.prediction.prediction import Trajectory, TrajectoryPrediction, SetBasedPrediction
from commonroad.visualization.mp_renderer import MPRenderer

from commonroad.geometry.shape import Rectangle
#commonroad-io
from commonroad.common.file_reader import CommonRoadFileReader

# commonroad_dc
import commonroad_dc.pycrcc as pycrcc
from commonroad_dc.collision.collision_detection.pycrcc_collision_dispatch import create_collision_checker, create_collision_object
from commonroad_dc.boundary.boundary import create_road_boundary_obstacle

from commonroad_dc.collision.trajectory_queries import trajectory_queries
from commonroad_dc.pycrcc.Util import trajectory_enclosure_polygons_static

# Oper and return the cr scenario and planning problems
def open_scenario(scenario_filename):
    crfr = CommonRoadFileReader(scenario_filename)
    scenario, planning_problem_set = crfr.open()
    return scenario, planning_problem_set

def remove_obstacle_from_scenario(obstacle_id: int, scenario: Scenario) -> Tuple[DynamicObstacle, Scenario]:
    new_scenario = deepcopy(scenario)
    obstacle = new_scenario.obstacle_by_id(obstacle_id)
    new_scenario.remove_obstacle(obstacle)
    return obstacle, new_scenario

def remove_all_obstacles_from_scenario(scenario: Scenario) -> Scenario:
    new_scenario = deepcopy(scenario)
    for obstacle_id in [obstacle.obstacle_id for obstacle in scenario.obstacles]:
        obstacle = new_scenario.obstacle_by_id(obstacle_id)
        new_scenario.remove_obstacle(obstacle)
    return new_scenario

def wrap_obstacle(obstacle: DynamicObstacle, buffer_m: float = 0.1):
    # Wrap the original ego vehicle in a buffer and repack it as DynamicObstacle
    original_trajectory = obstacle.prediction.trajectory
    original_shape: Rectangle  = obstacle.obstacle_shape

    buffered_shape = Rectangle(length=original_shape.length + 2 * buffer_m, width=original_shape.width + 2 * buffer_m)
    buffered_prediction = TrajectoryPrediction(trajectory=original_trajectory, shape=buffered_shape)
    # # create Ego Vehicle obstacle from trajectory
    buffered_obstacle = DynamicObstacle(obstacle_id=obstacle.obstacle_id,
                                           obstacle_type=obstacle.obstacle_type,
                                           initial_state=obstacle.initial_state,
                                           obstacle_shape=buffered_shape,
                                           prediction=buffered_prediction)
    return buffered_obstacle

def check_road_compliance(ego_vehicle_id, original_scenario, buffer_m=0.0):
    # Remove the ego from the scenario so we get its obstacle
    original_ego_vehicle, scenario = remove_obstacle_from_scenario(ego_vehicle_id, original_scenario)
    # Wrap the ego vehicle in a security buffer to ease collision checking
    # buffered_ego_vehicle = wrap_obstacle(original_ego_vehicle, buffer_m=buffer_m)
    # create ego vehicle collision object
    # ego_vehicle_co = create_collision_object(buffered_ego_vehicle)
    ego_vehicle_co = create_collision_object(original_ego_vehicle)
    # Remove all the obstacles from the scenario
    scenario = remove_all_obstacles_from_scenario(scenario)
    # create collision checker from scenario without obstacles
    cc = create_collision_checker(scenario)
    # create the road boundary object
    _, road_boundary = create_road_boundary_obstacle(scenario)
    # add road boundary to collision checker
    cc.add_collision_object(road_boundary)
    # Again: check if ego vehicle collides
    # return cc.collide(ego_vehicle_co)
    for t in range(ego_vehicle_co.time_start_idx(), ego_vehicle_co.time_end_idx()+1):
        if cc.collide(ego_vehicle_co.obstacle_at_time(t)):
            return t
    return -1


def check_collisions_with_obstacles(ego_vehicle_id, original_scenario, buffer_m=0.0) -> int:
    # The code below seems to be broken. For 1000 it reports a collision at t=0, but there's no
    # collision at that time. As can be seen by running the following code:
    # [npc_co.obstacle_at_time(t).collide(ego_vehicle_co.obstacle_at_time(t)) for t in range(ego_vehicle_co.time_start_idx(), ego_vehicle_co.time_end_idx()+1)]
    # Remove the ego from the scenario
    original_ego_vehicle, scenario = remove_obstacle_from_scenario(ego_vehicle_id, original_scenario)
    # Wrap the ego vehicle in a security buffer to ease collision checking
    # buffered_ego_vehicle = wrap_obstacle(original_ego_vehicle, buffer_m=buffer_m)
    # create ego vehicle collision object
    # ego_vehicle_co = create_collision_object(buffered_ego_vehicle)
    ego_vehicle_co = create_collision_object(original_ego_vehicle)
    # create collision checker from scenario
    cc = create_collision_checker(scenario)
    # check if ego vehicle collides
    # if cc.collide(ego_vehicle_co):
    # Return the instant of the first collision, or -1 instead
    for t in range(ego_vehicle_co.time_start_idx(), ego_vehicle_co.time_end_idx()+1):
        if cc.collide(ego_vehicle_co.obstacle_at_time(t)):
            return t
    return -1

# def check_collisions(original_scenario: Scenario, ego_vehicle_id: int, buffer_m: float):
    # return {
        # "has_collisions_with_road": check_road_compliance(ego_vehicle_id, original_scenario, buffer_m),
        # "has_collisions_with_obstacles": check_collisions_with_obstacles(ego_vehicle_id, original_scenario, buffer_m)
    # }

# def describe(scenario: Scenario):
#     # Collect some attributes about the scenario
#     dynamic_obstacles = [dob for dob in scenario.obstacles if isinstance(dob, DynamicObstacle)]
#     start_at = min([sys.maxsize * 2] + [obstacle.initial_state.time_step for obstacle in dynamic_obstacles])
#     end_at = max([-1] + [s.time_step for obstacle in dynamic_obstacles for s in obstacle.prediction.trajectory.state_list])
#     duration = end_at - start_at
#     return {
#         "n_vehicles": len(dynamic_obstacles),
#         "start_at": start_at,
#         "end_at": end_at,
#         "duration": duration
#     }

# def parse_name(output_folder, parameter_names):
#     parameters_dict = {}
#     output_folder_name = os.path.basename(output_folder)
#     for name, value in zip(parameter_names, output_folder_name.split('_')):
#         parameters_dict[name] = value
#     return parameters_dict
    
# if __name__ == "__main__":
#     # TODO Define a CLI
#     output_folder = sys.argv[1]
#     os.makedirs(output_folder, exist_ok=True)

#     # Assumption: scenario_xml_file is executed_scenario.xml and it is inside a folder named after the paramters from the csv file
#     scenario_xml_file = sys.argv[2]
#     scenario_xml_folder = os.path.basename(os.path.dirname(scenario_xml_file))
#     ego_vehicle_id = int(sys.argv[3])
    
#     buffer_m = 0.2
#     # open the example scenario with trajectory predictions
#     original_scenario, _ = open_scenario(scenario_xml_file)
#     # THIS IS HARD CODED!!!
#     parameters_dict = parse_name(scenario_xml_folder, ["Ve0", "Ve0-Vo0", "dy0", "dx0", "Vy", "result"])

#     attributes_dict = describe(original_scenario)
#     attributes_dict["safety_buffer_m"] = buffer_m
#     collisions_dict = check_collisions(original_scenario, ego_vehicle_id, buffer_m)

#     report_dict = parameters_dict | attributes_dict | collisions_dict
#     fieldnames = list(parameters_dict.keys()) + list(attributes_dict.keys()) + list(collisions_dict.keys())
#     output_file = os.path.join(output_folder, "report.csv")
    
#     with open(output_file, 'w') as csvfile:
#         writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
#         writer.writeheader()  # Write header row    
#         writer.writerows([report_dict])  # Write data rows
