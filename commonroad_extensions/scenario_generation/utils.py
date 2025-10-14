import shutil
import sqlite3

from copy import deepcopy
from typing import Tuple, List

import networkx as nx
import math
import numpy as np
import pandas as pd
import random
import os
import sys
import importlib

from omegaconf import OmegaConf

from shapely import get_coordinates
from shapely.geometry import Point, LineString
from shapely.affinity import rotate, scale, translate

from commonroad.common.file_reader import XMLFileReader
from commonroad.common.file_writer import XMLFileWriter
from commonroad.scenario.lanelet import Lanelet, LaneletNetwork, LaneletType
from commonroad.scenario.scenario import Scenario
from commonroad.planning.planning_problem import PlanningProblem, PlanningProblemSet
from commonroad.planning.goal import GoalRegion, Interval
from commonroad.geometry.shape import Rectangle
from commonroad.scenario.state import CustomState, InitialState
from commonroad.common.file_writer import OverwriteExistingFile

from cr_scenario_handler.utils.agent_status import AgentStatus

from commonroad_extensions.common.utils import cut, get_orientation_by_coords, speed_interval_for_lanelet, flatten

##### ROAD GENERATION 

def compute_orientation(initial_point: list = [], terminal_point: list = []):
    # orientation from initial_point to terminal_point
    x = (terminal_point[0] - initial_point[0])
    y = (terminal_point[1] - initial_point[1])
    # special cases
    if x < 0 and y == 0:
        return np.pi
    if x > 0 and y == 0:
        return 0
    if x == 0 and y < 0:
        return np.pi * 3 / 2
    if x == 0 and y > 0:
        return np.pi / 2
    if x == 0 and y == 0:
        raise ValueError('invalid orientation computation')
    # compute orientation
    orientation = abs(np.arctan(y / x))
    # adjust orientation according to quadrant
    if x > 0 and y > 0:
        pass
    elif x < 0 and y > 0:
        orientation = np.pi - orientation
    elif x < 0 and y < 0:
        orientation = np.pi + orientation
    elif x > 0 and y < 0:
        orientation = 2 * np.pi - orientation
    return orientation

def rotate_primitive(coordinates: {}, rotation: float):
    # compute center point
    cx = (sum(coordinates['left']['x']) + sum(coordinates['right']['x'])) / (len(coordinates['left']['x']) * 2)
    cy = (sum(coordinates['left']['y']) + sum(coordinates['right']['y'])) / (len(coordinates['left']['y']) * 2)
    # rotate left border around (cx, cy)
    left_border = {'x': [], 'y': []}
    for i in range(len(coordinates['left']['x'])):
        x = coordinates['left']['x'][i]
        y = coordinates['left']['y'][i]
        new_x = ((x - cx) * np.cos(rotation) + (y - cy) * np.sin(rotation)) + cx
        new_y = ((- x + cx) * np.sin(rotation) + (y - cy) * np.cos(rotation)) + cy
        left_border['x'].append(new_x)
        left_border['y'].append(new_y)
    # rotate right border around (cx, cy)
    right_border = {'x': [], 'y': []}
    for i in range(len(coordinates['right']['x'])):
        x = coordinates['right']['x'][i]
        y = coordinates['right']['y'][i]
        new_x = ((x - cx) * np.cos(rotation) + (y - cy) * np.sin(rotation)) + cx
        new_y = ((- x + cx) * np.sin(rotation) + (y - cy) * np.cos(rotation)) + cy
        right_border['x'].append(new_x)
        right_border['y'].append(new_y)
    return {'left': left_border, 'right': right_border}

def translate_primitive(coordinates: {}, left_point: [], right_point: []):
    # compute translation orientation and translation distance
    figure_origin = (coordinates['left']['x'][0], coordinates['left']['y'][0])
    orientation = compute_orientation(figure_origin, left_point)
    distance = np.sqrt(np.power(figure_origin[0] - left_point[0], 2) + np.power(figure_origin[1] - left_point[1], 2))
    # translate left border
    left_border = {'x': [], 'y': []}
    for i in range(len(coordinates['left']['x'])):
        x = coordinates['left']['x'][i]
        y = coordinates['left']['y'][i]
        new_x = x + np.cos(orientation) * distance
        new_y = y + np.sin(orientation) * distance
        left_border['x'].append(new_x)
        left_border['y'].append(new_y)
    # translate right border
    right_border = {'x': [], 'y': []}
    for i in range(len(coordinates['right']['x'])):
        x = coordinates['right']['x'][i]
        y = coordinates['right']['y'][i]
        new_x = x + np.cos(orientation) * distance
        new_y = y + np.sin(orientation) * distance
        right_border['x'].append(new_x)
        right_border['y'].append(new_y)
    return {'left': left_border, 'right': right_border}

