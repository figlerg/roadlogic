import random
import math

from typing import List, Tuple, Any, Dict

from omegaconf import OmegaConf
from copy import deepcopy

from shapely.geometry import LineString, Point

from commonroad.common.file_reader import XMLFileReader
from commonroad.common.file_writer import XMLFileWriter
from commonroad.scenario.lanelet import Lanelet, LaneletNetwork, LaneletType
from commonroad.scenario.scenario import Scenario
from commonroad.planning.planning_problem import PlanningProblem, PlanningProblemSet
from commonroad.planning.goal import GoalRegion, Interval
from commonroad.geometry.shape import Rectangle
from commonroad.scenario.state import CustomState, InitialState
from commonroad.common.file_writer import OverwriteExistingFile

from commonroad_extensions.common.utils import cut, get_orientation_by_coords, speed_interval_for_lanelet, flatten
from commonroad_extensions.scenario_generation.utils import (
    get_goal_region_on_lanelet,
    generate_planning_problem_at_timestep,
    compute_feasible_paths
)

from commonroad_extensions.scenario_generation.traffic_generation import TrafficGenerator

# Note: The assumption is that the seed was alredy set by cli.py if we want reproducible results
# TODO: Is there a way to ensure the seed was not altered?!
import random


# Simple class that generate a testing traffic in batches. 
# Each batch starts more or less together from different incoming lanelets.
# Batches start after some randomized time

class SimpleBatchedTrafficGenerator(TrafficGenerator):

    def __init__(self, config, scenario):
        super().__init__(config, scenario)

        self.intra_batch_delay_sec = 5
        self.inter_batch_delay_sec = 10

    def _generate_batch(self, initial_time_step: int, planning_problem_set: PlanningProblemSet, traffic_meta_data: dict) -> None:

        how_many_vehicles_to_generate = random.randint(self.config.traffic_flow.min_vehicles, self.config.traffic_flow.max_vehicles)
        start_agent_at_time_step = initial_time_step

        for _ in range(how_many_vehicles_to_generate):
            # Take one
            incoming_lanelet = self.incoming_lanelets[random.randint(0, len(self.incoming_lanelets) - 1)]
            # Get a random feasible path from the incoming lanelet
            outgoing_lanelet_id = random.choice([k[1] for k in self.feasible_paths.keys() if k[0] == incoming_lanelet.lanelet_id])
            outgoing_lanelet = self.scenario.lanelet_network.find_lanelet_by_id(outgoing_lanelet_id)
            # Get the corresponding goal region, this has fixed deadline
            goal_region =  get_goal_region_on_lanelet(outgoing_lanelet, self.config)
            # This will automatically assign the id to the planning problems based on what is in the scenario
            planning_problem = generate_planning_problem_at_timestep(start_agent_at_time_step, self.config, incoming_lanelet, outgoing_lanelet, goal_region, self.scenario)
            planning_problem_set.add_planning_problem(planning_problem)

            traffic_meta_data[planning_problem.planning_problem_id] = dict()
            traffic_meta_data[planning_problem.planning_problem_id]["initial_lanelet_id"] = incoming_lanelet.lanelet_id
            traffic_meta_data[planning_problem.planning_problem_id]["final_lanelet_id"] = outgoing_lanelet.lanelet_id
            traffic_meta_data[planning_problem.planning_problem_id]["air_travel_distance"] = Point(planning_problem.initial_state.position).distance(Point(goal_region.state_list[0].position.center))

            # Apply some inter-batch delay
            delay_time_step = self.intra_batch_delay_sec + int((self.intra_batch_delay_sec * random.uniform(0, 1)) / self.scenario.dt)
            start_agent_at_time_step = start_agent_at_time_step + delay_time_step


    def generate(self) -> Tuple[PlanningProblemSet, dict]:
        planning_problem_set = PlanningProblemSet()
        initial_time_step = 0
        traffic_meta_data = dict()
        while initial_time_step < self.config.traffig_generation.last_agent_starts_at_time_step:
            self._generate_batch(initial_time_step, planning_problem_set, traffic_meta_data)
            # Add at least 5 seconds after the previous batch's end
            last_batch_end_at_time_step = max([pp.initial_state.time_step for pp in planning_problem_set.planning_problem_dict.values()])
            # Compute the delay
            delay_time_step = self.inter_batch_delay_sec + int((self.inter_batch_delay_sec * random.uniform(0, 1)) / self.scenario.dt)
            # Compute the next batch initial time_step
            initial_time_step = last_batch_end_at_time_step + delay_time_step

        return planning_problem_set, traffic_meta_data
    
