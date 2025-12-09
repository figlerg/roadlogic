__author__ = "Alessio Gambi"
__copyright__ = "Austrian Institute of Technology"
__credits__ = ["DSS/DSE"]
__version__ = "0.0.1"
__maintainer__ = "Alessio Gambi"
__email__ = "alesio.gambi@ait.ac.at"
__status__ = "beta"

import math
import matplotlib.pyplot as plt
import time
import logging

import numpy as np

from matplotlib import patches as mpatches
from typing import Union, Set, List
from functools import partial
from shapely.geometry import LineString, Point

import commonroad_crime.utility.visualization as utils_vis
import commonroad_crime.utility.logger as utils_log
from commonroad_crime.data_structure.base import CriMeBase
from commonroad_crime.data_structure.configuration import CriMeConfiguration
from commonroad_crime.utility.visualization import TUMcolor
from commonroad.geometry.shape import ShapeGroup
from commonroad.scenario.obstacle import Obstacle
from commonroad.scenario.scenario import Scenario, Lanelet

from commonroad_extensions.common.utils import get_orientation_by_coords

logger = logging.getLogger(__name__)

# Extend the existing set of Criticality Metrics
from enum import Enum

# Those are the metrics we call Context
class TypeScenario(str, Enum):
    DFLLB = "distance_to_left_lane_border"
    DFRLB = "distance_to_right_lane_border"
    DFLRB = "distance_to_left_road_border"
    DFRRB = "distance_to_right_road_border"
    CW5M  = "vehicles_within_5_m"
    CW10M = "vehicles_within_10_m"
    CW20M = "vehicles_within_20_m"
    VH    = "vehicle_heading"


class TypeVehicleState(str, Enum):
    CURRSA = "steering_angle"
    CURRV  = "velocity"
    CURRO  = "orientation"
    CURRA  = "acceleration"
    CURRYR = "yaw_rate"
    LANE = "lane"
    LONGPOS = "longitudinal_position"


# percentage_feasible_traj;
# infeasible_sum;
# inf_kin_acceleration;
# inf_kin_negative_s_velocity;
# inf_kin_max_s_idx;
# inf_kin_negative_v_velocity;
# inf_kin_max_curvature;
# inf_kin_yaw_rate;
# inf_kin_max_curvature_rate;
# inf_kin_vehicle_acc;
# inf_cartesian_transform;
# inf_precision_error
# TODO Why it is not there inf for collisions?
# Those one are generally extracted from the logs.csv files
class TypePlanner(str, Enum):
    CALCT = "calculation_time_s" # "time to compute a trajectory (aka calculation time)"
    PERCF = "percentage_feasible_traj" # percentage of feasible trajectories"
    INFTRAJSUM = "infeasible_sum" # count of infeasible (but not invalid) trajectories


class CustomizedCriMeBase(CriMeBase):
    """
    This is exactly the same as CriMeBase but ensure we invoke them correctly (e.g., without the need for additional veh_id)
    """
    def compute_criticality(
        self, time_step: int, vehicle_id: Union[int, None] = None, verbose: bool = True
    ):
        """
        Wrapper for computing the criticality, i.e., the value of the measure.
        """
        if self.ego_vehicle.state_at_time(time_step) is None:
            utils_log.print_and_log_warning(
                logger,
                f"* The ego vehicle doesn't have state at time step {time_step}",
            )
            return np.nan

        utils_log.print_and_log_info(
            logger, "*********************************", verbose
        )

        self.time_step = time_step

        if vehicle_id:
            other_veh_ids = [vehicle_id]
        else:
            other_veh_ids = [
                veh.obstacle_id
                for veh in self.sce.obstacles
                if veh.obstacle_id is not self.ego_vehicle.obstacle_id
                and veh.state_at_time(self.time_step) is not None
            ]

        time_start = time.time()

        # This is the patch!        
        # TODO For the moment all the CustomizedMetrics are computed considering only the ego_vehicle
        criti = self.compute(time_step=time_step, vehicle_id=None, verbose=verbose)

        time_computation = time.time() - time_start
        utils_log.print_and_log_info(
            logger, f"*\t\t {self.measure_name} of the scenario: {criti}", verbose
        )
        utils_log.print_and_log_info(
            logger, f"\tTook: \t{time_computation:.3f}s", verbose
        )
        return criti