def fit_primitive(coordinates: dict = {}, connection_line: dict = {}):
    left_point = connection_line['left']
    right_point = connection_line['right']
    primitive_left = [coordinates['left']['x'][0], coordinates['left']['y'][0]]
    primitive_right = [coordinates['right']['x'][0], coordinates['right']['y'][0]]
    # compute orientation and rotate coordinates
    connection_line_orientation = compute_orientation(left_point, right_point)
    primitive_orientation = compute_orientation(primitive_left, primitive_right)
    orientation = primitive_orientation - connection_line_orientation
    rotated_primitive = rotate_primitive(coordinates, orientation)
    # translate coordinates
    translated_primitive = translate_primitive(rotated_primitive, left_point, right_point)
    left_border = translated_primitive['left']
    right_border = translated_primitive['right']
    # if plot is True:
    #     x_values = [left_point[0], right_point[0]]
    #     y_values = [left_point[1], right_point[1]]
    #     plt.plot(x_values, y_values, c='g')
    #     plt.plot(left_border['x'], left_border['y'], c='b')
    #     plt.plot(right_border['x'], right_border['y'], c='r')
    #     plt.axis('scaled')
    #     plt.show()
    return {'left': left_border, 'right': right_border}

def create_straight(extension_distance: float, width: float, plot: bool = False):
    precision = 10
    x_coordinates = np.linspace(0, extension_distance, precision)
    left_border = {'x': x_coordinates, 'y': [0] * precision}
    right_border = {'x': x_coordinates, 'y': [width] * precision}
    # if plot is True:
    #     plt.plot(left_border['x'], left_border['y'], c='b')
    #     plt.plot(right_border['x'], right_border['y'], c='r')
    #     plt.axis('scaled')
    #     plt.show()
    return {'left': left_border, 'right': right_border}

def extend_straight(lanelet: Lanelet, extension_distance: float, fuse: bool, extend_rear: bool):
    # extract connection_line and width
    if extend_rear is True:
        connection_line = {'left': [lanelet.right_vertices[-1][0], lanelet.right_vertices[-1][1]],
                           'right': [lanelet.left_vertices[-1][0], lanelet.left_vertices[-1][1]]}
    else:
        connection_line = {'left': [lanelet.left_vertices[0][0], lanelet.left_vertices[0][1]],
                           'right': [lanelet.right_vertices[0][0], lanelet.right_vertices[0][1]]}
    width = np.sqrt(np.power(connection_line['left'][0] - connection_line['right'][0], 2) +
                    np.power(connection_line['left'][1] - connection_line['right'][1], 2))
    # create straight extension
    extension = create_straight(extension_distance, width)
    # translate and rotate extension
    transformed_extension = fit_primitive(extension, connection_line)
    # compute center vertices
    left = transformed_extension['left']
    right = transformed_extension['right']
    center = {'x': [], 'y': []}
    for i in range(len(left['x'])):
        center['x'].append((left['x'][i] + right['x'][i]) / 2)
        center['y'].append((left['y'][i] + right['y'][i]) / 2)
    
    if fuse:
       # merge vertices
        left_vertices = deepcopy(lanelet.left_vertices)
        center_vertices = deepcopy(lanelet.center_vertices)
        right_vertices = deepcopy(lanelet.right_vertices)
        # skip first coordinate
        for i in range(1, len(left['x'])):
            if extend_rear is True:
                left_vertices = np.vstack((left_vertices, [right['x'][i], right['y'][i]]))
                center_vertices = np.vstack((center_vertices, [center['x'][i], center['y'][i]]))
                right_vertices = np.vstack((right_vertices, [left['x'][i], left['y'][i]]))
            else:
                left_vertices = np.vstack(([left['x'][i], left['y'][i]], left_vertices))
                center_vertices = np.vstack(([center['x'][i], center['y'][i]], center_vertices))
                right_vertices = np.vstack(([right['x'][i], right['y'][i]], right_vertices))
        new_vertices = {'left': left_vertices, 'center': center_vertices, 'right': right_vertices}
    else:
        # skip first coordinate i = 0 
        # Initialize the arrays
        i = 0
        left_vertices = np.array([right['x'][i], right['y'][i]]) if extend_rear else np.array([left['x'][i], left['y'][i]])
        center_vertices = np.array([center['x'][i], center['y'][i]])
        right_vertices = np.array([left['x'][i], left['y'][i]]) if extend_rear else np.array([right['x'][i], right['y'][i]])
        #
        for i in range(1, len(left['x'])):
            if extend_rear is True:
                left_vertices = np.vstack((left_vertices, [right['x'][i], right['y'][i]]))
                center_vertices = np.vstack((center_vertices, [center['x'][i], center['y'][i]]))
                right_vertices = np.vstack((right_vertices, [left['x'][i], left['y'][i]]))
            else:
                left_vertices = np.vstack(([left['x'][i], left['y'][i]], left_vertices))
                center_vertices = np.vstack(([center['x'][i], center['y'][i]], center_vertices))
                right_vertices = np.vstack(([right['x'][i], right['y'][i]], right_vertices))
        new_vertices = {'left': left_vertices, 'center': center_vertices, 'right': right_vertices}

    return new_vertices