class SimpleBatchedTrafficGeneratorWithInitialDisplacement(SimpleBatchedTrafficGenerator):
    
    # Assume constant speed and moves away the vehicles by a given amount
    # Start all of them at time 0
    # Remove all the vehicles that are outside the simulation
    
    def __init__(self, config, scenario):     
        super().__init__(config, scenario)

        # Goal region cannot be too close to the end of the lanelet
        self.config.goal_region.distance_from_end_m = 50 + config.goal_region.length_m * 0.5


    def generate(self) -> Tuple[PlanningProblemSet, dict]:
        planning_problem_set = PlanningProblemSet()
        initial_time_step = 0
        traffic_meta_data = dict()
        while initial_time_step < self.config.traffig_generation.last_agent_starts_at_time_step:
            self._generate_batch(initial_time_step, planning_problem_set, traffic_meta_data)
            # Add at least 5 seconds after the previous batch's end
            last_batch_end_at_time_step = max([pp.initial_state.time_step for pp in planning_problem_set.planning_problem_dict.values()])
            # Compute the delay
            delay_time_step = self.inter_batch_delay_sec + int((self.inter_batch_delay_sec * random.uniform(0, 1)) / self.scenario.dt)
            # Compute the next batch initial time_step
            initial_time_step = last_batch_end_at_time_step + delay_time_step

        # At this point we have a bunch of vehicles that start at different times from the same position
        # We convert them to a bunch of vehicles that start at the same time (max time) from different position
        # We remove all the agents that are NOT anymore in the map

        # Compute Displacements from initial state
        planning_problems_to_remove = []
        for planning_problem_id, planning_problem in planning_problem_set.planning_problem_dict.items():
            # Initial Delay in time_step - Assuming we start at 0
            initial_delay = planning_problem.initial_state.time_step
            # Intitial Speed
            intial_velocity = planning_problem.initial_state.velocity * 0.5
            # Displacement assuming constant speed model
            initial_displacement = intial_velocity * initial_delay * self.scenario.dt
            
            # Ensure a minimum space before the vehicle is there
            if initial_displacement < self.config.initial_state.distance_from_beginning_m:
                initial_displacement = self.config.initial_state.distance_from_beginning_m

            # We do not have a reference path yet, so we move the vehicle forward until we find the actual lanelets in which the vehicle will start
            # given the initial displacement

            initial_lanelet_id = next(iter(self.scenario.lanelet_network.find_most_likely_lanelet_by_state([planning_problem.initial_state])))
            #
            initial_lanelet = self.scenario.lanelet_network.find_lanelet_by_id(initial_lanelet_id)
            
            while initial_displacement > initial_lanelet.distance[-1]:
                if initial_lanelet.successor is None or len(initial_lanelet.successor) == 0:
                    # Outside the map
                    initial_lanelet = None
                    break
                else:
                    initial_displacement = initial_displacement - initial_lanelet.distance[-1]
                    initial_lanelet = self.scenario.lanelet_network.find_lanelet_by_id(next(iter(initial_lanelet.successor)))
            
            if initial_lanelet is None or initial_displacement < 0.0:
                print(f"Vehicle {planning_problem_id} went outside the map")
                planning_problems_to_remove.append(planning_problem_id)
                continue

            # We have the expected initial position of the vehicle and we need to check that it is not too close to goal area
            goal_area_center_position = planning_problem.goal.state_list[0].position.center
            goal_lanelet_id = self.scenario.lanelet_network.find_lanelet_by_position([goal_area_center_position])[0][0]
            goal_lanelet = self.scenario.lanelet_network.find_lanelet_by_id(goal_lanelet_id)

            # Find the coordinate on the center vertices at the given distance
            expected_initial_position, _, _, _ = initial_lanelet.interpolate_position(initial_displacement)
            
            # Approximate distance with Euclideian distance
            distance_to_goal_area = Point(goal_area_center_position).distance(Point(expected_initial_position))

            # To travel at least 100 m before reaching the boundary of the goal area
            min_travel_distance = 100 + self.config.goal_region.length_m * 0.5      

            if distance_to_goal_area < min_travel_distance:
                print(f"Vehicle {planning_problem_id} is to close to the goal area boundaries {distance_to_goal_area - min_travel_distance}")
                planning_problems_to_remove.append(planning_problem_id)
                continue
            
            # Update the planning problem
            planning_problem.initial_state.position = expected_initial_position
            # Reset time
            planning_problem.initial_state.time_step = 0
            # Enforce standing position
            planning_problem.initial_state.velocity = 0.0
            planning_problem.initial_state.yaw_rate = 0.0
            planning_problem.initial_state.acceleration = 0.0


        planning_problem_list = list()
        for planning_problem_id, planning_problem in planning_problem_set.planning_problem_dict.items():
            if planning_problem_id not in planning_problems_to_remove:
                planning_problem_list.append(planning_problem)
            
        planning_problem_set = PlanningProblemSet(planning_problem_list)
        return planning_problem_set, traffic_meta_data

    