class VehicleMeBase(CustomizedCriMeBase):

    def __init__(self, config, commonroad_state_attribute_name: str, metric_unit: str):
        super().__init__(config)
        self.commonroad_state_attribute_name = commonroad_state_attribute_name
        self.metric_unit = metric_unit

    def compute(self, time_step, vehicle_id, verbose):
        if not self.validate_update_states_log(vehicle_id, time_step, verbose):
            return np.nan
        
        # Get the state of the vehilce at the given time
        state = self.ego_vehicle.state_at_time(time_step)
        self.value = np.nan if self.commonroad_state_attribute_name not in state.attributes else getattr(state, self.commonroad_state_attribute_name)
        
        utils_log.print_and_log_info(
            logger, f"*\t\t {self.measure_name} = {self.value}", verbose
        )
        return self.value
    
    def visualize(self, figsize: tuple = (25, 15)):
        # Visualize the state metric as Text label beside the vehicle

        if self.configuration.debug.plot_limits:
            plot_limits = self.configuration.debug.plot_limits
        else:
            plot_limits = utils_vis.plot_limits_from_state_list(
                self.time_step,
                self.ego_vehicle.prediction.trajectory.state_list,
                margin=10,
            )

        self._initialize_vis(figsize=figsize, plot_limit=plot_limits)
        self.rnd.render()
        
        # Highlight the ego vehicle
        utils_vis.draw_dyn_vehicle_shape(
            self.rnd, self.ego_vehicle, self.time_step, color=TUMcolor.TUMred
        )

        state = self.ego_vehicle.state_at_time(self.time_step)
        x = state.position[0] + 5
        y = state.position[1]
        s = f"{self.measure_name} = {self.value}"
        plt.text(x, y, s, bbox=dict(facecolor='red', alpha=0.5))

        plt.title(f"{self.measure_name} of {self.value} {self.metric_unit}")
        if self.configuration.debug.draw_visualization:
            if self.configuration.debug.save_plots:
                utils_vis.save_fig(
                    self.measure_name,
                    self.configuration.general.path_output,
                    self.time_step,
                )
            else:
                plt.show()


class CURRSA(VehicleMeBase):

    measure_name = TypeVehicleState.CURRSA

    def __init__(self, config):
        super().__init__(config, commonroad_state_attribute_name="steering_angle", metric_unit = "rad")


class CURRV(VehicleMeBase):

    measure_name = TypeVehicleState.CURRV

    def __init__(self, config):
        super().__init__(config, commonroad_state_attribute_name="velocity", metric_unit = "mps")


class CURRO(VehicleMeBase):

    measure_name = TypeVehicleState.CURRO

    def __init__(self, config):
        super().__init__(config, commonroad_state_attribute_name="orientation", metric_unit = "rad")


class CURRA(VehicleMeBase):

    measure_name = TypeVehicleState.CURRA

    def __init__(self, config):
        super().__init__(config, commonroad_state_attribute_name="acceleration", metric_unit = "mps2")


class CURRYR(VehicleMeBase):

    measure_name = TypeVehicleState.CURRYR

    def __init__(self, config):
        super().__init__(config, commonroad_state_attribute_name="yaw_rate", metric_unit = "radps")