def extend_the_incoming_lanelets_with_a_straight(scenario: Scenario, planning_problem_set: PlanningProblemSet,
                                                 extension_distance: float, fuse_lanelets: bool, keep_original_adj: bool) -> LaneletNetwork:
    """
    Add lanelets at the beginning of the road. Fuse them if necessary
    """
    original_lanelet_network = scenario.lanelet_network
    if extension_distance == 0.0:
        return original_lanelet_network
    elif extension_distance < 0.0:
        raise ValueError('extension_distance must be greater than or equal to 0.0')
    else:
        new_lanelet_network = deepcopy(original_lanelet_network)

        if fuse_lanelets:
            for lanelet_in_new_lanelet_network in [ new_lanelet_network.find_lanelet_by_id(lanelet.lanelet_id) for lanelet in original_lanelet_network.lanelets if len(lanelet.predecessor) == 0]:
                new_vertices = extend_straight(lanelet_in_new_lanelet_network, extension_distance, fuse=True, extend_rear=False)
            
                # TODO Incomplete
                # build the new lanelet that replaces the old one in the new_lanelet_network
                replacement_lanelet = Lanelet(left_vertices=new_vertices['left'],
                                        center_vertices=new_vertices['center'],
                                        right_vertices=new_vertices['right'],
                                        # Lane Marking
                                        line_marking_left_vertices=lanelet_in_new_lanelet_network.line_marking_left_vertices,
                                        line_marking_right_vertices=lanelet_in_new_lanelet_network.line_marking_right_vertices,
                                        # Connections
                                        predecessor=lanelet_in_new_lanelet_network.predecessor,
                                        successor=lanelet_in_new_lanelet_network.successor,
                                        adjacent_left=lanelet_in_new_lanelet_network.adj_left,
                                        adjacent_left_same_direction=lanelet_in_new_lanelet_network.adj_left_same_direction,
                                        adjacent_right=lanelet_in_new_lanelet_network.adj_right,
                                        adjacent_right_same_direction=lanelet_in_new_lanelet_network.adj_right_same_direction,
                                        #
                                        lanelet_id= lanelet_in_new_lanelet_network.lanelet_id,
                                        lanelet_type=lanelet_in_new_lanelet_network.lanelet_type)
            
                # TODO Fix the connections !

                # Replace the original lanelet with the new one!
                new_lanelet_network.remove_lanelet(lanelet_in_new_lanelet_network.lanelet_id)
                new_lanelet_network.add_lanelet(replacement_lanelet)

                # Plot original
                def debug_plot():
                    from commonroad.visualization.mp_renderer import MPRenderer
                    import matplotlib.pyplot as plt
                    mpr = MPRenderer()
                    new_lanelet_network.draw(mpr)
                    mpr.render()
                    plt.savefig(f"extending_{lanelet_in_new_lanelet_network.lanelet_id}.png")
                
                # debug_plot()

        else:
            # Find the first available ID
            existing_ids = list(planning_problem_set.planning_problem_dict.keys())
            existing_ids = existing_ids + [o.obstacle_id for o in scenario.obstacles]
            existing_ids = existing_ids + [lanelet.lanelet_id for lanelet in original_lanelet_network.lanelets]

            adj_map = {}
            for index, lanelet_in_new_lanelet_network in enumerate([ new_lanelet_network.find_lanelet_by_id(lanelet.lanelet_id) for lanelet in original_lanelet_network.lanelets if len(lanelet.predecessor) == 0], start=1):
                
                new_lanelet_id = scenario.generate_object_id()
                while new_lanelet_id in existing_ids:
                    new_lanelet_id = scenario.generate_object_id()

                # Compute the new vertices after the extension
                new_vertices = extend_straight(lanelet_in_new_lanelet_network, extension_distance, fuse=False,extend_rear=False)
                
                # TODO Incomplete
                # build the new lanelet that replaces the old one in the new_lanelet_network
                new_lanelet = Lanelet(left_vertices=new_vertices['left'],
                                        center_vertices=new_vertices['center'],
                                        right_vertices=new_vertices['right'],
                                        lanelet_id= new_lanelet_id,
                                        lanelet_type=lanelet_in_new_lanelet_network.lanelet_type)
                # Fix the connections
                new_lanelet_network.add_lanelet(new_lanelet)
                lanelet_in_new_lanelet_network.add_predecessor(new_lanelet.lanelet_id)
                new_lanelet.add_successor(lanelet_in_new_lanelet_network.lanelet_id)

                adj_map[lanelet_in_new_lanelet_network.lanelet_id] = {
                    "extended_by": new_lanelet.lanelet_id
                }
                
                if keep_original_adj:
                    # Iterate over the extended lanelets
                    for lanelet_in_new_lanelet_network in [new_lanelet_network.find_lanelet_by_id(lanelet_id) for lanelet_id in adj_map.keys()]:
                        
                        extended_by = new_lanelet_network.find_lanelet_by_id(adj_map[lanelet_in_new_lanelet_network.lanelet_id]["extended_by"])

                        # Fix adj
                        if lanelet_in_new_lanelet_network.adj_left:
                            # Ensure the extended one is also linked to the lanelet extending the adj of the original one
                            adj_left_extended_by = new_lanelet_network.find_lanelet_by_id(adj_map[lanelet_in_new_lanelet_network.adj_left]["extended_by"])
                            extended_by.adj_left = adj_left_extended_by.lanelet_id

                        if lanelet_in_new_lanelet_network.adj_right:
                            adj_right_extended_by = new_lanelet_network.find_lanelet_by_id(adj_map[lanelet_in_new_lanelet_network.adj_right]["extended_by"])
                            extended_by.adj_right = adj_right_extended_by.lanelet_id

        return new_lanelet_network
    