# def generate_normal_traffic(config: OmegaConf, goal_regions: Dict, feasible_paths, scenario: Scenario):
#     """
#     Creates some normal traffic as follows: creates a random number of vehicles at the beginning, approximate how long it will take to vehicles to reach the end, and
#     iteratively creates more traffic such that (more or less) the overall number of vehicles in the monitored traffic segment is bounded between 2 and 10

#     TODO This is a draft and empirically created for the reference scenario!
#     """

#     # Creates the planning problems that starts at time 0
#     planning_problem_set = PlanningProblemSet()
    
#     # First agent has the following id, the others will be done incrementally
#     agent_id = 10000

#     # Ramp up the simulation - In the first seconds add as many vehicles as possible
#     time_stamps = []
    
#     # TODO For debugging purposes, start the simulation after instance 0 *but still 3x*
#     timestep = 3 * 0

#     # for i in range(config.n_vehicled_mean):
#     for i in range(2):
#         # Have at least one car at time = 0
#         time_stamps.append(timestep)
#         # Validation is broken, and vehicles are somewhat placed one on top of the others?
#         delta_time = 50 #random.randint(100, 30)
#         delta_time = delta_time - (delta_time % 3)
#         timestep = timestep + delta_time

#     # Regime
#     while len(time_stamps) > 0:
#         # Pop from time_step the oldest one
#         timestep = time_stamps.pop(0)
        
#         # Generate the goal for a new problem in a way that is about 5 seconds from the current one
#         agent_id = agent_id + 1
#         planning_problem = generate_planning_problem_at_timestep(timestep, config, goal_regions, feasible_paths, scenario, agent_id, planning_problem_set)
#         planning_problem_set.add_planning_problem(planning_problem)

#         # Compute the replacement time_step
#         # sign = 1 if random.random() <= 0.5 else -1
   
#         # delta_time = config.time_step_to_complete_scenario_mean + sign + random.randint(config.time_step_to_complete_scenario_mean-config.time_step_to_complete_scenario_var, 
#         #                                                                                   config.time_step_to_complete_scenario_mean+config.time_step_to_complete_scenario_var)
#         delta_time = 50

#         # % 3 == 0 if round division
#         # Adjust to be multiple of 3 (actually its replanning frequency)
#         delta_time = delta_time - (delta_time % 3)

#         # Adjst the time step
#         timestep = timestep + delta_time

#         if len(time_stamps) > 0 and time_stamps[-1] <= config.max_time_step + config.time_step_to_complete_scenario_mean + config.time_step_to_complete_scenario_var:
#             # Put it back
#             time_stamps.append(timestep)
#         else:
#             # Keep removing planning problems until we make all of them
#             pass

#     return planning_problem_set