class DistanceToBorderMeBase(CustomizedCriMeBase):
   
    def __init__(self, config: CriMeConfiguration, is_left: bool, is_road: bool):
        super(DistanceToBorderMeBase, self).__init__(config)
        self.is_left = is_left
        self.is_road = is_road
    
    def compute(self, vehicle_id: int = None, time_step: int = 0, verbose: bool = True):
        if not self.validate_update_states_log(vehicle_id, time_step, verbose):
            return np.nan
        
        # Get the state of the vehilce at the given time
        state = self.ego_vehicle.state_at_time(time_step)
        
        # Get all the lanelets on which the vehicle is located, approximate the size of the road segment 
        # using the adjacency info

        max_distance_from_the_border = -math.inf
        self.reference_line = None
        for lanelet_id in self.sce.lanelet_network.find_lanelet_by_position([self.ego_vehicle.state_at_time(time_step).position])[0]:
            lanelet = self.sce.lanelet_network.find_lanelet_by_id(lanelet_id)

            # If we need to compute distand to Road border we need to identify the 
            # left-most/right-most border of the left-most/right-most lanelets
            # Otherwise, we use the left-most/right-most border of the current lanelet
            if self.is_road:
                # Find the ,i.e., the left/right border of the left/right most
                # lane on the same road with the same direction
                if self.is_left:
                    while lanelet.adj_left is not None and lanelet.adj_left_same_direction:
                        lanelet = self.sce.lanelet_network.find_lanelet_by_id(lanelet.adj_left)
                else:
                    while lanelet.adj_right is not None and lanelet.adj_right_same_direction:
                        lanelet = self.sce.lanelet_network.find_lanelet_by_id(lanelet.adj_right)

            # Get the border of the left-/right-most lanelet and compute the distance from the current position of the vehicle
            the_lane_border = LineString(lanelet.left_vertices) if self.is_left else LineString(lanelet.right_vertices) 
            distance_from_left_border = the_lane_border.distance(Point(state.position))
            # We take the max distance because if the vehicle is on multiple lanelets (fork/merge) we need to compare distance from
            # each road boundary and take the max. This is the same as the DistanceToLaneBorder
            if max_distance_from_the_border < distance_from_left_border:
                max_distance_from_the_border = distance_from_left_border
                self.reference_line = the_lane_border
            
        # Compute the distance to the lane border
        self.value = max_distance_from_the_border

        utils_log.print_and_log_info(
            logger, f"*\t\t {self.measure_name} = {self.value}", verbose
        )
        return self.value
    
    def visualize(self, figsize: tuple = (25, 15)):
        # Collect the info to visualize
        state = self.ego_vehicle.state_at_time(self.time_step)
        vehicle_position = Point(state.position)
        touching_point = self.reference_line.interpolate(self.reference_line.project(vehicle_position))
        segment = LineString([vehicle_position, touching_point])

        # Set the limits to entire show the segment with some margin
        if self.configuration.debug.plot_limits:
            plot_limits = self.configuration.debug.plot_limits
        else:
            margin=20
            np_limits = np.array([[vehicle_position.x, vehicle_position.y], [touching_point.x, touching_point.y]])
            plot_limits = [
                np.min(np_limits[0, :]) - margin, np.max(np_limits[0, :]) + margin, 
                np.min(np_limits[1, :]) - margin, np.max(np_limits[1, :]) + margin
            ]

        self._initialize_vis(figsize=figsize, plot_limit=plot_limits)
        self.rnd.render()
        
        # Highlight the ego vehicle
        utils_vis.draw_dyn_vehicle_shape(
            self.rnd, self.ego_vehicle, self.time_step, color=TUMcolor.TUMred
        )
        # # Draw where is the point
        # utils_vis.draw_circle(
        #     rnd=self.rnd,
        #     center = np.array([touching_point.x, touching_point.y]),
        #     radius = 0.05,
        #     opacity = 0.5,
        #     color=TUMcolor.TUMblack
        # )
        
        # Draw the segment highlighting the distance
        plt.plot(*segment.xy, "-", color=TUMcolor.TUMblack, alpha=0.2, lw=20, zorder=100)
        plt.plot(*segment.xy, "-", color=TUMcolor.TUMblack, lw=4, zorder=100)

        plt.title(f"{self.measure_name} of {self.value} m")
        if self.configuration.debug.draw_visualization:
            if self.configuration.debug.save_plots:
                utils_vis.save_fig(
                    self.measure_name,
                    self.configuration.general.path_output,
                    self.time_step,
                )
            else:
                plt.show()


class DFRLB(DistanceToBorderMeBase):
    """
    Max distance from any right border of the lanelet(s) in meter
    """

    measure_name = TypeScenario.DFRLB

    def __init__(self, config):
        super().__init__(config, is_left=False, is_road=False)


class DFLLB(DistanceToBorderMeBase):
    """
    Max distance from any left border of the lanelet(s) in meter
    """

    measure_name = TypeScenario.DFLLB

    def __init__(self, config):
        super().__init__(config, is_left=True, is_road=False)

    
class DFLRB(DistanceToBorderMeBase):
    """
    Max distance from any right border of the lanelet(s) in meter
    """

    measure_name = TypeScenario.DFLRB

    def __init__(self, config):
        super().__init__(config, is_left=True, is_road=True)


class DFRRB(DistanceToBorderMeBase):
    """
    Max distance from any left border of the lanelet(s) in meter
    """

    measure_name = TypeScenario.DFRRB

    def __init__(self, config):
        super().__init__(config, is_left=False, is_road=True)