def extend_the_outgoing_lanelets_with_a_straight(scenario: Scenario, planning_problem_set: PlanningProblemSet, extension_distance: float, fuse_lanelets: bool, keep_original_adj: bool) -> LaneletNetwork:
    """
    TODO Extend_incoming lanelets must be updated to fix the issue of attributes

    Add lanelets by the end of the road
    """
    original_lanelet_network = scenario.lanelet_network

    if extension_distance == 0.0:
        return original_lanelet_network
    elif extension_distance < 0.0:
        raise ValueError('extension_distance must be greater than or equal to 0.0')
    else:

        new_lanelet_network = deepcopy(original_lanelet_network)
        
        if fuse_lanelets:

            for outgoing_lanelet_id, outgoing_lanelet_in_new_lanelet_network in [(l.lanelet_id, l) for l in new_lanelet_network.lanelets if len(l.successor) == 0]:

                original_lanelet = original_lanelet_network.find_lanelet_by_id(outgoing_lanelet_id)

                # Create the new vertices                
                new_vertices = extend_straight(outgoing_lanelet_in_new_lanelet_network, extension_distance, fuse=True, extend_rear=True)

                # Build the new lanelet that replaces the old one in the new_lanelet_network fix all the attributes using the original lanelet
                replacement_lanelet = Lanelet(left_vertices=new_vertices['left'],
                                        center_vertices=new_vertices['center'],
                                        right_vertices=new_vertices['right'],
                                        # Lane Marking
                                        line_marking_left_vertices=original_lanelet.line_marking_left_vertices,
                                        line_marking_right_vertices=original_lanelet.line_marking_right_vertices,
                                        # Connections
                                        predecessor=original_lanelet.predecessor,
                                        successor=original_lanelet.successor,
                                        adjacent_left=original_lanelet.adj_left,
                                        adjacent_left_same_direction=original_lanelet.adj_left_same_direction,
                                        adjacent_right=original_lanelet.adj_right,
                                        adjacent_right_same_direction=original_lanelet.adj_right_same_direction,
                                        #
                                        lanelet_id= original_lanelet.lanelet_id,
                                        lanelet_type=original_lanelet.lanelet_type)
            
                # Replace the original lanelet with the new one!
                # Removing a lanelet from the network breaks the lanelet structure so we need to fix it back!
                new_lanelet_network.remove_lanelet(outgoing_lanelet_in_new_lanelet_network.lanelet_id)
                
                # Add the new lanelet
                new_lanelet_network.add_lanelet(replacement_lanelet)

                # TODO The same is needed to extend_incoming_lanelet method above!

                # Fix the connections of the "other" lanelets linked to this one (the links of this with the others is taken care of in its initialization)
                # We use the "original network to help"
                for l in original_lanelet_network.lanelets:
                    # Find the corresponding lanelet in the new network
                    new_l = new_lanelet_network.find_lanelet_by_id(l.lanelet_id)

                    if l.adj_left == outgoing_lanelet_id:
                        # The replaced lanelet was at the left of l
                        new_l.adj_left = outgoing_lanelet_id
                        new_l.adj_left_same_direction = l.adj_left_same_direction
                    if l.adj_right == outgoing_lanelet_id:
                        # The replaced lanelet was at the right of l
                        new_l.adj_right = outgoing_lanelet_id
                        new_l.adj_right_same_direction = l.adj_right_same_direction
                    if outgoing_lanelet_id in l.successor:
                        # The replaced lanelet was a successor of l
                        new_l.add_successor(outgoing_lanelet_id)
                    if outgoing_lanelet_id in l.predecessor:
                        # The replaced lanelet was a predecessor of l
                        new_l.add_predecessor(outgoing_lanelet_id)
        else:
            # Find the first available ID = use scenario.generate_id()
            existing_ids = list(planning_problem_set.planning_problem_dict.keys())
            existing_ids = existing_ids + [o.obstacle_id for o in scenario.obstacles]
            existing_ids = existing_ids + [lanelet.lanelet_id for lanelet in original_lanelet_network.lanelets]

            adj_map = {}

            # Select the outgoing lanelets as those that do not have any successor. But return the corresponding lanelet in the new network so we
            #   can properly set their attributes
            for index, outgoing_lanelet_in_new_lanelet_network in enumerate([new_lanelet_network.find_lanelet_by_id(lanelet.lanelet_id) for lanelet in original_lanelet_network.lanelets if len(lanelet.successor) == 0], start=1):
                
                lanelet_id = scenario.generate_object_id()
                while lanelet_id in existing_ids:
                    scenario.generate_object_id()
                
                # TODO It might be necessary to update this code as well
                new_vertices = extend_straight(outgoing_lanelet_in_new_lanelet_network, extension_distance, fuse=False, extend_rear=True)
                
                # build the new lanelet
                new_lanelet = Lanelet(left_vertices=new_vertices['left'],
                                        center_vertices=new_vertices['center'],
                                        right_vertices=new_vertices['right'],
                                        lanelet_id=lanelet_id,
                                        # adjacent_left=lanelet.adj_left,
                                        # adjacent_left_same_direction=lanelet.adj_left_same_direction,
                                        # adjacent_right=lanelet.adj_right,
                                        # adjacent_right_same_direction=lanelet.adj_right_same_direction,
                                        # predecessor=lanelet.predecessor,
                                        # successor=lanelet.successor,
                                        lanelet_type=outgoing_lanelet_in_new_lanelet_network.lanelet_type)
                # Fix the connections
                outgoing_lanelet_in_new_lanelet_network.add_successor(new_lanelet.lanelet_id)
                new_lanelet.add_predecessor(outgoing_lanelet_in_new_lanelet_network.lanelet_id)

                adj_map[outgoing_lanelet_in_new_lanelet_network.lanelet_id] = {
                    "extended_by": new_lanelet.lanelet_id
                }
                
                # print(f"Adding lanelet {new_lanelet}")
                new_lanelet_network.add_lanelet(new_lanelet)

            if keep_original_adj:
                # Iterate over the extended lanelets
                for outgoing_lanelet_in_new_lanelet_network in [new_lanelet_network.find_lanelet_by_id(lanelet_id) for lanelet_id in adj_map.keys()]:
                    
                    extended_by = new_lanelet_network.find_lanelet_by_id(adj_map[outgoing_lanelet_in_new_lanelet_network.lanelet_id]["extended_by"])

                    # Fix adj
                    if outgoing_lanelet_in_new_lanelet_network.adj_left:
                        # Ensure the extended one is also linked to the lanelet extending the adj of the original one
                        adj_left_extended_by = new_lanelet_network.find_lanelet_by_id(adj_map[outgoing_lanelet_in_new_lanelet_network.adj_left]["extended_by"])
                        extended_by.adj_left = adj_left_extended_by.lanelet_id
                        extended_by.adj_left_same_direction = outgoing_lanelet_in_new_lanelet_network.adj_left_same_direction

                    if outgoing_lanelet_in_new_lanelet_network.adj_right:
                        adj_right_extended_by = new_lanelet_network.find_lanelet_by_id(adj_map[outgoing_lanelet_in_new_lanelet_network.adj_right]["extended_by"])
                        extended_by.adj_right = adj_right_extended_by.lanelet_id
                        extended_by.adj_right_same_direction = outgoing_lanelet_in_new_lanelet_network.adj_right_same_direction

        return new_lanelet_network

