import random
import math
import os

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

import matplotlib as mpl
import matplotlib.pyplot as plt

import numpy as np

# Base class to generate traffic
class TrafficGenerator():
    """
    Common base class for generating traffic
    """
    
    def __init__(self, config: OmegaConf, scenario: Scenario):
        self.config = config
        self.scenario = scenario
        self.planning_problem_set: PlanningProblemSet = None
        
        # Map parsing of common elements
        self.incoming_lanelets = [l for l in self.scenario.lanelet_network.lanelets if len(l.predecessor) == 0]
        self.outgoing_lanelets = [l for l in self.scenario.lanelet_network.lanelets if len(l.successor) == 0]
        # feasible_paths[(incoming_lanelet_id, outgoing_lanelet_id)] = lane_changes
        self.feasible_paths = compute_feasible_paths(self.scenario)

    def generate(self) -> Tuple[PlanningProblemSet, dict]:
        """
        Return the Planning problems to be used in the scenario and meta data about the traffic generation
        """
        raise NotImplementedError("Implement this method in subclasses!")
    
    # TODO Move this up or to a separate module
    def summarize(self, planning_problem_set: PlanningProblemSet, traffic_meta_data: dict) -> None:
        covered_incoming_lanelets = set()
        covered_outgoing_lanelets = set()
        print(f"Summary of traffic generation:")
        
        print(f"* Generated Vehicles")
        total_vehicles = len(planning_problem_set.planning_problem_dict.values())
        # Last vehicle will start at:
        total_duration = max([pp.initial_state.time_step for pp in planning_problem_set.planning_problem_dict.values()])
        avg_vehicle_rate = (float(total_vehicles) + 1 ) / (float(total_duration) + 1)

        print(f"  Total (veh) = {total_vehicles}")
        print(f"  Avg Rate (veh/sec)= {avg_vehicle_rate}")
        print(f"  Vehicle details")
        for planning_problem in sorted(planning_problem_set.planning_problem_dict.values(), key= lambda pp: pp.initial_state.time_step):
            incoming_lanelet = traffic_meta_data[planning_problem.planning_problem_id]['initial_lanelet_id']
            outgoing_lanelet = traffic_meta_data[planning_problem.planning_problem_id]['final_lanelet_id']
            
            print(f"\tVehicle {planning_problem.planning_problem_id}")
            print(f"\t\twill start at time {planning_problem.initial_state.time_step} from lanelet {incoming_lanelet}")
            print(f"\t\tat velocity {planning_problem.initial_state.velocity}")
            print(f"\t\twill drive to lanelet {outgoing_lanelet}")
            
            covered_incoming_lanelets.add(incoming_lanelet)
            covered_outgoing_lanelets.add(outgoing_lanelet)

        # Input lanelet coverage
        incoming_lanelets_coverage = round(float(len(covered_incoming_lanelets)) / float(len(self.incoming_lanelets)), 2)
        outgoing_lanelets_coverage = round(float(len(covered_outgoing_lanelets)) / float(len(self.outgoing_lanelets)), 2)
        
        print(f"* Lanelet Coverage:")
        print(f"    Incoming: {len(covered_incoming_lanelets)}/{len(self.incoming_lanelets)} = {incoming_lanelets_coverage}")
        print(f"    Outgoing: {len(covered_outgoing_lanelets)}/{len(self.outgoing_lanelets)} = {outgoing_lanelets_coverage}")


    def visualize(self, planning_problem_set: PlanningProblemSet, traffic_meta_data: dict, output_folder: str) -> None:
        # Plot 1: Show in time the vehicles per incoming lanelets
        x = list()
        y = list()
        segments = list()

        incoming_lanelet_ids = [ l.lanelet_id for l in self.incoming_lanelets]
        outgoing_lanelet_ids = [ l.lanelet_id for l in self.outgoing_lanelets]

        for planning_problem in sorted(planning_problem_set.planning_problem_dict.values(), key= lambda pp: pp.initial_state.time_step):
            incoming_lanelet_id = traffic_meta_data[planning_problem.planning_problem_id]['initial_lanelet_id']
            outgoing_lanelet_id = traffic_meta_data[planning_problem.planning_problem_id]['final_lanelet_id']
            initial_time_step = planning_problem.initial_state.time_step
            
            x.append(initial_time_step)
            y.append(incoming_lanelet_ids.index(incoming_lanelet_id))

            x1 = 0
            x2 = 10
            y1 = incoming_lanelet_ids.index(incoming_lanelet_id)
            y2 = outgoing_lanelet_ids.index(outgoing_lanelet_id)

            segments.append(([x1, x2], [y1, y2]))
        

        # Define the grid and labels
        def format_using_incoming_lanelet_ids(x, pos):
            if int(x) == x and x < len(incoming_lanelet_ids):
                return f"Lane {incoming_lanelet_ids[int(x)]}"
            
        def format_using_outgoing_lanelet_ids(x, pos):
            if int(x) == x and x < len(outgoing_lanelet_ids):
                return f"Lane {outgoing_lanelet_ids[int(x)]}"
            
        fig, ax = plt.subplots()
        # Draw the grid as major
        ax.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(lambda x, pos: None))
        lane_boundary_yticks = [-0.5] + [ x + 0.5 for x in range(len(incoming_lanelet_ids))]
        ax.set_yticks(lane_boundary_yticks, minor=False)
        ax.yaxis.grid(True, which='major')

        # Show the label of the lanelets id
        ax.yaxis.set_minor_formatter(mpl.ticker.FuncFormatter(format_using_incoming_lanelet_ids))
        lane_id_yticks = list(range(len(incoming_lanelet_ids)))
        ax.set_yticks(lane_id_yticks, minor=True)

        # Ensure symmetry
        ax.set_ylim([min(lane_boundary_yticks), max(lane_boundary_yticks)])

        # Plot a dot for each vehicle at the right time and lanelet
        plt.scatter(x, y)

        # Save to file
        plot_file = os.path.join(output_folder, "traffic-dispersion.png")
        plt.savefig(plot_file)
        plt.close()

        # Plot 2: Show the linkage between incoming and outgoing lanetes (normalize distance by travel distance)

        fig, ax1 = plt.subplots()
        ax2 = ax1.twinx()
        
        # On the left side x=0, index of incoming lanelet
        # On the right side x=10, index of the outgoing lanelet

        lane_boundary_yticks = [-0.5] + [ x + 0.5 for x in range(max(len(incoming_lanelet_ids), len(outgoing_lanelet_ids)))]
        # Ensure symmetry: TODO centering would be better, so we need an offset on the min one
        ax1.set_ylim([min(lane_boundary_yticks), max(lane_boundary_yticks)])
        ax2.set_ylim([min(lane_boundary_yticks), max(lane_boundary_yticks)])

        # Show the label of the lanelets id
        ax1.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(format_using_incoming_lanelet_ids))
        ax2.yaxis.set_major_formatter(mpl.ticker.FuncFormatter(format_using_outgoing_lanelet_ids))

        incoming_lane_id_yticks = list(range(len(incoming_lanelet_ids)))
        outgoing_lane_id_yticks = list(range(len(outgoing_lanelet_ids)))

        ax1.set_yticks(incoming_lane_id_yticks, minor=True)
        ax2.set_yticks(outgoing_lane_id_yticks, minor=True)

        for segment in segments:
            plt.plot(segment[0], segment[1], color="black")

        # Save to file
        plot_file = os.path.join(output_folder, "traffic-interconnection.png")
        plt.savefig(plot_file)
        plt.close()