def reacheable_set(scenario: Scenario, time_step: int, vehicle: Obstacle) -> Set[int]:
    """
    Return the set of lanelet id reacheable from the vehicle at time_step
    """  
    reacheable_set_vehicle = set()

    if vehicle.state_at_time(time_step) is None:
        return reacheable_set_vehicle
    
    list_lanelet_of_vehicle = scenario.lanelet_network.find_lanelet_by_position([vehicle.state_at_time(time_step).position])[0]
    
    # Sometimes the vehicle falls into narrow gaps between lanelets...
    if len(list_lanelet_of_vehicle) == 0:
        list_lanelet_of_vehicle = scenario.lanelet_network.find_lanelet_by_shape(vehicle.occupancy_at_time(time_step).shape)

    job_list = list()
    job_list += list_lanelet_of_vehicle
    while len(job_list) > 0:
        current_lanelet_id = job_list.pop()
        current_lanelet = scenario.lanelet_network.find_lanelet_by_id(current_lanelet_id)
        # Add to the reacheable set the current lanelet
        reacheable_set_vehicle.add(current_lanelet_id)
        # Add to the job list the lanelets reacheable from current_lanelet unless those are already in the reacheable set
        for pred in [p for p in current_lanelet.predecessor if p not in reacheable_set_vehicle]:
            job_list.append(pred)
        for succ in [s for s in current_lanelet.successor if s not in reacheable_set_vehicle]:
            job_list.append(succ)
        if current_lanelet.adj_left is not None and current_lanelet.adj_left_same_direction and current_lanelet.adj_left not in reacheable_set_vehicle:
            job_list.append(current_lanelet.adj_left)
        if current_lanelet.adj_right is not None and current_lanelet.adj_right_same_direction and current_lanelet.adj_right not in reacheable_set_vehicle:
            job_list.append(current_lanelet.adj_right)
    
    return reacheable_set_vehicle

def is_vehicle_within_reach(reacheable_lanelets_id: Set[int], vehicle_lanelets: List[int]) -> bool:
    """
    Vehicles are relevant to each other if the can reach each other
    """
    return len(reacheable_lanelets_id.intersection(set(vehicle_lanelets))) > 0


class CountVehiclesWithinMetersMeBase(CustomizedCriMeBase):
    
    def __init__(self, config, observation_radius: float):
        super().__init__(config)
        self.observation_radius = observation_radius

    def compute(self, vehicle_id: int = None, time_step: int = 0, verbose: bool = True):
        if not self.validate_update_states_log(vehicle_id, time_step, verbose):
            return np.nan
        
        count_of_vehicles_nearby = 0

        # Contextualize the function
        # Precompute the set of lanelets reacheable by ego_vehicle position
        ego_reacheable_set_at_time_step = reacheable_set(self.sce, time_step, self.ego_vehicle)
        # Define the ego-vehicle specific function
        is_other_vehicle_relevant_to_ego = partial(is_vehicle_within_reach, ego_reacheable_set_at_time_step)

        state = self.ego_vehicle.state_at_time(time_step)
        ego_vehicle_position = Point(state.position)
        # ego_poly = self.ego_vehicle.occupancy_at_time(i).shape.shapely_object
        for other_vehicle in [o for o in self.sce.obstacles if o.obstacle_id != self.ego_vehicle.obstacle_id]:
            other_vehicle_state = other_vehicle.state_at_time(time_step)
            other_vehicle_occupancy = other_vehicle.occupancy_at_time(time_step)
            # If the vehicle was indeed there at that time
            if other_vehicle_occupancy is not None:
                other_shape = other_vehicle_occupancy.shape

                if isinstance(other_shape, ShapeGroup):
                    distance = min(
                        [
                            ego_vehicle_position.distance(shape_element.shapely_object)
                            for shape_element in other_shape.shapes
                        ]
                    )
                else:
                    other_poly = other_vehicle_occupancy.shape.shapely_object
                    distance = ego_vehicle_position.distance(other_poly)

                if distance <= self.observation_radius:
                    # Check if the other vehicle is on the same road segment (reacheable via successor, predecessor, adj left or right with same direction)
                    other_vehicle_lanelets = self.sce.lanelet_network.find_lanelet_by_position([other_vehicle_state.position])[0]
                    if is_other_vehicle_relevant_to_ego(other_vehicle_lanelets):
                        count_of_vehicles_nearby = count_of_vehicles_nearby + 1
        
        self.value = count_of_vehicles_nearby

        utils_log.print_and_log_info(
            logger, f"*\t\t {self.measure_name} = {self.value}", verbose
        )
        return self.value
    
    def visualize(self, figsize: tuple = (25, 15)):
        if self.configuration.debug.plot_limits:
            plot_limits = self.configuration.debug.plot_limits
        else:
            # Ensure the circle is visible
            margin = 10
            plot_limits = utils_vis.plot_limits_from_state_list(
                self.time_step,
                self.ego_vehicle.prediction.trajectory.state_list,
                margin=self.observation_radius + margin,
            )

        self._initialize_vis(figsize=figsize, plot_limit=plot_limits)
        self.rnd.render()
        
        # Highlight the ego vehicle
        utils_vis.draw_dyn_vehicle_shape(
            self.rnd, self.ego_vehicle, self.time_step, color=TUMcolor.TUMred
        )

        state = self.ego_vehicle.state_at_time(self.time_step)

        # Draw where is the point
        utils_vis.draw_circle(
            rnd=self.rnd,
            center = np.array(state.position),
            radius = self.observation_radius,
            opacity = 0.5,
            color=TUMcolor.TUMblack
        )

        plt.title(f"{self.measure_name} is {self.value}")
        if self.configuration.debug.draw_visualization:
            if self.configuration.debug.save_plots:
                utils_vis.save_fig(
                    self.measure_name,
                    self.configuration.general.path_output,
                    self.time_step,
                )
            else:
                plt.show()