##### GOAL AREA GENERATION
def replace_lanelet_network_in_scenario(scenario: Scenario, lanelet_network: LaneletNetwork) -> None:
    for lanelet_id in [l.lanelet_id for l in scenario.lanelet_network.lanelets[:]]:
        scenario.lanelet_network.remove_lanelet(lanelet_id)

    for lanelet in [l for l in lanelet_network.lanelets]:
        scenario.lanelet_network.add_lanelet(lanelet)

def load_scenario_executor(output_folder: str, debug: bool, verbose: bool, tranche_size: int, additional_config: OmegaConf = None):
    # Add the Frenetix Framework (We do this because we need a patched version)
    # return se_class(output_folder, debug=debug)
    # We install the framework using pip install -e .
    # frenetix_framework_root = os.path.join(os.path.dirname(os.path.realpath(__file__)), "Frenetix-Motion-Planner")
    # sys.path.append(frenetix_framework_root)
    from commonroad_extensions.scenario_execution.stitched_execution import FrenetixScenarioExecution
    # TODO Is the driving agent name necessary?
    return FrenetixScenarioExecution(output_folder, debug=debug, driving_agent_name="frenetix", verbose=verbose,
                                     tranche_size=tranche_size,
                                     additional_config=additional_config)

def _define_circle(p1, p2, p3):
    """
    Returns the center and radius of the circle passing the given 3 points.
    In case the 3 points form a line, returns (None, infinity).
    """
    temp = p2[0] * p2[0] + p2[1] * p2[1]
    bc = (p1[0] * p1[0] + p1[1] * p1[1] - temp) / 2
    cd = (temp - p3[0] * p3[0] - p3[1] * p3[1]) / 2
    det = (p1[0] - p2[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p2[1])

    if abs(det) < 1.0e-6:
        return None, np.inf

    # Center of circle
    cx = (bc * (p2[1] - p3[1]) - cd * (p1[1] - p2[1])) / det
    cy = ((p1[0] - p2[0]) * cd - (p2[0] - p3[0]) * bc) / det
    center = Point(cx, cy)

    radius = np.sqrt((cx - p1[0]) ** 2 + (cy - p1[1]) ** 2)
    return center, radius

def max_curvature(nodes: List[Tuple[float, float]], w=5):
    min_radius = np.inf
    for i in range(len(nodes) - w):
        p1 = nodes[i]
        p2 = nodes[i + int((w - 1) / 2)]
        p3 = nodes[i + (w - 1)]

        # We care only about the radius of the circle here
        _, radius = _define_circle(p1, p2, p3)
        if radius < min_radius:
            min_radius = radius
    # Max curvature is the inverse of Min radius
    max_curvature = 1.0 / min_radius
    return max_curvature

def get_goal_region_on_lanelet(lanelet: Lanelet, config: OmegaConf) -> GoalRegion:
    """
    Return the Rectangle corresponding to the Goal Area for the given lanelet. 
    """
    # reversed_center_vertices = LineString(lanelet.center_vertices[::-1])
    # Cut the lanelet at the end by the given 
    # goal_center_vertices: LineString = cut(reversed_center_vertices, config.goal_region.distance_from_end_m)[0]
    # TODO: Is this really OK?!
    # goal_center = goal_center_vertices.centroid

    goal_center_coords, _, _, _ = lanelet.interpolate_position( (lanelet.distance[-1] - config.goal_region.distance_from_end_m) )
    last_point_coords, _, _, _ = lanelet.interpolate_position( (lanelet.distance[-1] - config.goal_region.distance_from_end_m + 1) )
 
    goal_center = Point(goal_center_coords)
    last_point = Point(last_point_coords)

    # last_point is at index 0 because vertices were reversed previously
    # last_point = goal_center_vertices.coords[0] 
    # orientation = get_orientation_by_coords((goal_center.x, goal_center.y), (last_point[0], last_point[1]))
    orientation = get_orientation_by_coords((goal_center.x, goal_center.y), (last_point.x, last_point.y))

    goal_area = Rectangle(config.goal_region.length_m, config.goal_region.width_m, np.array([goal_center.x, goal_center.y]), orientation)
    # Does this change the way the planners drive? For instance, if they are spawn at time X, but need to drive until T they might adapt their speed?
    duration = random.randint(config.goal_region.min_duration_time_step, config.goal_region.max_duration_time_step)

    goal_state_list = [CustomState(position=goal_area, time_step=Interval(0, duration))]

    return GoalRegion(goal_state_list)
#####
# def debug_plot(lanelet_network):
#     from commonroad.visualization.mp_renderer import MPRenderer
#     import matplotlib.pyplot as plt
#     mpr = MPRenderer()
#     lanelet_network.draw(mpr)
#     mpr.render()
#     plt.show()

def compute_feasible_paths(scenario: Scenario):
    """
      Add a warm up zone to the scenario wehre to spawn vehicles. To generate different distributions we can place them closers/farther from
      the start of the original road

      NOTE: This does not define a position in the lanelet, but only the lanelet id!
      """
    # temp_scenario = deepcopy(scenario)
    # # BUG: Also if the lanelet extensio keep the original data, it causes a collision with the ROAD (check scenario_test_fixed.xml)
    # # NOTE: Let's try to "merget" the lanelets instead, like done in the STRETCH paper
    # replace_lanelet_network_in_scenario(temp_scenario,
    #     extend_the_incoming_lanelets_with_a_straight(temp_scenario.lanelet_network,
    #                                                  extension_distance=config.warmup_length, 
    #                                                  fuse_lanelets=False,
    #                                                  keep_original_adj=False))

    # XMLFileWriter(scenario, _planning_problem_set).write_to_file("generated_scenario.xml", overwrite_existing_file=OverwriteExistingFile.ALWAYS)

    # Now we have a default place "outside" the zone of interested where we can spawn the vehicles, we call them incoming lanelets
    # Compute all the feasible (minimum) paths from the incoming lanelets to the goal areas.
    # Rank them by the number of lane changes, i.e., the cost assuming each step costs 1
    
    G=nx.Graph()
    # Add one node for each lanelet
    for lanelet_id in [l.lanelet_id for l in scenario.lanelet_network.lanelets]:
        G.add_node(lanelet_id)
    # Add the edges in successor, left with same orientation, rigth with same orientation
    for lanelet in scenario.lanelet_network.lanelets:
        lanelet_id = lanelet.lanelet_id
        for successor_lanelet_id in lanelet.successor:
            G.add_edge(lanelet_id, successor_lanelet_id)
        
        if lanelet.adj_left and lanelet.adj_left_same_direction:
            G.add_edge(lanelet_id, lanelet.adj_left)
        
        if lanelet.adj_right and lanelet.adj_right_same_direction:
            G.add_edge(lanelet_id, lanelet.adj_right)

    # Compute feasible paths and compute a sensible initial speed based on the max curvature of the reference path
    feasible_paths = {}

    for incoming_lanelet_id in [l.lanelet_id for l in scenario.lanelet_network.lanelets if len(l.predecessor) == 0]:
        for outgoing_lanelet_id in [l.lanelet_id for l in scenario.lanelet_network.lanelets if len(l.successor) == 0]:
            
            path = nx.dijkstra_path(G, source=incoming_lanelet_id, target=outgoing_lanelet_id)
            
            # Analyze the path to count how many left/right changes are necessary
            lane_changes = 0

            for source_lanelet_id, target_lanelet_id in zip(path[:-1], path[1:]):
                source_lanelet = scenario.lanelet_network.find_lanelet_by_id(source_lanelet_id)
                if target_lanelet_id == source_lanelet.adj_left or target_lanelet_id == source_lanelet.adj_right:
                    lane_changes = lane_changes + 1
                else:
                    assert target_lanelet_id in source_lanelet.successor, f"Problem with path {target_lanelet_id} not a successor of {source_lanelet_id}"

            # We need only to store the incoming and outgoing lanet and the cost (min?)
            feasible_paths[(incoming_lanelet_id, outgoing_lanelet_id)] = lane_changes
    
    return feasible_paths


def get_random_init_state_on_lanelet_at_time_step(config: OmegaConf, lanelet: Lanelet, time_step: int) -> InitialState:
    """
    Return the Default Initial State of the Vehicle on the given lanelet.
    TODO: There is nothing random here... so probably better to change the name?
    """

    # Get the speed limit for the given type of lanelet or a default one
    lanelet_min_speed, lanelet_max_speed = speed_interval_for_lanelet(config, lanelet)
    
    # Set initial speed based on lanelet type at 90% of the limit
    initial_velocity = 0.9 * lanelet_max_speed

    # Set initial position
    initial_distance = config.initial_state.distance_from_beginning_m
    lanelet_length = lanelet.distance[-1]

    # Get the coordinates on the center vertices at the initial position
    position = lanelet.interpolate_position(initial_distance)[0]

    # Take another point on the center vertices to establish the road orientation
    if initial_distance + 1 < lanelet_length:
        next_point = lanelet.interpolate_position(initial_distance + 1)[0]
        orientation = get_orientation_by_coords(
            (position[0], position[1]), (next_point[0], next_point[1]))
    else:
        previous_point = lanelet.interpolate_position(initial_distance - 1)[0]
        orientation = get_orientation_by_coords(
            (previous_point[0], previous_point[1]), (position[0], position[1]))

    # Those are kept at zero at the beginning... We can alter them to simulate braking/accelerating and similar later
    acceleration = 0.0
    yaw_rate = 0.0
    slip_angle = 0.0
    
    # TODO time_step is necessary?
    return InitialState(time_step=time_step, 
                        position=position,
                        orientation=orientation, 
                        velocity=initial_velocity, 
                        acceleration=acceleration,
                        yaw_rate=yaw_rate,
                        slip_angle=slip_angle)

def generate_planning_problem_at_timestep(time_step: int, config: OmegaConf, initial_lanelet: Lanelet, goal_lanelet: Lanelet, goal_region, scenario: Scenario) -> PlanningProblem:
    """
    Use rejection randomly to select a feasible path (check whether it is a feasible compared to existing planning problems). Fails after 5 times
    """
    from itertools import cycle
    
    agent_id = scenario.generate_object_id()
    
    init_state = get_random_init_state_on_lanelet_at_time_step(config, initial_lanelet, time_step)
    
    the_goal_region = deepcopy(goal_region)
       
    # Make sure we set the correct speed on the goal region
    goal_min_speed_m_s, goal_max_speed_m_s = speed_interval_for_lanelet(config, goal_lanelet)
    # Make sure that the end time of the goal region is reflected by the initial time of the agent
    # default_goal_time = 
    default_goal_time_start = the_goal_region.state_list[0].time_step.start
    default_goal_time_end = the_goal_region.state_list[0].time_step.end
    # Shift the time by offset
    offset = time_step - default_goal_time_start
    updated_goal_time_start, updated_goal_time_end = default_goal_time_start + offset, default_goal_time_end + offset
    # the_goal_region.state_list[0].time_step
    the_goal_region.state_list[0].time_step = Interval(updated_goal_time_start, updated_goal_time_end)
    the_goal_region.state_list[0].velocity = Interval(goal_min_speed_m_s, goal_max_speed_m_s)

    # Create the Planning Problem
    new_planning_problem = PlanningProblem(agent_id, init_state, the_goal_region)

    return new_planning_problem

# Deprecated
def generate_planning_problem_at_timestep_with_warmup_and_teardow_zones(time_step: int, config: OmegaConf, goal_regions: dict, feasible_paths: dict, scenario: Scenario, agent_id: int, planning_problem_set: PlanningProblemSet) -> PlanningProblem:
    """
    Use rejection randomly to select a feasible path (check whether it is a feasible compared to existing planning problems). Fails after 5 times
    """
    from itertools import cycle

    # Shuffle the lanets once and iterate over them
    shuffled_list = list(feasible_paths.keys())
    random.shuffle(shuffled_list)

    for _, (warmup_lanelet_id, goal_lanelet_id) in zip(range(0, config.max_generation_retry), cycle(shuffled_list)):       
        warmup_lanelet = scenario.lanelet_network.find_lanelet_by_id(warmup_lanelet_id)
        goal_lanelet = scenario.lanelet_network.find_lanelet_by_id(goal_lanelet_id)

        init_state = get_random_init_state_on_lanelet_at_time_step(config, warmup_lanelet, time_step)
        # TODO: Shall we adjust the interval in the speed? like random sampling of speed?
        goal_region = deepcopy(goal_regions[goal_lanelet_id])
        
        # Make sure we set the correct speed on the goal region
        goal_min_speed_m_s, goal_max_speed_m_s = speed_interval_for_lanelet(config, goal_lanelet)
        goal_region.state_list[0].velocity = Interval(goal_min_speed_m_s, goal_max_speed_m_s)

        # Create the Planning Problem
        new_planning_problem = PlanningProblem(agent_id, init_state, goal_region)

        if validate_planning_problem(agent_id, config, new_planning_problem, planning_problem_set, scenario):
            print(f"Agent {agent_id} start from lanelet {warmup_lanelet_id} ({warmup_lanelet.lanelet_type}) at time {time_step} and speed {round(init_state.velocity * 3.6, 2)}")
            return new_planning_problem
    
    raise RuntimeError(f"Cannot generate a problem for {agent_id} at {time_step}!")

# TODO Move to utils.py or validation? or utilities.validation.py?
def validate_planning_problem(agent_id: int, config: OmegaConf, planning_problem: PlanningProblem, planning_problem_set: PlanningProblemSet, scenario: Scenario) -> bool:
    # TODO: Ideally to validate this we should be able to predict the position of all the other vehicles!
    ego_time_step = planning_problem.initial_state.time_step
    ego_initial_position = planning_problem.initial_state.position
    ego_initial_lanelets_set = set(flatten(scenario.lanelet_network.find_lanelet_by_position([ego_initial_position])))

    # Check if there are cars overlapping in the same lanelet as the planning problem with the same time_step
    for pp in [pp for pp in planning_problem_set.planning_problem_dict.values() if ego_time_step - 10 <= pp.initial_state.time_step <= ego_time_step + 10]:
        initial_position = pp.initial_state.position
        initial_lanelets_set = set(flatten(scenario.lanelet_network.find_lanelet_by_position([initial_position])))
        
        same_lanelets = len(ego_initial_lanelets_set.intersection(initial_lanelets_set)) > 0
        too_close_to_each_other = Point(ego_initial_position).distance(Point(initial_position)) < config.min_initial_dist
        
        # if same_lanelets:
        #     print(f"Planner {agent_id} is on the same lanelet(s) of planner {pp.planning_problem_id}")

        # if too_close_to_each_other:
        #     print(f"Planner {agent_id} is too close to planner {pp.planning_problem_id}")

        if same_lanelets and too_close_to_each_other:
            # print(f"* Planner {agent_id} is INVALID")
            return False

    # After checking them ALL, we can say it is valid
    return True
    
# Scenario Generation: Planning Problem: Initial State
def get_random_init_state_on_lanelet_at_time_step_with_warmup_and_teardown_zones(config: OmegaConf, lanelet: Lanelet, time_step: int) -> InitialState:
        """
        Return the Initial State of the Vehicle on the given lanelet.
        """

        lanelet_min_speed, lanelet_max_speed = speed_interval_for_lanelet(config, lanelet)
        
        # Sample the initial speed based on lanelet type
        velocity = random.uniform(lanelet_min_speed, lanelet_max_speed)

        # Sample the initial position inside the lanelet
        # lanelet.distance is the cumulative distance at each center point
        lanelet_length = lanelet.distance[-1]
        max_d = min(lanelet_length, config.warmup_length - config.length)
        min_d = min(lanelet_length, config.length)

        initial_distance = random.uniform(min_d, max_d)

        # Get the coordinates on the center vertices that
        position = lanelet.interpolate_position(initial_distance)[0]

        # Take another point to establish direction, pay attention to their order!
        if initial_distance + 1 < max_d:
            next_point = lanelet.interpolate_position(initial_distance + 1)[0]
            orientation = get_orientation_by_coords(
                (position[0], position[1]), (next_point[0], next_point[1]))
        else:
            previous_point = lanelet.interpolate_position(initial_distance - 1)[0]
            orientation = get_orientation_by_coords(
                (previous_point[0], previous_point[1]), (position[0], position[1]))

        # Those are kept at zero at the beginning... We can alter them to simulate braking/accelerating and similar later
        acceleration = 0.0
        yaw_rate = 0.0
        slip_angle = 0.0
        
        # TODO time_step is necessary?
        return InitialState(time_step=time_step, 
                            position=position,
                            orientation=orientation, 
                            velocity=velocity, 
                            acceleration=acceleration,
                            yaw_rate=yaw_rate,
                            slip_angle=slip_angle)