class CW5M(CountVehiclesWithinMetersMeBase):

    measure_name = TypeScenario.CW5M

    def __init__(self, config):
        super().__init__(config, observation_radius=5.0)
    

class CW10M(CountVehiclesWithinMetersMeBase):

    measure_name = TypeScenario.CW10M

    def __init__(self, config):
        super().__init__(config, observation_radius=10.0)


class CW20M(CountVehiclesWithinMetersMeBase):

    measure_name = TypeScenario.CW20M

    def __init__(self, config):
        super().__init__(config, observation_radius=20.0)


def compute_rotation_at_position(lanelet: Lanelet, position: np.ndarray):
    """
    Identify the next/prev point on the lanlet given the current position
    """
    center_line = LineString(lanelet.center_vertices)
    center_line_as_list_of_points = [ Point(p) for p in center_line.coords]

    point_position = Point(position)
    # Find the point on the center_line corresponding to position
    distance_from_beginning = center_line.project(point_position)

    points_before = list()
    points_after = list()

    for point in center_line_as_list_of_points:
        if center_line.project(point) < distance_from_beginning:
            points_before.append(point)
        elif center_line.project(point) > distance_from_beginning:
            points_after.append(point)

        if len(points_after) > 0:
            break
    
    orientation_before = None
    if len(points_before) > 0:
        orientation_before = get_orientation_by_coords((points_before[-1].x, points_before[-1].y), (point_position.x, point_position.y))
    
    orientation_after = None
    if len(points_after) > 0:
        orientation_after = get_orientation_by_coords((point_position.x, point_position.y), (points_after[0].x, points_after[0].y))

    assert orientation_after is not None or orientation_before is not None, "Invalid lanelet!"

    if orientation_before is not None and orientation_after is not None:
        # Take the average
        return (orientation_after + orientation_before) * 0.5

    if orientation_before is not None and orientation_after is None:
        return orientation_before
    
    if orientation_before is None and orientation_after is not None:
        return orientation_after


class VH(CustomizedCriMeBase):

    measure_name = TypeScenario.VH

    def __init__(self, config):
        super().__init__(config)
        self.reference_lanelet: Lanelet = None

    def compute(self, time_step, vehicle_id, verbose):
        if not self.validate_update_states_log(vehicle_id, time_step, verbose):
            return np.nan
        
        # Get the current orientation of the vehicle
        state = self.ego_vehicle.state_at_time(time_step)
        ego_orientation = state.orientation

        # Get the estimated direction of the road in the current ego vehicle position
        min_lanelet_orientation = math.inf

        for lanelet in [ self.sce.lanelet_network.find_lanelet_by_id(l_id) for l_id in self.sce.lanelet_network.find_lanelet_by_position([state.position])[0]]:
            rotation = compute_rotation_at_position(lanelet, state.position)
            if rotation < min_lanelet_orientation:
                min_lanelet_orientation = rotation
                self.reference_lanelet = lanelet
                self.lanelet_orientation = rotation

        # Do we like negative angles?
        self.value = ego_orientation - min_lanelet_orientation

        utils_log.print_and_log_info(
            logger, f"*\t\t {self.measure_name} = {self.value}", verbose
        )
        
        return self.value

    def visualize(self, figsize: tuple = (25, 15)):
        # Highlight the ego, highlight the center line of the lanelet used as reference, highlight the orientation of the vehicle, 
        # draw an arc between them

        if self.configuration.debug.plot_limits:
            plot_limits = self.configuration.debug.plot_limits
        else:
            # Ensure the circle is visible
            margin = 30
            plot_limits = utils_vis.plot_limits_from_state_list(
                self.time_step,
                self.ego_vehicle.prediction.trajectory.state_list,
                margin=margin,
            )

        self._initialize_vis(figsize=figsize, plot_limit=plot_limits)
        self.rnd.render()
        
        # Highlight the ego vehicle
        utils_vis.draw_dyn_vehicle_shape(
            self.rnd, self.ego_vehicle, self.time_step, color=TUMcolor.TUMred
        )

        # Highlight the center line of the lanelet

        state = self.ego_vehicle.state_at_time(self.time_step)
        
        # Draw Lanelet
        arc_size = 10

        initial_point = state.position[0], state.position[1]
        lanelet_orientation_segment = [initial_point, [initial_point[0] + arc_size * math.cos(self.lanelet_orientation), initial_point[1] + arc_size * math.sin(self.lanelet_orientation)]]
        vehicle_orientation_segment = [initial_point, [initial_point[0] + arc_size * math.cos(state.orientation), initial_point[1] + arc_size * math.sin(state.orientation)]]
        
        plt.plot([lanelet_orientation_segment[0][0], lanelet_orientation_segment[1][0]],
                 [lanelet_orientation_segment[0][1], lanelet_orientation_segment[1][1]], "-", lw="4", zorder=100, color= TUMcolor.TUMblack)
        plt.plot([vehicle_orientation_segment[0][0], vehicle_orientation_segment[1][0]],
                 [vehicle_orientation_segment[0][1], vehicle_orientation_segment[1][1]], "-", lw="4", zorder=100, color= TUMcolor.TUMblack)

        
        if self.value < 0:
            inner_pac = mpatches.Arc(state.position, 2*arc_size, 2*arc_size, angle=math.degrees(state.orientation), theta1=0.0, theta2=-math.degrees(self.value), lw=10, zorder=100, color=TUMcolor.TUMgreen)
            outer_pac = mpatches.Arc(state.position, 2*arc_size, 2*arc_size, angle=math.degrees(self.lanelet_orientation), theta1=0.0, theta2=math.degrees(self.value), lw=4, alpha=0.5, zorder=100, color=TUMcolor.TUMred)
            plt.gca().add_patch(inner_pac)
            plt.gca().add_patch(outer_pac)
        else:
            inner_pac = mpatches.Arc(state.position, 2*arc_size, 2*arc_size, angle=math.degrees(self.lanelet_orientation), theta1=0.0, theta2=math.degrees(self.value), lw=10, zorder=100, color=TUMcolor.TUMgreen)
            outer_pac = mpatches.Arc(state.position, 2*arc_size, 2*arc_size, angle=math.degrees(state.orientation), theta1=0.0, theta2=-math.degrees(self.value), lw=4, alpha=0.5, zorder=100, color=TUMcolor.TUMred)
            plt.gca().add_patch(inner_pac)
            plt.gca().add_patch(outer_pac)

        plt.title(f"{self.measure_name} is {self.value}")
        if self.configuration.debug.draw_visualization:
            if self.configuration.debug.save_plots:
                utils_vis.save_fig(
                    self.measure_name,
                    self.configuration.general.path_output,
                    self.time_step,
                )
            else:
                plt.show()

import warnings

def find_leftmost_lanelet(sce):
    """
    Identifies the leftmost lanelet of a straight, uninterrupted road by traversing
    from any lanelet backwards and then laterally, using a geometric cross-product check
    to determine if left/right annotations are flipped.
    """
    any_lanelet = next(iter(sce.lanelet_network.lanelets))

    # Step 1: Follow predecessors backward
    while any_lanelet.predecessor:
        if len(any_lanelet.predecessor) > 1:
            warnings.warn(
                f"Lanelet {any_lanelet.lanelet_id} has multiple predecessors — possible merge. "
                f"This may violate assumptions for LANE metric."
            )
        any_lanelet = sce.lanelet_network.find_lanelet_by_id(any_lanelet.predecessor[0])

    # Step 2: Geometric sanity check to determine if left/right annotations are flipped
    should_flip = False
    v0, v1 = any_lanelet.center_vertices[:2]
    direction = np.array(v1) - np.array(v0)

    if any_lanelet.adj_left:
        neighbor = sce.lanelet_network.find_lanelet_by_id(any_lanelet.adj_left)
        neighbor_pt = np.array(neighbor.center_vertices[0])
        to_neighbor = neighbor_pt - np.array(v0)
        cross = direction[0] * to_neighbor[1] - direction[1] * to_neighbor[0]
        if cross < 0:
            should_flip = True
            warnings.warn("Detected flipped left/right orientation — adjusting anchor traversal.")
    elif any_lanelet.adj_right:
        neighbor = sce.lanelet_network.find_lanelet_by_id(any_lanelet.adj_right)
        neighbor_pt = np.array(neighbor.center_vertices[0])
        to_neighbor = neighbor_pt - np.array(v0)
        cross = direction[0] * to_neighbor[1] - direction[1] * to_neighbor[0]
        if cross > 0:
            should_flip = True
            warnings.warn("Detected flipped left/right orientation — adjusting anchor traversal.")

    # Step 3: Traverse across to geometric leftmost
    while True:
        next_adj = any_lanelet.adj_right if should_flip else any_lanelet.adj_left
        same_dir = any_lanelet.adj_right_same_direction if should_flip else any_lanelet.adj_left_same_direction
        if next_adj is None or not same_dir:
            break
        any_lanelet = sce.lanelet_network.find_lanelet_by_id(next_adj)

    return any_lanelet.lanelet_id, should_flip


class LANE(CustomizedCriMeBase):
    """
    LANE Metric:
    Computes the lateral lane index of the ego vehicle relative to the leftmost lanelet of a single, uninterrupted road.

    Assumptions:
    - The road is a straight sequence of connected lanelets (no forks, merges, or intersections).
    - Lanelets are adjacent laterally with correct 'adj_left/right' and 'same_direction' annotations.
    - Longitudinal segments are connected via single predecessor/successor relationships.
    - All vehicles share the same coordinate reference (leftmost lanelet is index 0).

    Why this got a bit more complicated:
    This got a little bit too complicated because I encountered maps where leftAdjacent/rightAdjacent were flipped
    or inconsistently annotated. To deal with that, we added a geometric check to detect flipped left/right annotations
    and correct the traversal logic accordingly.

    Warning:
    If any lanelet has multiple successors (road split), the behavior may be undefined or inconsistent.
    """

    measure_name = TypeVehicleState.LANE

    def __init__(self, config):
        super().__init__(config)
        self.anchor_lanelet_id = None
        self.lane_index_map = None
        self._should_flip = False

    def compute(self, time_step, vehicle_id, verbose):
        if not self.validate_update_states_log(vehicle_id, time_step, verbose):
            return np.nan

        if self.lane_index_map is None:
            self.anchor_lanelet_id, self._should_flip = find_leftmost_lanelet(self.sce)
            self.lane_index_map = self._compute_lane_index_map(self.anchor_lanelet_id)

        state = self.ego_vehicle.state_at_time(time_step)
        lanelet_ids = self.sce.lanelet_network.find_lanelet_by_position([state.position])[0]

        if not lanelet_ids:
            self.value = np.nan
        else:
            lanelet_id = lanelet_ids[0]  # assume no overlaps
            self.value = self.lane_index_map.get(lanelet_id, np.nan)

        return self.value

    def _compute_lane_index_map(self, anchor_lanelet_id):
        anchor = 1
        index_map = {anchor_lanelet_id: anchor}

        # Traverse right
        current_id = anchor_lanelet_id
        idx = anchor+1
        while True:
            lanelet = self.sce.lanelet_network.find_lanelet_by_id(current_id)
            next_adj = lanelet.adj_left if self._should_flip else lanelet.adj_right
            same_dir = lanelet.adj_left_same_direction if self._should_flip else lanelet.adj_right_same_direction
            if next_adj is None or not same_dir:
                break
            current_id = next_adj
            index_map[current_id] = idx
            idx += 1

        # Traverse left
        current_id = anchor_lanelet_id
        idx = anchor-1
        while True:
            lanelet = self.sce.lanelet_network.find_lanelet_by_id(current_id)
            next_adj = lanelet.adj_right if self._should_flip else lanelet.adj_left
            same_dir = lanelet.adj_right_same_direction if self._should_flip else lanelet.adj_left_same_direction
            if next_adj is None or not same_dir:
                break
            current_id = next_adj
            index_map[current_id] = idx
            idx -= 1

        return index_map

from cr_scenario_handler.utils.utils_coordinate_system import CoordinateSystem
from types import SimpleNamespace



class LONGPOS(CustomizedCriMeBase):
    measure_name = TypeVehicleState.LONGPOS

    def __init__(self, config: CriMeConfiguration):
        super().__init__(config)
        self._curvi_coord_system = None

    def compute(self, vehicle_id: int = None, time_step: int = 0, verbose: bool = True):
        if not self.validate_update_states_log(vehicle_id, time_step, verbose):
            return np.nan

        if self._curvi_coord_system is None:
            anchor_lanelet_id, _ = find_leftmost_lanelet(self.sce)
            lanelet = self.sce.lanelet_network.find_lanelet_by_id(anchor_lanelet_id)
            reference_line = lanelet.center_vertices
            anchor_point = reference_line[0]

            # Create dummy config_sim to avoid AttributeError
            config_sim = SimpleNamespace(
                visualization=SimpleNamespace(ref_path_debug=False)
            )
            self._curvi_coord_system = CoordinateSystem(reference=reference_line, config_sim=config_sim)

        pos = self.ego_vehicle.state_at_time(time_step).position
        s,_ = self._curvi_coord_system.convert_to_curvilinear_coords(*pos)

        # TODO was short on time, should be an input or part of a config somewhere
        from commonroad_extensions.plan_execution.map_plan import padding_distance_left  
        s-= padding_distance_left  # correct by the padding (ie ego starts at 0)
        
        return s


import glob
import pandas as pd

class AgentLogBasedMeBase(CustomizedCriMeBase):
    """
    All those metrics are extracted from the logs in the simulation folder and 
    not from the executed scenario file
    """
    def __init__(self, config, metric_name):
        super().__init__(config)
        self.metric_name = metric_name
        self.simulation_folder = config.general.simulation_folder
        # Currently we do not merge the logs, so they must be found inside the tranches folder(s)
        # find tranches/ -iname logs.csv -ipath "*tranches/*/logs/1012*"

    def _lookup_in_logs_csv_files_metric_for_ego_vehicle(self, time_step):
        # TODO What is the simulation_folder here? The entire folder containing the tranches or the one contating the log file?
        logs_csv_files = sorted(glob.glob(f"{self.simulation_folder}/tranches/**/logs/{self.ego_vehicle.obstacle_id}/logs.csv", recursive=True))
        for logs_csv_file in logs_csv_files:
            # Read the file and check if the time_step and metric_name are there!
            df = pd.read_csv(logs_csv_file, sep=";", usecols=["trajectory_number", self.metric_name])
            # Ask for forgiveness
            try:
                return df[ df["trajectory_number"] == time_step][self.metric_name].values[0]
            except:
                pass

        # In case there's no such a metric/time_step return a default missing value
        # TODO Should be None instead?
        return np.nan

    def compute(self, time_step, vehicle_id, verbose):
        if not self.validate_update_states_log(vehicle_id, time_step, verbose):
            return np.nan
        
        # Get the current id of the ego vehicle and look up the logs.csv files in its folders
        # TODO Proably we could read once instead of everytime since this is an Instance of a class?!
        self.value = self._lookup_in_logs_csv_files_metric_for_ego_vehicle(time_step)

        utils_log.print_and_log_info(
            logger, f"*\t\t {self.measure_name} = {self.value}", verbose
        )
        
        return self.value


class CALCT(AgentLogBasedMeBase):
    
    measure_name = TypePlanner.CALCT

    def __init__(self, config):
        super().__init__(config, metric_name="calculation_time_s")

    
class PERCF(AgentLogBasedMeBase):
    
    measure_name = TypePlanner.PERCF

    def __init__(self, config):
        super().__init__(config, metric_name="percentage_feasible_traj")


class INFTRAJSUM(AgentLogBasedMeBase):
    
    measure_name = TypePlanner.INFTRAJSUM

    def __init__(self, config):
        super().__init__(config, metric_name="infeasible_sum")

# percentage_feasible_traj