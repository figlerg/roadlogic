# NOTE: Copy of Evita's Scenario Executor
from typing import Tuple, List, Dict, Any, Optional

# import csv
import os
import sys
import pickle

from glob import glob

import traceback

import enlighten

from copy import deepcopy

from datetime import datetime

from omegaconf import OmegaConf

# Assumes Frenetix is on the PYTHON Path. Added during the setup
from cr_scenario_handler.simulation.simulation import Simulation
from cr_scenario_handler.utils.configuration_builder import ConfigurationBuilder
from cr_scenario_handler.simulation.agent import AgentStatus, Agent

from commonroad.visualization.mp_renderer import MPRenderer
from commonroad.common.file_writer import CommonRoadFileWriter, XMLFileWriter
from commonroad.common.file_reader import CommonRoadFileReader, XMLFileReader
from commonroad.scenario.scenario import Scenario
from commonroad.planning.planning_problem import PlanningProblem, PlanningProblemSet
from commonroad.prediction.prediction import Trajectory, TrajectoryPrediction

from commonroad_extensions.common.utils import (
    merge_scenarios,
    override_configuration,
    store_scenario_and_planning_problems_to_output_folder,
    store_executed_scenario_to_output_folder
    )



# get n unique colors
def _get_cmap(n, name='hsv'):
    import matplotlib.pyplot as plt
    """Returns a function that maps each index in 0, 1, ..., n-1 to a distinct
    RGB color; the keyword argument name must be a standard mpl colormap name."""
    return plt.cm.get_cmap(name, n)


##################################################################################################################################################################
# UTILITY METHODS
##################################################################################################################################################################

def clip_executed_scenario(simulation: Simulation, inplace=True) -> Scenario|None:
    """
    This generates a modifies executed scenario!
    """
    
    if inplace:
        executed_scenario = simulation.scenario
    else:
        executed_scenario = deepcopy(simulation.scenario)
    
    # Clip the agent trajectory to its actual execution time
    # TODO For crashed vehicles we should replicate the last state until scenario max duration
    for agent in simulation.agents:
        obs = executed_scenario.obstacle_by_id(agent.id)
        shape = obs.obstacle_shape
        initial_timestep = obs.prediction.trajectory.initial_time_step
        lanelet_assigned = obs.prediction.center_lanelet_assignment

        cutpoint = agent.agent_state.last_timestep
        if hasattr(simulation, "maximum_scenario_duration"):
            cutpoint = min(getattr(simulation, "maximum_scenario_duration"), cutpoint)
        # This one is broken
        # traj = obs.prediction.trajectory.states_in_time_interval(initial_timestep, cutpoint)
        traj = [s for s in obs.prediction.trajectory.state_list if s is not None and initial_timestep <= s.time_step <= cutpoint]
        
        obs.prediction = TrajectoryPrediction(
            Trajectory(initial_time_step=traj[0].time_step, state_list=traj), shape,
            center_lanelet_assignment=lanelet_assigned)
    
    if not inplace:
        return executed_scenario


class PatchedConfigurationBuilder(ConfigurationBuilder):
    # Try to fix in a clean way the issues with the current ConfigurationBuilder object

    @classmethod
    def build_configuration(cls, scenario_name: str, path_root: str = None,
                            dir_config="configurations", module="simulation"):
        """Builds configuration from default, scenario-specific, but NOT considering the commandline config!.

        Args:
            scenario_name (str): considered scenario
            path_root (str): root path of the package
            dir_config (str): folder of configs
            module (str): module name of config

        """
        if path_root is None:
            path_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "../../"))

        cls.set_paths(path_root=path_root, dir_config=dir_config, dir_config_default=module)

        config_default = cls.construct_configuration(scenario_name)
        # config_cli = OmegaConf.from_cli()
        # configurations coming after overrides the ones coming before
        # config_merged = OmegaConf.merge(config_default, config_cli)
        # return config_merged
        return config_default

####################################################################################################
# TODO Move this somewhere else
####################################################################################################

import os
from typing import List, Union, Dict
from PIL import Image

import matplotlib
from matplotlib import pyplot as plt
import imageio.v3 as iio
import numpy as np
import matplotlib.cm as cm
import matplotlib.colors as colors
from commonroad.scenario.obstacle import DynamicObstacle, ObstacleType
from commonroad.scenario.state import State, CustomState
from commonroad.planning.planning_problem import PlanningProblem
from cr_scenario_handler.utils.agent_status import AgentStatus
# commonroad_dc
from commonroad_dc import pycrcc

from commonroad.scenario.scenario import Scenario
from commonroad.visualization.draw_params import MPDrawParams, DynamicObstacleParams, ShapeParams
from commonroad.visualization.mp_renderer import MPRenderer
from commonroad.geometry.shape import Rectangle

from cr_scenario_handler.utils.configuration import Configuration


from cr_scenario_handler.utils.visualization import colors_spec, darkcolors, lightcolors, green_to_red_colormap


def custom_visualize_multiagent_scenario_at_timestep(scenario: Scenario,
                                              agent_list: List,
                                              timestep: int,
                                              config: Configuration, log_path: str,
                                              orig_pp_id: List=None,
                                              predictions: dict = None,
                                              rnd: MPRenderer = None,
                                              plot_window: int = None,
                                              save: bool = False, show: bool = False, gif: bool = False,
                                              figsize: tuple[int, int] = (20,10),
                                              plot_format: str = "png"):
    """
    Extend the original code to force a specific size for figure and plot format.
    """

    # create renderer object (if no existing renderer is passed)
    if rnd is None:
        rnd = MPRenderer(figsize=figsize)

        if plot_window is not None:
            # focus on window around all agents AND obstacles
            left = np.inf
            right = - np.inf
            top = - np.inf
            bottom = np.inf
            for agent in agent_list:
                try:
                    ini_pos = agent.planning_problem.initial_state.position
                    if hasattr(agent.planning_problem.goal.state_list[0].position, "shapes"):
                        goal_pos = agent.planning_problem.goal.state_list[0].position.shapes[0].center
                    elif hasattr(agent.planning_problem.goal.state_list[0].position, "center"):
                        goal_pos = agent.planning_problem.goal.state_list[0].position.center
                    # else:
                    #     raise ValueError

                    left = min(left, goal_pos[0], ini_pos[0])
                    right = max(right, goal_pos[0], ini_pos[0])
                    top = max(top, goal_pos[1], ini_pos[1])
                    bottom = min(bottom, goal_pos[1], ini_pos[1])
                except AttributeError:
                    pass
            
            # Set the limits only if there are, otherwise, use the default
            if not (np.isinf(left) or np.isinf(bottom) or np.isinf(right) or np.isinf(top)):
                rnd.plot_limits = [-plot_window + left,
                               plot_window + right,
                               -plot_window + bottom,
                               plot_window + top]

    # Set obstacle parameters
    obs_params = MPDrawParams()
    obs_params.dynamic_obstacle.time_begin = timestep
    # Otherwise set to 200 as default!?
    obs_params.dynamic_obstacle.time_end = timestep + 100

    obs_params.dynamic_obstacle.draw_icon = config.visualization.draw_icons
    obs_params.dynamic_obstacle.show_label = config.visualization.show_labels
    obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.facecolor = "#E37222"
    obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.edgecolor = "#003359"

    obs_params.static_obstacle.show_label = config.visualization.show_labels
    obs_params.static_obstacle.occupancy.shape.facecolor = "#A30000"
    obs_params.static_obstacle.occupancy.shape.edgecolor = "#756F61"

    # visualize scenario
    scenario.draw(rnd, draw_params=obs_params)

    # Visualize agents and planning problems
    # for i in range(len(agent_list)):
    
    # Visualize RUNNING AGENTS
    for agent in [a for a in agent_list if a.status == AgentStatus.RUNNING]:
        # if agent.status != AgentStatus.RUNNING:
            # continue
        # set ego vehicle draw params
        ego_params = DynamicObstacleParams()
        ego_params.time_begin = timestep
        # Otherwise set to 200 as default!
        ego_params.time_end = timestep + 100

        ego_params.draw_icon = config.visualization.draw_icons
        ego_params.show_label = config.visualization.show_labels

        # Use standard colors for single-agent plots
        if len(agent_list) == 1:
            ego_params.vehicle_shape.occupancy.shape.facecolor = "#E37222"
            ego_params.vehicle_shape.occupancy.shape.edgecolor = "#9C4100"
        elif orig_pp_id:
            if agent.id in orig_pp_id:
                ego_params.vehicle_shape.occupancy.shape.facecolor = "#E37222"
                ego_params.vehicle_shape.occupancy.shape.edgecolor = "#9C4100"
            else:
                obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.facecolor = "#E37222"
                obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.edgecolor = "#003359"
        else:
            ego_params.vehicle_shape.occupancy.shape.facecolor = \
                colors_spec[agent.id % len(colors_spec)]
            ego_params.vehicle_shape.occupancy.shape.edgecolor = \
                darkcolors[agent.id % len(darkcolors)]
        ego_params.vehicle_shape.occupancy.shape.zorder = 50
        ego_params.vehicle_shape.occupancy.shape.opacity = 1

        # Visualize planning problem and agent
        # if multiple_agents:
        #     planning_problems.find_planning_problem_by_id(agent.obstacle_id).draw(rnd)
        # else:

        agent.vehicle_history[-1].draw(rnd, draw_params=ego_params)
        agent.planning_problem.draw(rnd)

    # Visualize COLLIDED AGENTS
    for agent in [a for a in agent_list if a.status == AgentStatus.COLLISION]:
        # set ego vehicle draw params
        ego_params = DynamicObstacleParams()
        ego_params.time_begin = timestep
        # Otherwise set to 200 as default
        ego_params.time_end = timestep + 100

        ego_params.draw_icon = config.visualization.draw_icons
        ego_params.show_label = config.visualization.show_labels

        # Use standard colors for single-agent plots
        if len(agent_list) == 1:
            ego_params.vehicle_shape.occupancy.shape.facecolor = "#E37222"
            ego_params.vehicle_shape.occupancy.shape.edgecolor = "#e6007e" # SHOW THEM IN RED
        elif orig_pp_id:
            if agent.id in orig_pp_id:
                ego_params.vehicle_shape.occupancy.shape.facecolor = "#E37222"
                ego_params.vehicle_shape.occupancy.shape.edgecolor = "#e6007e" # SHOW THEM IN RED
            else:
                obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.facecolor = "#E37222"
                obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.edgecolor = "#e6007e" # SHOW THEM IN RED
        else:
            ego_params.vehicle_shape.occupancy.shape.facecolor = colors_spec[agent.id % len(colors_spec)]
            ego_params.vehicle_shape.occupancy.shape.edgecolor = "#e6007e" # SHOW THEM IN RED
        
        ego_params.vehicle_shape.occupancy.shape.zorder = 51
        # Check if beneth there's another vehicle plotted... it should not be since we plot it looking at the status!
        ego_params.vehicle_shape.occupancy.shape.opacity = 0.2

        # Draw the current state
        # vehicle_history[-1] might not correspond to the latest one...
        agent.vehicle_history[-1].draw(rnd, draw_params=ego_params)
        # Should we draw also their planning problem?
        # agent.planning_problem.draw(rnd)
    
    rnd.render()
    
    # Add additional metadata for running agents
    for agent in [a for a in agent_list if a.status == AgentStatus.RUNNING]:
        # visualize optimal trajectory
        history = [i for i in agent.vehicle_history if i.initial_state.time_step == timestep]
        if history:
            history = history[0]

            if history.prediction is not None and config.visualization.draw_calc_traj:
                rnd.ax.plot([i.position[0] for i in history.prediction.trajectory.state_list],
                            [i.position[1] for i in history.prediction.trajectory.state_list],
                            color='k' , marker='x', markersize=1.5, zorder=21, linewidth=2.0, label='optimal trajectory')

        if agent.all_trajectories is not None and agent.config_planner.debug.draw_traj_set:
            valid_traj = [obj for obj in agent.all_trajectories if obj.valid is True and obj.feasible is True]
            invalid_traj = [obj for obj in agent.all_trajectories if obj.valid is False or obj.feasible is False]
            norm = matplotlib.colors.Normalize(
                vmin=0,
                vmax=len(valid_traj),
                clip=True,
            )
            mapper = cm.ScalarMappable(norm=norm, cmap=green_to_red_colormap())
            # step_inv = int(len(invalid_traj) / 50) if int(len(invalid_traj) / 50) > 2 else 1
            step_val = int(len(valid_traj)/50)  if int(len(valid_traj) / 50) > 2 else 1
            step_inv=step_val
            for idx in range(0, len(valid_traj), step_val):
                val = valid_traj[idx]
                if not val._coll_detected:
                    color = mapper.to_rgba(idx)
                    color = lightcolors[idx % len(lightcolors)]
                    plt.plot(val.cartesian.x, val.cartesian.y,
                             color=color, zorder=20, linewidth=1.0, alpha=1.0, picker=False)
                else:
                    plt.plot(val.cartesian.x, val.cartesian.y,
                             color='cyan', zorder=20, linewidth=1.0, alpha=0.8, picker=False)
            for ival in range(0, len(invalid_traj), step_inv):
                plt.plot(invalid_traj[ival].cartesian.x, invalid_traj[ival].cartesian.y,
                         color="#808080", zorder=19, linewidth=0.8, alpha=0.4, picker=False)

        if agent.reference_path is not None and config.visualization.draw_reference_path:

            rnd.ax.plot(agent.reference_path[:, 0], agent.reference_path[:, 1], color='g', marker='.', markersize=1, zorder=19, linewidth=0.8,
                        label='reference path')

    # visualize predictions
    if predictions is not None and config.visualization.draw_predictions:
        from wale_net_lite.visualization import draw_uncertain_predictions
        draw_uncertain_predictions(predictions, rnd.ax)
    
    # If linear prediction is used
    # if predictions is not None and config.visualization.draw_predicted_positions:
    #     obstacle_ids = list(predictions.keys())
    #     for obstacle_id in obstacle_ids:
    #         pred_traj = predictions[obstacle_id]['pos_list']
    #         x = [p[0] for p in pred_traj]
    #         y = [p[1] for p in pred_traj]
    #         rnd.ax.scatter(x, y, color="black", alpha=0.6, marker="o", s=10, zorder=100)

    if save or gif:
        plot_dir = os.path.join(log_path, "plots")
        os.makedirs(plot_dir, exist_ok=True)
        if gif:
            plt.axis('off')
            plt.savefig(f"{plot_dir}/{scenario.scenario_id}_{timestep}.{plot_format}", format=plot_format, bbox_inches='tight',
                        pad_inches=0)
        else:
            # plt.savefig(f"{plot_dir}/{scenario.scenario_id}_{timestep}.svg", format='svg') - dpi=300, 
            plt.savefig(f"{plot_dir}/{scenario.scenario_id}_{timestep}.{plot_format}", format=plot_format, bbox_inches='tight',
                        pad_inches=0)

    if show:
        matplotlib.use("TkAgg")
        plt.pause(0.0001)

####################################################################################################
#
####################################################################################################
from cr_scenario_handler.planner_interfaces.frenet_interface import FrenetPlannerInterface

class CustomFrenetPlannerInterface(FrenetPlannerInterface):
    
    def __init__(self, agent_id, config_planner, config_sim, scenario, planning_problem, log_path, mod_path,
                 precomputed_reference_path):

        self.config_plan = config_planner
        self.config_sim = config_sim
        self.scenario = scenario
        self.id = agent_id
        self.config_sim.simulation.ego_agent_id = agent_id
        self.DT = self.config_plan.planning.dt
        self.replanning_counter = 0
        self.replanning_traj = None
        self.behavior_module_state = None

        self.planning_problem = planning_problem
        self.log_path = log_path
        self.mod_path = mod_path

        # *************************************
        # Message Logger of Run
        # *************************************
        # self.msg_logger = logging.getLogger("Message_logger_" +str(self.id ))
        # Make the logger contextual to the tranche
        initial_time_step = planning_problem.initial_state.time_step
        self.msg_logger = lh.logger_initialization(self.config_plan, log_path, f"Message_logger_{self.id}_{initial_time_step}")

        self.msg_logger.critical("Start Custom Frenetic Planner for Agent ID: " + str(self.id))

        # Init and Goal State

        # Initialize planner
        self.planner = ReactivePlannerCpp(self.config_plan, self.config_sim, scenario, planning_problem, log_path, mod_path, self.msg_logger) \
            if self.config_plan.debug.use_cpp else \
              ReactivePlannerPython(self.config_plan, self.config_sim, scenario, planning_problem, log_path, mod_path, self.msg_logger)

        problem_init_state = planning_problem.initial_state

        if not hasattr(problem_init_state, 'acceleration'):
            problem_init_state.acceleration = 0.
        x_0 = deepcopy(problem_init_state)

        shape = Rectangle(self.planner.vehicle_params.length, self.planner.vehicle_params.width)
        ego_vehicle = DynamicObstacle(agent_id, ObstacleType.CAR, shape, x_0, None)
        self.planner.set_ego_vehicle_state(current_ego_vehicle=ego_vehicle)

        # Set initial state and curvilinear state
        self.x_0 = ReactivePlannerState.create_from_initial_state(
            deepcopy(planning_problem.initial_state),
            self.config_sim.vehicle.wheelbase,
            self.config_sim.vehicle.wb_rear_axle
        )
        self.planner.record_state_and_input(self.x_0)

        self.x_cl = None
        self.desired_velocity = None
        self.occlusion_module = None
        self.behavior_module = None
        self.route_planner = None

        # Set reference path
        if not self.config_sim.behavior.use_behavior_planner:

            if precomputed_reference_path is None:
                # Regular case
                self.route_planner = RoutePlanner(lanelet_network=scenario.lanelet_network,
                                                planning_problem=planning_problem,
                                                scenario=scenario,
                                                extended_search=False)
                shortest_route = self.route_planner.plan_routes().retrieve_shortest_route(retrieve_shortest=True)

                planned_reference_path = np.copy(shortest_route.reference_path)
                
                # The original code is broken. At the beginning of the lanelet, the points may be too close
                # so the extendion computes reference paths with size in the order of 1M unnecessarily blocking the execution
                def extend_path_linearly(points, extension_length=50, max_points=200, at_start=True):
                    """Extend the list of points linearly at the start or end by a given length."""
                    if at_start:
                        p1, p2 = points[0], points[1]
                    else:
                        p1, p2 = points[-2], points[-1]

                    delta_x = p2[0] - p1[0]
                    delta_y = p2[1] - p1[1]

                    dist = np.sqrt(delta_x ** 2 + delta_y ** 2)
                    if dist == 0:
                        return points  # Avoid division by zero if p1 and p2 are the same

                    step_x = delta_x / dist
                    step_y = delta_y / dist

                    num_new_points = min(int(extension_length / dist), max_points)

                    new_points = []
                    for i in range(1, num_new_points + 1):
                        if at_start:
                            new_point = (p1[0] - i * step_x * dist, p1[1] - i * step_y * dist)
                            new_points.append(new_point)
                        else:
                            new_point = (p2[0] + i * step_x * dist, p2[1] + i * step_y * dist)
                            new_points.append(new_point)

                    if at_start:
                        return np.vstack((new_points[::-1], points))
                    else:
                        return np.vstack((points, new_points))


                # reference_path = extend_ref_path_both_ends(planned_reference_path)
                #  """Extend the reference path on both ends by a default length."""
                extension_length=30
                reference_path = extend_path_linearly(planned_reference_path, extension_length, at_start=True)
                reference_path = extend_path_linearly(reference_path, extension_length, at_start=False)
                
                self.reference_path = smooth_ref_path(reference_path)
            else:
                self.msg_logger.critical(f"Forced precomputed reference path")
                self.reference_path = precomputed_reference_path

        else:
            raise NotImplementedError("Behavioral Planner is not supported ")

        self.goal_area = gc.get_goal_area_shape_group(planning_problem=planning_problem, scenario=scenario)

        # **************************
        # Set External Planner Setups
        # **************************
        self.planner.update_externals(x_0=self.x_0, reference_path=self.reference_path, goal_area=self.goal_area,
                                      occlusion_module=self.occlusion_module)
        self.x_cl = self.planner.x_cl

        # ***************************
        # Initialize Velocity Planner
        # ***************************
        # TODO Replace this hideous component!
        self.velocity_planner = VelocityPlanner(scenario=scenario, planning_problem=planning_problem,
                                                coordinate_system=self.coordinate_system)

####################################################################################################
#
####################################################################################################
from copy import deepcopy
import numpy as np
import logging
import inspect

from commonroad.geometry.shape import Rectangle
from commonroad.planning.planning_problem import PlanningProblem
from commonroad.scenario.obstacle import DynamicObstacle, ObstacleType
from commonroad.scenario.scenario import Scenario
from commonroad.scenario.state import InitialState

from commonroad_route_planner.route_planner import RoutePlanner

import cr_scenario_handler.utils.multiagent_logging as lh
import cr_scenario_handler.utils.goalcheck as gc
from cr_scenario_handler.evaluation.collision_report import coll_report
from cr_scenario_handler.planner_interfaces.planner_interface import PlannerInterface
from cr_scenario_handler.utils.utils_coordinate_system import smooth_ref_path, extend_ref_path_both_ends
from cr_scenario_handler.utils.velocity_planner import VelocityPlanner

from behavior_planner.behavior_module import BehaviorModule

from frenetix_motion_planner.reactive_planner import ReactivePlannerPython
from frenetix_motion_planner.reactive_planner_cpp import ReactivePlannerCpp
from frenetix_motion_planner.state import ReactivePlannerState

# scenario handler
import cr_scenario_handler.planner_interfaces as planner_interfaces
import cr_scenario_handler.utils.multiagent_helpers as hf
import cr_scenario_handler.utils.prediction_helpers as ph
import cr_scenario_handler.utils.visualization as visu
from cr_scenario_handler.planner_interfaces.planner_interface import PlannerInterface
from cr_scenario_handler.evaluation.collision_report import coll_report
from cr_scenario_handler.evaluation.agent_evaluation import evaluate
from cr_scenario_handler.utils.agent_status import AgentStatus, AgentState
from cr_scenario_handler.utils.visualization import visualize_agent_at_timestep


class ResumableAgent(Agent):
    
    def __init__(self, agent_id: int, planning_problem: PlanningProblem,
                 scenario: Scenario, config_planner, config_sim, msg_logger, log_path: str, mod_path: str,
                 precomputed_reference_path=None, precomputed_planner_interface_x_0=None, force_collided: bool = False):
        """
        Extend the base Agent by allowing us to force the precomputed_reference_path into the planner interface
        """

        # Agent id, equals the id of the dummy obstacle
        self.dt = scenario.dt
        self.id = agent_id

        self.msg_logger = msg_logger

        self.config = deepcopy(config_sim)
        self.config_simulation = self.config.simulation
        self.config_visu = self.config.visualization
        self.config_planner = deepcopy(config_planner)
        self.vehicle = config_sim.vehicle

        self.mod_path = mod_path
        self.log_path = os.path.join(config_sim.simulation.log_path, str(agent_id)) if (
                                     self.config_simulation.use_multiagent) else log_path

        self.save_plot = (self.id in self.config_visu.save_specific_individual_plots
                          or self.config_visu.save_all_individual_plots)
        self.gif = (self.config_visu.save_all_individual_gifs
                    or self.id in self.config_visu.save_specific_individual_gifs)
        self.show_plot = (self.id in self.config_visu.show_specific_individual_plots
                          or self.config_visu.show_all_individual_plots)

        # This is the expected agent lifetime, which is originally defined by that self.config_simulation.max_steps multiplier
        # try:
        #     self.max_time_steps_scenario = int(
        #         self.config_simulation.max_steps * planning_problem.goal.state_list[0].time_step.end)
        # except NameError:
        #     self.max_time_steps_scenario = 200
        # self.msg_logger.critical(f"Agent {self.id}: Max time steps {self.max_time_steps_scenario}")
        # Where is this used by the agent to decide if it missed the goal area, i.e., timeout
        multiplier = 1.0
        try:
            # note that we take the last goal this time!
            # self.config_simulation.max_steps is a multiplier not a value!
            multiplier = self.config_simulation.max_steps
        except NameError:
            pass
        except AttributeError:
            pass

        # Set the agent lifetime based on its goal and any defined multiplier
        self.max_time_steps_scenario = int(multiplier * planning_problem.goal.state_list[-1].time_step.end)
        self.msg_logger.critical(f"Agent {self.id}: Original Life Time: {self.max_time_steps_scenario}")

        # In case the duration of the simulation is capped, enforce that as well.
        # Note we take the MAX because the simulation will be stopped no matter what at max_duration
        max_duration = -1
        try:
            max_duration = self.config_simulation.max_duration
        except NameError:
            pass
        except AttributeError:
            pass

        self.max_time_steps_scenario = max(self.max_time_steps_scenario, max_duration)

        self.msg_logger.critical(f"Agent {self.id}: Adjusted Life Time: {self.max_time_steps_scenario}")


        self.planning_problem = planning_problem
        self.scenario = hf.scenario_without_obstacle_id(scenario=deepcopy(scenario), obs_ids=[self.id])
        initial_time_step = planning_problem.initial_state.time_step

        # Regular initial state setup create x_0 from the initial state
        problem_init_state = deepcopy(planning_problem.initial_state)
        if not hasattr(problem_init_state, 'acceleration'):
            problem_init_state.acceleration = 0.
        
        x_0 = deepcopy(problem_init_state)
        
        # TODO CR-Reach/Spot/ Occlusion / Sensor

        self.planning_times = list()

        self.predictions = None
        self.visible_area = None

        self.collision_objects = list()
        self._create_collision_object(x_0, initial_time_step)

        self._all_trajectories = None
        # Initialize Planner - Use our CUSTOM one!
        used_planner = self.config_simulation.used_planner_interface

        # THIS IS OUR PATCH
        if used_planner == CustomFrenetPlannerInterface.__name__:
            # This is the problematic call, since it needs to compute the reference path
            self.planner_interface = CustomFrenetPlannerInterface(self.id, self.config_planner, self.config, self.scenario,
                                                    self.planning_problem, self.log_path, self.mod_path, 
                                                    # Here's the additional parameter
                                                    precomputed_reference_path
                                                    )
        else:

            try:
                planner_interface = [cls for _, module in inspect.getmembers(planner_interfaces, inspect.ismodule)
                                    for name, cls in inspect.getmembers(module, inspect.isclass) if
                                    issubclass(cls, PlannerInterface)
                                    and name == used_planner][0]
            except:
                raise ModuleNotFoundError(f"No such planner class found in planner_interfaces: {used_planner}")
            
            # This is the problematic call, since it needs to compute the reference path
            self.planner_interface = planner_interface(self.id, self.config_planner, self.config, self.scenario,
                                                    self.planning_problem, self.log_path, self.mod_path)

        self.agent_state = AgentState(planning_problem=planning_problem, reference_path=self.reference_path,
                                      coordinate_system=self.coordinate_system)
        
        if planning_problem.initial_state.time_step == 0:
            self.agent_state.log_running(0)

        if precomputed_planner_interface_x_0 is not None:
            print(f"Forcing precomputed planner state {precomputed_planner_interface_x_0}")
            # ego_as_obstacle = scenario.obstacle_by_id(self.id)
            # # ego_current_state = ego_as_obstacle.state_at_time(time_step)
            # # This is buggy, it will not consider the actual time, but lookup on the index of the latest one
            # # state = self._state_list[time_step - self._initial_time_step]
            # # ego_as_obstacle.prediction.trajectory.state_at_time_step(time_step)
            # ego_current_state = next(iter([s for s in ego_as_obstacle.prediction.trajectory.state_list if s.time_step == time_step]))
            # ego_state_as_initial_state = ego_current_state.convert_state_to_state(InitialState())
            
            # # Set initial state and curvilinear state
            # # This one shift the position of the vehicle to the rear axle... but is it correct?
            # # NOTE: This one changes the object: ego_state_as_initial_state that's why we have a deepcopy
            # updated_x_0 = ReactivePlannerState.create_from_initial_state(
            #     deepcopy(ego_state_as_initial_state),
            #     self.vehicle.wheelbase,
            #     self.vehicle.wb_rear_axle
            # )

            # # This one ONLY changes the batched-agent, not the agent synchronized in simulation
            # # However, the agent will send the "updated" trajectory including the updated initial state
            # self.planner_interface.record_state_list[-1] = updated_x_0
            # Setting the x_cl to None will force planner to recompute it
            
            # NOTE: x_cl is the state actually used by the (CPP) planner to planning the trajectories!
            self.planner_interface.planner.x_cl = None

            # Update the new cartesian current state to match the one observed in the scenario
            self.planner_interface.planner.update_externals(x_0=precomputed_planner_interface_x_0)
            # Log the updated x_cl as well. We need both to update planner_interface internal state (BAD DESIGN!)
            updated_x_cl = self.planner_interface.planner.x_cl

            # This DOES NOT automatically happen after calling update_externals
            # So we need to force it. 
            self.planner_interface.x_0 = precomputed_planner_interface_x_0
            # The X_CL is used by the CPP planner to compute the trajectories, but calling planner.update_externals was not enough 
            self.planner_interface.x_cl = updated_x_cl

        #
        # Assume we do not start in a collision  TODO We cannot assume that!
        
        self.already_collided = force_collided
        

    def update_agent(self, scenario: Scenario, time_step: int, global_predictions: dict,
                     collision: bool = False, colliding_agents: list = []):
        """ 
        Extend the original code to enable collided agents to remain in the simulation after they collided.
        TODO This requires a deep redesign... IMHO
        """
        self.agent_state.log_running(time_step)

        if not collision:
            if self.config_simulation.use_multiagent:
                self.scenario = hf.scenario_without_obstacle_id(scenario=deepcopy(scenario), obs_ids=[self.id])
            if global_predictions:
                self.predictions, self.visible_area = ph.filter_global_predictions(self.scenario, global_predictions,
                                                                                   self.vehicle_history[-1],
                                                                                   time_step,
                                                                                   self.config,
                                                                                   occlusion_module=self.planner_interface.occlusion_module,
                                                                                   ego_id=self.id,
                                                                                   msg_logger=self.msg_logger)
            else:
                self.predictions, self.visible_area = None, None
        else:
            # This avoids inconsistency in collision reporting (see tests/data/flaky-collisions.xml)
            self.scenario = hf.scenario_without_obstacle_id(scenario=deepcopy(scenario), obs_ids=[self.id])
            
            if self.agent_state.status == AgentStatus.COLLISION:
                self.msg_logger.info(f"Agent {self.id} already collided at time_step {time_step}")    
                # This triggers one step after colliding
                self.already_collided = True
            else:
                self.msg_logger.info(f"Agent {self.id} collided at time_step {time_step}. Colliding agents {colliding_agents}")
                # Set the status of the agent to COLLISION and the last time step to the current one
                # But what's the status of the agent at this point?
                self.agent_state.log_collision(time_step)
                # TODO Is this really necessary?
                self.colliding_agents = colliding_agents

                
    def step_agent(self, timestep):
        """
        Execute one planning step unless the agent is collided. In this case, planning is the same as remaining in the current state (with v=0 and a=0)
        """
        #
        # Check for collisions in previous timestep - done only at collision time
        #
        if self.agent_state.status == AgentStatus.COLLISION and not self.already_collided:
            self.planning_times.append(0)
            # Report the collision ONLY if its a new collision
            if self.config.evaluation.collision_report and not self.already_collided:
                # TODO It does not report the collision of the second vehicle?
                # It does report the wrong value for the collision speed of the obstacle
                
                #Report the collisions in the run folder, not inside the the agent path!
                collision_folder = os.path.dirname(self.log_path)

                coll_report(self.vehicle_history, self.planner_interface.planner,
                            self.scenario, self.planning_problem,
                            self.agent_state.last_timestep,
                            self.config,
                            collision_folder)
                
            self.postprocessing()

            self.already_collided = True
        
        # Note this one. When the agent collides, it's current state is not computed, leaving an hole in the dataset that breaks the evaluation

        if timestep > self.max_time_steps_scenario and self.agent_state.status != AgentStatus.COLLISION:
            # Do not log a different requirement violation if already collided
            self.msg_logger.critical(f"Timestep {timestep} Agent {self.id} reached max_time_steps {self.max_time_steps_scenario}")
            self.planning_times.append(0)
            self.agent_state.log_timelimit(timestep)
            self.postprocessing()

        elif self.planner_interface.planner.x_cl[0][0] > self.agent_state.goal_checker.last_goal_position and self.agent_state.status != AgentStatus.COLLISION:
            # Do not log a different requirement violation if already collided
            self.msg_logger.critical(f"Timestep {timestep} Agent {self.id} when over the goal")
            self.agent_state.log_max_s_position(timestep)
            self.planning_times.append(0)
            self.postprocessing()
        
        else:
            # Otherwise, the planner is either running or init ?
            # check for completion of this agent - 
            collided = self.agent_state.status == AgentStatus.COLLISION
            # this changes the AgentStatus.RUNNING and overwrite the collision state
            self.agent_state.check_goal_reached(self.record_state_list, self.planner_interface.planner.x_cl)
            # Ensure collisions are preserved
            self.agent_state.status = AgentStatus.COLLISION if collided else self.agent_state.status

            if self.agent_state.status not in [AgentStatus.RUNNING, AgentStatus.COLLISION]:
                self.planning_times.append(0)
                self.agent_state.log_finished(timestep)
                self.postprocessing()
            
            else:
                self.msg_logger.debug(f"Agent {self.id} planning current time step {timestep}")

                comp_time_start = time.time()

                if self.agent_state.status == AgentStatus.COLLISION and self.already_collided:
                    self.msg_logger.debug(f"Agent {self.id}: Already crashed at current time step: {timestep}. Computing its collided trajectory")
                    
                    # Replan the agent trajectory such that it stays still 

                    # state_list : List[TraceState]
                    initial_time_step = timestep
                    # Take the latest state and replicate
                    
                    # TODO There might be an hole corresponding to the timestep of the collision...

                    # Check that is the same timestemp! record_state_list[-1] == timestep -1 !
                    # assert timestep - 1 == self.record_state_list[-1].time_step, f"timestep {timestep} but last recorded state {self.record_state_list[-1]}"
                    current_state = deepcopy(self.record_state_list[-1])
                    state_list = list()
                    for i in range(int(self.config_planner.planning.planning_horizon / self.config_planner.planning.dt) + 1):
                        current_state = deepcopy(self.record_state_list[-1])
                        # From the initial time count the necessasry steps to build the trajectory
                        # Will this also update the computed_trajectory and the rest?
                        current_state.time_step = initial_time_step + i
                        current_state.velocity = 0.0
                        current_state.acceleration = 0.0
                        current_state.yaw_rate = 0.0

                        state_list.append(current_state)

                    trajectory =  Trajectory(initial_time_step, state_list)
                    replanning_counter = 0

                    # Force the planner_interface state as it would do with step_interface
                    # Maybe this is enough? it
                    # record the new state for planner-internal logging
                    self.planner_interface.planner.record_state_and_input(trajectory.state_list[1])

                    # record the entire trajectory
                    # TODO Alessio: Why do we need to record this trajectory at this point?
                    # self.planner_interface.planner.record_computed_trajectory(trajectory)

                    current_ego_vehicle = self.planner_interface.planner.convert_state_list_to_commonroad_object(trajectory.state_list[replanning_counter:],
                                                                                                                 self.config_simulation.ego_agent_id)

                    # This one sets the ego_vehicle history which is used (also) for plotting        
                    self.planner_interface.planner.set_ego_vehicle_state(current_ego_vehicle=current_ego_vehicle)

                    # This requires the curvilinear trajectory for logging
                    # self.planner_interface.planner.plan_postprocessing(optimal_trajectory=trajectory, planning_time=0.0, replanning_counter=replanning_counter)
                    
                else:
                    # **************************
                    # Cycle Occlusion Module
                    # **************************
                    # if config.occlusion.use_occlusion_module:
                    #     occlusion_module.step(predictions=predictions, x_0=planner.x_0, x_cl=planner.x_cl)
                    #     predictions = occlusion_module.predictions

                    # **************************
                    # Set Planner Subscriptions
                    # **************************

                    # TODO Are the agents that reached goal area still in this scenario!?
                    # Set the agent.already_collided flag
                    # Do they set history?
                    self.planner_interface.update_planner(self.scenario, self.predictions)

                    # **************************
                    # Execute Planner
                    # This includes computing a standing still trajectory until initial delay is passed
                    # **************************
                    # comp_time_start = time.time()
                    trajectory, replanning_counter = self.planner_interface.step_interface(timestep)

                #### At this point we computed - trajectory, replanning_counter
                comp_time_end = time.time()

                # END TIMER
                self.planning_times.append(comp_time_end - comp_time_start)
                self.msg_logger.info(f"Agent {self.id}: Total Planning Time: \t\t{self.planning_times[-1]:.5f} s")

                if trajectory:
                    self._create_collision_object(self.vehicle_history[-1].initial_state,
                                                self.vehicle_history[-1].initial_state.time_step)
                    self.agent_state.log_running(timestep)

                    # plot own view on scenario
                    if (self.save_plot or self.show_plot or self.gif or ((self.config_visu.save_plots or
                                                                        self.config_visu.show_plots) and
                                                                        not self.config.simulation.use_multiagent)):
                        # Here's the SVG
                        visualize_agent_at_timestep(self.scenario, self.planning_problem,
                                                    self.vehicle_history[-1], timestep,
                                                    self.config, self.log_path,
                                                    traj_set=self.all_trajectories,
                                                    optimal_traj=self.planner_interface.trajectory_pair[0],
                                                    ref_path=self.planner_interface.reference_path,
                                                    predictions=self.predictions,
                                                    visible_area=self.visible_area,
                                                    plot_window=self.config_visu.plot_window_dyn, save=self.save_plot,
                                                    show=self.show_plot, gif=self.gif,
                                                    replanning_counter=replanning_counter)

                else:
                    self.msg_logger.critical(f"Agent {self.id}: No Kinematic Feasible and Optimal Trajectory Available!")
                    self.agent_state.log_error(timestep)
                    self.postprocessing()

####################################################################################################
#
####################################################################################################
import os
import time
from multiprocessing import Process, Queue, Event
from queue import Empty
from typing import Optional, List

from commonroad.scenario.scenario import Scenario

from cr_scenario_handler.utils.agent_status import AgentStatus, TIMEOUT
from cr_scenario_handler.simulation.agent_batch import AgentBatch

class CustomAgentBatch(AgentBatch):
     
    def _update_batch(self):
        """
        Extend base implementation by NOT removing Collided Agents
        """
        for agent in reversed(self.running_agent_list):
            if agent.status > AgentStatus.RUNNING:
                # This is used to tell the agent that is done in multiagent
                self.terminated_agent_list.append(agent)

                # Do not remove from the running_agents...
                if agent.status != AgentStatus.COLLISION:
                    self.running_agent_list.remove(agent)
                else:
                    with (open(os.path.join(self.mod_path, "logs", "score_overview.csv"), 'a') as file):
                        msg = "Success" if agent.status == AgentStatus.COMPLETED_SUCCESS else "Failed"
                        line = str(agent.scenario.scenario_id) + ";" + str(agent.id) + ";" + str(agent.current_timestep) + ";" + \
                            str(agent.status) + ";" + str(agent.agent_state.message) + ";" + msg + "\n"
                        file.write(line)

            # Pass the info back to central executor
            # If the agent is COLLIDED leave it be!
            self.out_queue_dict[agent.id] = {"agent_state": agent.agent_state,
                                             "collision_objects": agent.collision_objects[-1],
                                             "vehicle_history": agent.vehicle_history[-1],
                                             "record_state_list": agent.record_state_list[-1],
                                             "record_input_list": agent.record_input_list[-1],
                                             "planning_times": agent.planning_times[-1],
                                             # When the agent fails to compute a trajectory (no one available according to kinematic) this will fail
                                            #  "computed_trajectories": agent.computed_trajectories[-1] if len(agent.computed_trajectories) > 0 else None,
                                             # TODO Maybe better to have a flag? False/True to indicate that whatever trajectory is there it was a panic/emergency one?
                                            #  "record_disengagement": agent.record_disengagement[-1] if len(agent.record_disengagement) > 0 else None,
                                            #  "record_emergency": agent.record_emergency[-1] if len(agent.record_emergency) > 0 else None
                                             }

    def _stop_agents(self):
        self.msg_logger.debug(f"Batch {self.name} Stopping the agents")
        #
        for agent in self.running_agent_list:
            # TODO Check if IDLE and COLLIDED are here!
            agent.planning_times.append(0)
            # If this was running and we finished the tranche it was a success
            agent.agent_state.status = AgentStatus.COMPLETED_SUCCESS
            # TODO Hopefully this does not screw up the data analysis!
            # TODO Check the timestep is indeed correct!
            agent.agent_state.log_finished(agent.agent_state.last_timestep + 1)
            agent.postprocessing()

        # update batch. Create the out_queue_dict
        self._update_batch()
        self.msg_logger.debug(f"Batch {self.name} updated")
        # check for batch completion
        self._check_completion()
        self.msg_logger.debug(f"Batch {self.name} completion checked")
        

    def run(self):
        """
        Extend the original behavior by checking for END events coming from the central simulation
        """
        while True:
            # Receive the next predictions
            # Synchronize agents
            # receive dummy obstacles and outdated agent list
            start_time = time.perf_counter()

            try:
                args = self.in_queue.get(block=True, timeout=TIMEOUT)
            except Empty:
                self.event.set()
                self.msg_logger.error(f"Batch {self.name}: Timeout waiting for "
                                      f"{'simulation' if self.finished else 'agent'} updates!")

                raise RuntimeError(f"Batch {self.name}: Timeout waiting for "
                                   f"{'simulation' if self.finished else 'agent'} updates!")

            if self.event.is_set():
                self.msg_logger.error(f"Batch {self.name}: Termination event is triggered!")
                break

            sync_time_in = time.perf_counter() - start_time

            # This should be the case in which the batch terminates itself via _check_completion()
            if self.finished:
                # if batch finished, postprocess agents (currently only make_gif())
                for agent in self.terminated_agent_list:
                    agent.make_gif()
                self.msg_logger.critical(f"Batch {self.name}: Simulation of the batch finished!")
                break
            elif len(args) < 4:
                # This should be the case in which the batch terminates itself via _check_completion()
                self.finished = True
                self.msg_logger.critical(f"Batch {self.name}: Got {args} message from the simulation!")
                # At this point the simulation will stop and any agent that was running, will be reported as 
                # running. However, agents that were reported as "done" must not be resumed!
                #
                # Make sure we notify the agents!
                # self._stop_agents()
                # We need to send back some message such that agents on both sides synchroni
                # syn_time_out = time.perf_counter()
                # send agent updates to simulation
                # self.out_queue.put(self.out_queue_dict)
                break
            else:
                # simulate next step
                self.step_simulation(*args)

                syn_time_out = time.perf_counter()
                # send agent updates to simulation
                self.out_queue.put(self.out_queue_dict)

            self.process_times.update({"sync_time_out": time.perf_counter() - syn_time_out,
                                       "process_iteration_time": time.perf_counter() - start_time,
                                       "sync_time_in": sync_time_in})

            self.out_queue.put([self.finished, self.process_times])


            if self.event.is_set():
                self.msg_logger.error(f"Batch {self.name}: Termination event is triggered!")
                break
            #print(self.name, self.event.is_set())

####################################################################################################
#
####################################################################################################

# TODO Clean up the imports
import os
import copy
import random
import time
from math import ceil
from multiprocessing import Queue, Event
from queue import Empty
from typing import List
import numpy as np
import traceback
import csv
from datetime import datetime
from copy import deepcopy

import psutil
from commonroad.common.util import AngleInterval
from commonroad.common.util import Interval
from commonroad.scenario.lanelet import Lanelet
from commonroad.geometry.shape import Rectangle, Polygon
from commonroad.planning.goal import GoalRegion
from commonroad.planning.planning_problem import PlanningProblem
from commonroad.prediction.prediction import TrajectoryPrediction
from commonroad.scenario.obstacle import ObstacleType, ObstacleRole, DynamicObstacle
from commonroad.scenario.state import CustomState
from commonroad.scenario.trajectory import Trajectory

# commonroad-dc
from commonroad_dc.boundary.boundary import create_road_boundary_obstacle
from commonroad_dc.collision.collision_detection.pycrcc_collision_dispatch import create_collision_object
from commonroad_dc.collision.trajectory_queries import trajectory_queries

# cr-scenario-handler
import cr_scenario_handler.utils.general as general
import cr_scenario_handler.utils.multiagent_helpers as hf
from cr_scenario_handler.utils.helper_functions import find_lanelet_by_position_and_orientation
import cr_scenario_handler.utils.multiagent_logging as multi_agent_log
import cr_scenario_handler.utils.prediction_helpers as ph
import cr_scenario_handler.utils.visualization as visu
# from cr_scenario_handler.utils.visualization import visualize_multiagent_scenario_at_timestep
from cr_scenario_handler.simulation.agent_batch import AgentBatch
from cr_scenario_handler.simulation.agent import Agent
from cr_scenario_handler.utils.agent_status import TIMEOUT, AgentStatus
# TODO Replace with einlighten
# Show the progress bar
# https://stackoverflow.com/questions/3160699/python-progress-bar


class MultipartSimulation(Simulation):
    """
    This class extends the original implementation to allow arbitrary initial states for agents
    that shall be resumed as part of a stitched execution.
    """

    def __init__(self, config_sim, config_planner, initial_time_step=0, agents_to_resume: List[Agent] = []):
        # TODO Enforce agents to resume ref_path and status if COLLISION!
        # This methos is almost a copy of the original one, but because we need to perform additional operation
        #   instead of calling super we simply copied it. We also added comments

        # Performance Logging
        init_time_start = time.perf_counter()

        # Setup the configuration objects
        self.config = config_sim
        #
        self.config_planner = config_planner
        self.config_simulation = config_sim.simulation
        self.config_visu = config_sim.visualization
        self.config_eval = None

        # TODO Not sure what's this...
        self.event = Event()

        # Setup parallel execution mode
        self._multiproc = self.config_simulation.multiprocessing
        # use specified number of processors, else use all physical cores (-1 bc of the main process)
        self._num_procs = self.config_simulation.num_procs if not self.config_simulation.num_procs == -1 else (psutil.cpu_count(logical=False) - 1)
        
        # Setup Logging
        self.mod_path = self.config_simulation.mod_path
        self.log_path = self.config_simulation.log_path

        # This one should be reinitialized for every simulation?
        # This one logs to messages.log (and console, which is disabled now)
       
        # Make the logger name parametric in the initial_time_step which changes for each tranche
        self.msg_logger = multi_agent_log.logger_initialization(config_sim, self.log_path, f"Simulation_logger_{initial_time_step}")
        # This one logs to the sqlite DB
        self.sim_logger = multi_agent_log.SimulationLogger(self.config)

        # New behaviors and attributes:
        # Keep track of the arbitrary initial time step, which might not be zero as in the base case
        self.initial_time_step = initial_time_step
        self.global_timestep = self.initial_time_step - 1
        # Book-keeping initialization switch
        self.beginning_of_simulation = True
        # Ensure we always replan at the initial step (this might introduce issues is stithing does not sync with replanning cycles...)
        self.replanning_counter = 0

        scenario, self.planning_problem_set = self._open_scenario()

        # Compute the expected duration of the simulation, assuming no crashes.
        # In case no planning problems, max is the last instance of the obstacles
        obstacles_last_time_steps = [state.time_step for obstacle in scenario.obstacles if isinstance(obstacle, DynamicObstacle) for state in obstacle.prediction.trajectory.state_list]
        planning_problems_goal_time_steps = [goal_state.time_step.end for planning_problem in self.planning_problem_set.planning_problem_dict.values() for goal_state in planning_problem.goal.state_list]
        self.expected_last_time_step = max(planning_problems_goal_time_steps + obstacles_last_time_steps)

        # TODO Is this even used?!
        self.original_agent_id = list(self.planning_problem_set.planning_problem_dict.keys())

        # TODO Do not create additional problems for dynamic obstacles. This is confusing...
        # if self.config_simulation.use_multiagent:

        # get all agents IDs
        self.agent_id_list = list(self.planning_problem_set.planning_problem_dict.keys())

        # Make sure that the scenario shared among agents only contains Dynamic Obstacles. Each representing an Ego Vehicle
        self.scenario = self._preprocess_scenario(scenario)

        # additional external Modules
        self._predictor = None
        self._occlusion = None
        self._reach_set = None

        # load additional external modules
        # At the moment it configure prediction via walenet only
        self._load_external_modules()

        # create list with agent batches for parallel batch-wise processing
        self.batch_list, self.agents = self._create_agent_batches(config_planner, agents_to_resume)

        # prepare global collision checker
        self._cc_dyn = None
        self._cc_stat = None
        self._set_collision_check()

        # initialize prediction horizon and horizon
        self.global_predictions = None
        # get prediction horizon if specified in planner-configuration, else use 2.0 seconds by default
        self.prediction_horizon = config_planner.planning.planning_horizon if (hasattr(config_planner, "planning")
                                                                               and hasattr(config_planner.planning,
                                                                                           "planning_horizon")) else 2.0

        self.process_times = dict()

        if self.config.evaluation.evaluate_simulation or self.config.evaluation.evaluate_runtime:
            # if logging is activated log meta data of simulation
            self.sim_logger.log_meta(agent_ids=self.agent_id_list,
                                     original_planning_problem_id=self.original_agent_id,
                                     batch_names={batch.name: batch.agent_ids for batch in self.batch_list},
                                     duration_init=time.perf_counter() - init_time_start,
                                     config_sim=self.config,
                                     config_planner=config_planner)

    def _open_scenario(self):
        """
        opens the scenario specified
        :return: the scenario and the original planning-problem set (empty if none are defined)
        NOTE: This is a modified version of the original code that cannot handle the case of no planning problems specified
        """
        # scenario, _, original_planning_problem_set = general.load_scenario_and_planning_problem(self.config)
        # The following code is a modified version of the above call
        scenario, original_planning_problem_set = CommonRoadFileReader(self.config.simulation.scenario_path).open()
        for planning_problem in original_planning_problem_set.planning_problem_dict.values():
            if not hasattr(planning_problem.initial_state, 'acceleration'):
                planning_problem.initial_state.acceleration = 0.

        return scenario, original_planning_problem_set
    
    def _create_agent_batches(self, config_planner, agents_to_resume: List[Agent] = []):
        """ 
        Extends the basic behavior by ensuring that agents that must be resumed from the previous tranche
        are included in this tranche of simulation. We do so by using a subclass of the original Agent class

        As before, the new and old logic are mingled, so we cannot simply call super(). Instead, we copied
        and modified the original code here.
        """

        batch_list: List[AgentBatch] = []

        agents = []
        agent_ids = self.agent_id_list
        to_be_removed = []
        for agent_id in agent_ids:
            try:
                precomputed_reference_path = None
                precomputed_planner_interface_x_0 = None

                agent_to_resume = next((agent for agent in agents_to_resume if agent.id == agent_id), None)
                
                if agent_to_resume:
                    self.msg_logger.critical(f"Resuming Agent {agent_to_resume.id} for {agent_id}")
                    precomputed_reference_path = deepcopy(agent_to_resume.reference_path)
                    # At this point the agent_to_resume has already moved to the next time step, so we need to get one before
                    # This one instead is one step before?!
                    # self.global_timestep = 5, initial_time_step = 6, x_0.time_step = 7
                    precomputed_planner_interface_x_0 = deepcopy(agent_to_resume.planner_interface.record_state_list[-2])
                
                planning_problem = self.planning_problem_set.find_planning_problem_by_id(agent_id)

                # Make sure we use Agents that can get precomputed reference paths and that can survive after a collision
                agents.append(ResumableAgent(agent_id, planning_problem,
                                self.scenario, config_planner, self.config, self.msg_logger, self.log_path,
                                self.mod_path,
                                # Note this one
                                precomputed_reference_path=precomputed_reference_path,
                                precomputed_planner_interface_x_0=precomputed_planner_interface_x_0))

            except Exception as e:

                def debug_plot():
                    rnd = MPRenderer()
                    self.scenario.draw(rnd)
                    planning_problem.draw(rnd)
                    rnd.render()
                    plt.savefig("temp.png")
                    # plt.show()

                error_traceback = traceback.format_exc()
                to_be_removed.append(agent_id)
                self.msg_logger.critical(f"Agent {agent_id} failed to start because of the following error: \n {str(e)}: {error_traceback}")
                raise RuntimeError("Some agent failed to start. Stop the simulation!")

        if not self._multiproc or self._num_procs < 3 \
                or len(self.agent_id_list) < 2:
            batch_list.append(CustomAgentBatch(agents, self.global_timestep, self.msg_logger, self.log_path, self.mod_path))

        else:
            # We need at least one agent per batch, and one process for the main simulation
            chunk_size = ceil(len(self.agent_id_list) / (self._num_procs))
            chunks = [agents[ii * chunk_size: min(len(agents), (ii + 1) * chunk_size)] for ii in range(0, self._num_procs)]
            for i, chunk in enumerate(chunks):
                if not chunk:
                    # no empty chucks allowed
                    continue
                inqueue = Queue()
                outqueue = Queue()

                batch_list.append(CustomAgentBatch(chunk, self.global_timestep, self.msg_logger, self.log_path, self.mod_path,
                                             outqueue, inqueue, self.event))

        return batch_list, agents

    def run_simulation(self, stop_simulation_after_simulation_steps : Optional[int] = None):
        """ 
        Extends the basic behavior by optionally forcing to stop the simulation after some time
        TODO For the agents to resume ensure that reference path is given and state is maintained if COLLISION 
        """

        if stop_simulation_after_simulation_steps:
            new_expected_duration = self.initial_time_step + stop_simulation_after_simulation_steps
            self.msg_logger.info(f"Forcing to stopping the simulation at {new_expected_duration}. {stop_simulation_after_simulation_steps} steps after {self.initial_time_step}")
            self.expected_last_time_step = new_expected_duration
            self.msg_logger.info(f"New expected simulation duration is {self.expected_last_time_step}")

        sim_time_start = time.perf_counter()
        # start agent batches
        if len(self.batch_list) == 1:
            # If we have only one batch, run sequential simulation
            self.run_sequential_simulation()
        else:
            # run parallel simulation
            self.run_parallel_simulation()

        sim_duration = time.perf_counter() - sim_time_start

        # TODO Maybe just info?
        self.msg_logger.critical(f"Simulation completed")

        # TODO Consider moving post processing, outside simulation
        post_time = time.perf_counter()
        self.postprocess_simulation()
        post_duration = time.perf_counter() - post_time

        if self.config.evaluation.evaluate_simulation or self.config.evaluation.evaluate_runtime:
            self.sim_logger.update_meta(scenario_name=self.config_simulation.name_scenario,
                                        sim_duration=sim_duration, post_duration=post_duration)
            self.sim_logger.log_results(self.agents)
    
    def step_sequential_simulation(self):
        """
        Enforce that the simulation is reported as finished also if the provided timeout triggers
        """

        # Invoke the original code
        running = super().step_sequential_simulation()

        # Ensure to forcefully stop the simulation if the global timeout triggers
        return running and self.global_timestep <= self.expected_last_time_step

    def _step_parallel_simulation(self):
        """
        Enforce that the simulation is reported as finished also if the provided timeout triggers.
        Note. we recompute the self.replanning_counter because the original implementation is buggy.
        See: https://github.com/TUM-AVS/Frenetix-Motion-Planner/issues/8
        We also fix the issue with visualization of time_step = -1
        """
        # Ensure we update the replanning counter to avoid predicting at every step, which currently
        # expect to be synched with planner effective planning cycle
        if int(self.replanning_counter / self.config_planner.planning.replanning_frequency) == 1:
            self.replanning_counter = 0

        # Patched version of the original code
        # update Scenario, calculate new predictions and check for collision of prev. iteration
        self.global_predictions, colliding_agents = self.prestep_simulation()
        # send data to each batch process
        for batch in self.batch_list:
            batch.in_queue.put([self.scenario, self.global_timestep, self.global_predictions,
                                colliding_agents])

        # Plot previous timestep while batches are busy - but ensure that we do not plot invalid timesteps
        if self.global_timestep > 0:
            self.visualize_simulation(self.global_timestep - 1)

        syn_time = time.perf_counter()
        # Receive simulation step results
        for batch in reversed(self.batch_list):
            if self.event.is_set():
                # an error occured in subprocesses
                self.msg_logger.error(f"Simulation received a termination event from child processes!")
                raise ChildProcessError(f"Simulation received a termination event from child processes!")
            try:
                # update agents
                queue_dict = batch.out_queue.get(block=True, timeout=TIMEOUT)
                agent_ids = list(queue_dict.keys())

                for agent_id in agent_ids:
                    agent = self.get_agent_by_id(agent_id)
                    for attr, value in queue_dict[agent_id].items():
                        if hasattr(agent, attr):
                            if type(getattr(agent, attr)) != list:
                                setattr(agent, attr, value)
                            elif attr == "all_trajectories":
                                setattr(agent, attr, value)

                            else:
                                getattr(agent, attr).append(value)
                        else:
                            self.event.set()
                            raise AttributeError(f"{attr} is no valid attribute for the agents")
                # check if batch is finished
                [batch_finished, proc_times] = batch.out_queue.get(block=True, timeout=TIMEOUT)
                self.msg_logger.debug(f"Simulation received batch infos from batch {batch.name}")
                self.process_times[batch.name] = proc_times
                if batch_finished:
                    self.msg_logger.debug(f"Start closing Batch {batch.name}")
                    # terminate finished process
                    batch.in_queue.put("END", block=True)
                    batch.join()
                    self.batch_list.remove(batch)
                    self.msg_logger.critical(f"Closing Batch {batch.name}")
            except Empty:
                if self.event.is_set():
                    # an error occured in subprocesses
                    self.msg_logger.error(f"Simulation received a termination event from child processes!")
                    raise ChildProcessError(f"Simulation received a termination event from child processes!")
                self.msg_logger.error(f"Timeout while waiting for step results of batch {batch.name}!")
                self.event.set()
                raise Empty(f"Timeout while waiting for step results of batch {batch.name}!")
        self.process_times["time_sync"] = time.perf_counter() - syn_time

        running = len(self.batch_list) > 0

        # Ensure we update the replanning counter to avoid predicting at every step, which currently
        # expect to be synched with planner effective planning cycle
        self.replanning_counter += 1    

        # Ensure to forcefully stop the simulation if the global timeout triggers
        return running and self.global_timestep <= self.expected_last_time_step

    def check_collision(self):
        """
        Controls agents for collisions with other agents, obstacles and the road boundaries.
        Extends the original behavior by checking collisions also with already collided objects (multi-vehicle
        collisions) since we DO not remove collided objects from the scenarios. 
        We also added more verbose logging to report different types of collisions
        """
        coll_objects = []
        agent_ids = []
        collided_agents = []
        # get collision objects from agents, including those already collided
        for agent in self.agents:
            if agent.status == AgentStatus.RUNNING or agent.status == AgentStatus.COLLISION:
                coll_objects.append(agent.collision_objects[-1])
                agent_ids.append(agent.id)

        # check if any agent collides with a static obstacle / road boundary
        coll_time_stat = trajectory_queries.trajectories_collision_static_obstacles(coll_objects, self._cc_stat)
        if any(i > -1 for i in coll_time_stat):
            index = [i for i, n in enumerate(coll_time_stat) if n != -1]
            collided_agents.extend([agent_ids[i] for i in index])
            self.msg_logger.debug(f"** Identified collision with static obstacles for agents {[agent_ids[i] for i in index]} at time {coll_time_stat}")

        # # check if any agent collides with a dynamic obstacle
        coll_time_dyn = trajectory_queries.trajectories_collision_dynamic_obstacles(coll_objects, self._cc_dyn)
        if any(i > -1 for i in coll_time_dyn):
            index = [i for i, n in enumerate(coll_time_dyn) if n != -1]
            collided_agents.extend([agent_ids[i] for i in index])
            self.msg_logger.debug(f"** Identified collision with dynamic obstacles for agents {[agent_ids[i] for i in index]} at time {coll_time_stat}")

        # check if agents crash against each other
        if len(coll_objects) > 1:
            # Check only those objects that are NOT yet collided.
            for index, ego in enumerate(coll_objects):

                # if ego.status == AgentStatus.COLLISION:
                    # self.msg_logger.critical(f"Skip collisions checking for collided ego {ego.id}")
                
                # Check collisions to others vehicles including the collided ones!
                other_agents = copy.copy(coll_objects)
                other_agents.remove(ego)
                coll_time = trajectory_queries.trajectories_collision_dynamic_obstacles([ego], other_agents,
                                                                                        method='box2d')
                if coll_time != [-1]:
                    # collision detected
                    self.msg_logger.debug(f"** Identified collision for ego {agent_ids[index]} at time {coll_time}")
                    collided_agents.append(agent_ids[index])

        if len(collided_agents) > 0:
            self.msg_logger.debug(f"Collision detected for agents {collided_agents}")

        return collided_agents

    def update_scenario(self):
        """
        Extend the original behavior by including already collided objects and ensuring that we can deal with simulations tranches starting at arbitrary
        time_steps
        
        TODO Collided agents MUST stay still
        """
        if self.beginning_of_simulation:
            self.beginning_of_simulation = False
            return
        
        shape = Rectangle(self.config.vehicle.length, self.config.vehicle.width)
        
        updated_agents = []
        # Update RUNNING and COLLISION agents
        for agent in [a for a in self.agents if a.status == AgentStatus.RUNNING or a.status == AgentStatus.COLLISION]:
            # Why the double check?!
            # if agent.status == AgentStatus.RUNNING:  # and agent.id not in colliding_agents:
            obs = self.scenario.obstacle_by_id(agent.id)
            initial_timestep = obs.prediction.trajectory.initial_time_step
            # add calculated position to trajectory of dummy obstacles
            if len(obs.prediction.trajectory.state_list) > 1:
                traj = (obs.prediction.trajectory.states_in_time_interval(initial_timestep,
                                                                            self.global_timestep - 1)
                        + agent.vehicle_history[-1].prediction.trajectory.state_list[1:])

            else:
                traj = agent.vehicle_history[-1].prediction.trajectory.state_list[1:]

            lanelet_assigned = obs.prediction.center_lanelet_assignment
            obs.prediction = TrajectoryPrediction(
                Trajectory(initial_time_step=traj[0].time_step, state_list=traj), shape,
                center_lanelet_assignment=lanelet_assigned)
            
            updated_agents.append(agent.id)
        
        # Update all the OTHER Agents.
        agents_to_update = [agent for agent in self.agents if (agent.status != AgentStatus.RUNNING and agent.status != AgentStatus.IDLE and agent.status != AgentStatus.COLLISION)]

        for agent in agents_to_update:
            obs = self.scenario.obstacle_by_id(agent.id)
            initial_timestep = obs.prediction.trajectory.initial_time_step  # agent.agent_state.first_timestep
            lanelet_assigned = obs.prediction.center_lanelet_assignment
            traj = obs.prediction.trajectory.states_in_time_interval(initial_timestep, agent.agent_state.last_timestep)
            obs.prediction = TrajectoryPrediction(
                Trajectory(initial_time_step=traj[0].time_step, state_list=traj), shape,
                center_lanelet_assignment=lanelet_assigned)

    def visualize_simulation(self, timestep):
        """
        Extends the basic behavior by calling a custom visualize_multiagent_scenario_at_timestep method that takes additional parameters
        """
        if ((self.config_visu.show_plots or self.config_visu.save_plots or self.config_visu.save_gif)
                and self.config_simulation.use_multiagent):
            time_visu = time.perf_counter()
            
            ######
            ### TODO Fix me with the right code that takes the right input including figsize and the like
            custom_visualize_multiagent_scenario_at_timestep(self.scenario,
                                                      self.agents,
                                                      timestep, self.config, self.log_path,
                                                      orig_pp_id=self.original_agent_id,
                                                      predictions=self.global_predictions,
                                                      plot_window=self.config_visu.plot_window_dyn,
                                                      save=self.config_visu.save_plots,
                                                      show=self.config_visu.show_plots,
                                                      gif=self.config_visu.save_gif,
                                                      figsize=(self.config_visu.plot_height, self.config_visu.plot_width),
                                                      plot_format=self.config_visu.plot_format)
            self.process_times["time_visu"] = time.perf_counter() - time_visu



###########################
#   TODO: Refactor me!!
###########################
from rich.logging import RichHandler
def logger_initialization(logLevel: str, logger = "FrenetixScenarioExecution_logger") -> logging.Logger:
    """
    Log only on the console
    """
    msg_logger = logging.getLogger(logger)
    msg_logger.setLevel(logLevel)
    msg_logger.addHandler(RichHandler())
    msg_logger.propagate = False

    return msg_logger

from commonroad_extensions.scenario_execution.macro_agent_simulation import MacroAgentSimulation

class FrenetixScenarioExecution():
    
    # TODO Add details about the planner !
    def __init__(self, output_folder:str, frenetix_root: str, additional_config: OmegaConf) -> None:   
        # Mandatory values    
        self.output_folder = output_folder
        self.frenetix_root = frenetix_root

        # Refactor this code managing the options!
        self.debug = OmegaConf.select(additional_config, "debug", default=False)
        self.verbose = OmegaConf.select(additional_config, "verbose", default=False)
        self.driving_agent_name = OmegaConf.select(additional_config, "driving_agent_name", default="frenetix")
        # This might require some adjustment because the execution can only start at replanning cycle of the agent
        # Or we need to enfore the state (e.g., previus trajectories) which is cumbersome
        self.tranche_size_time_step = OmegaConf.select(additional_config, "tranche_size_time_step", default=None)
        # Other local configurations 
        self.plot_height = additional_config.plot_height
        self.plot_width = additional_config.plot_width
        self.plot_format = additional_config.plot_format
        

        self.override_config_sim = additional_config.config_sim
        self.override_config_planner = additional_config.config_planner

        # Load the default simulation configuration from the Frenetix Motion Planner configuration module
        # and extract the replanning frequency
        self.replanning_frequency = PatchedConfigurationBuilder.build_frenetplanner_configuration("dummy", module="frenetix_motion_planner", root_path=self.frenetix_root).planning.replanning_frequency
        
        # We do not have a simulation folder at the moment, since that is set when executing the simulation
        logLevel = 'DEBUG' if self.verbose else 'CRITICAL'
        # Use default logger name
        self.msg_logger = logger_initialization(logLevel)


        # Adjust the tranche_size such that trace starts always at replanning frequency to obtain the same
        # behavior of the original (long) scenario execution
        if self.tranche_size_time_step is not None:
            adjusted_tranche_size_time_step = self.tranche_size_time_step
            while adjusted_tranche_size_time_step % self.replanning_frequency != 0:
                adjusted_tranche_size_time_step = adjusted_tranche_size_time_step + 1
            if adjusted_tranche_size_time_step != self.tranche_size_time_step:
                self.msg_logger.info(f"Adjusting the tranche size to {self.tranche_size_time_step} to match planner replanning frequency {self.replanning_frequency}")
                self.tranche_size_time_step = adjusted_tranche_size_time_step
        
    # TODO Use the one from simulation_visualization instead?
    def visualize_the_scenario(self, scenario, planning_problem_set, output_folder):
        """
        Visualize and plot the initial scenario
        """

        import matplotlib.pyplot as plt
        import matplotlib.colors as colors

        planning_problems = sorted(planning_problem_set.planning_problem_dict.values(), key= lambda pp : pp.planning_problem_id)

        unique_colors = _get_cmap(len(planning_problems), 'rainbow')
        
        figsize = (self.plot_height, self.plot_width)

        rnd = MPRenderer(figsize=figsize)

        # set renderer draw params
        rnd.draw_params.time_begin = 0
        rnd.draw_params.dynamic_obstacle.draw_icon = True

        # Draw Road and Obstacles at time stamp
        scenario.draw(rnd)
        
        for i, planning_problem in enumerate(planning_problems):
            from commonroad.planning.planning_problem import PlanningProblem
            planning_problem: PlanningProblem
            # set renderer draw params
            rnd.draw_params.planning_problem.initial_state.state.facecolor = colors.to_hex(unique_colors(i))
            rnd.draw_params.planning_problem.initial_state.state.draw_arrow = True
            rnd.draw_params.planning_problem.initial_state.state.radius = 0.5
            
            # Add labels
            rnd.draw_params.planning_problem.initial_state.label= f"{planning_problem.planning_problem_id} - {planning_problem.initial_state.velocity}"

            rnd.draw_params.planning_problem.goal_region.shape.facecolor = colors.to_hex(unique_colors(i))
            rnd.draw_params.planning_problem.goal_region.shape.opacity = 0.5
                
            # Include the arrow here!
            planning_problem.draw(rnd)

        # Render the plot
        rnd.render()

        # # Get the x, y limts without vehicles
        # x_lim = rnd.ax.get_xlim()
        # y_lim = rnd.ax.get_ylim()

        # # Plot the reference path of the planners
        # for planner in planners:
        #     rnd.ax.plot(planner.reference_path[:, 0], planner.reference_path[:, 1], color='g', marker='.', markersize=1, zorder=19, linewidth=0.8,
        #                 label=f'reference path planner {planner.name}')
            
        # # Get the x, y limts without the annotations
        # rnd.ax.set_xlim(x_lim)
        # rnd.ax.set_ylim(y_lim)

        plt.savefig(f"{output_folder}/scenario.{self.plot_format}", format=self.plot_format, bbox_inches='tight')

    def _execute_as_single_simulation(self, scenario, planning_problem_set,
                                      simulation_folder:str, scenario_name:str,
                                      stop_simulation_after_simulation_steps=None,
                                      agents_to_resume: List[Agent] = [],
                                      meta_data: Dict[str, Any] = {}) -> Simulation:
        """
        Execute a single simulation, producing a folder with all the results, plots, logs, etc. in a given location defined by
        exeuction_folder
        """

        # Create the folders for the simulation
        os.makedirs(simulation_folder, exist_ok=False)
        # Ensure the input scenario is where the Simulator class expects it. Note how we define scenario_file_name
        store_scenario_and_planning_problems_to_output_folder(scenario, planning_problem_set, simulation_folder, scenario_file_name=f"{scenario_name}.xml")
        # Plot the scenario and planning problems for reference
        self.visualize_the_scenario(scenario, planning_problem_set, simulation_folder)
        # Collect here the execution logs and the usual plots generated by Frenetix
        logs_folder = os.path.join(simulation_folder, "logs")
        os.makedirs(logs_folder, exist_ok=False)

        # Load the default simulation configuration from the Frenetix Motion Planner configuration module
        # config_sim = ConfigurationBuilder.build_sim_configuration(scenario_name, simulation_folder, root_path=self.frenetix_root, module="simulation")
        config_sim = PatchedConfigurationBuilder.build_sim_configuration(scenario_name, simulation_folder, root_path=self.frenetix_root, module="simulation")

        # Make sure we write the logs in the right folder
        config_sim.simulation.log_path = logs_folder
        
        # Load the default planner configuration from the Frenetix Motion Planner configuration module
        # Ideally, each vehicle should have its own planner...
        # config_planner = ConfigurationBuilder.build_frenetplanner_configuration(scenario_name, module="frenetix_motion_planner", root_path=self.frenetix_root)
        config_planner = PatchedConfigurationBuilder.build_frenetplanner_configuration(scenario_name, module="frenetix_motion_planner", root_path=self.frenetix_root)
        
        # Apply any custom provided overrides if any
        # TODO Ideally, we should not allow "important" configurations to be overridden...
        override_configuration(config_sim, self.override_config_sim)
        override_configuration(config_planner, self.override_config_planner)

        # TODO Move to utility method

        # All the configurations used for this execution will be stored in simulation.db, table meta, but we also store them in planning text
        pickled_configurations_folder = os.path.join(simulation_folder, "pickled_configurations")
        os.makedirs(pickled_configurations_folder, exist_ok=False)
        config_sim_pickled = os.path.join(pickled_configurations_folder, "config_sim.pickled")
        with open(config_sim_pickled, 'wb') as f:
            pickle.dump(config_sim, f)

        config_planner_pickled = os.path.join(pickled_configurations_folder, "config_planner.pickled")
        with open(config_planner_pickled, 'wb') as f:
            pickle.dump(config_planner, f)

        # Start the simulation
        simulation = None

        # TODO Replace print with msg_logger or similar
        try:
            # If any agent fails to start, this will trigger an exception, and stop the simulation
            # see: https://stackoverflow.com/questions/7604966/maximum-and-minimum-values-for-ints
            initial_time_step_from_obstacles = min([sys.maxsize * 2] + [obstacle.initial_state.time_step for obstacle in scenario.obstacles if isinstance(obstacle, DynamicObstacle)])
            initial_time_step_from_planning_problems = min([sys.maxsize * 2] + [planning_problem.initial_state.time_step for planning_problem in planning_problem_set.planning_problem_dict.values()])
            initial_time_step = min(initial_time_step_from_obstacles, initial_time_step_from_planning_problems)
            # min([planning_problem.initial_state.time_step for planning_problem in planning_problem_set.planning_problem_dict.values()])
            
            # Dump for each agent to resume its precomputed reference path. This allows us to 
            # resume the execution from the tranche, which is useful for debugging
            for agent_to_resume in agents_to_resume:
                reference_path_file = os.path.join(simulation_folder, f"reference_path_{agent_to_resume.id}.dat")
                agent_to_resume.reference_path.tofile(reference_path_file)

            self.msg_logger.critical(f"Simulation Initial Time Step = {initial_time_step}")
            simulation = MultipartSimulation(config_sim, config_planner, initial_time_step, agents_to_resume=agents_to_resume)
            
            # TODO Run this simulation for the given amount of steps
            simulation.run_simulation(stop_simulation_after_simulation_steps=stop_simulation_after_simulation_steps)

            # Ensure that the data reported in the executed scenario refer only to agents' history and NOT their planning activities
            clip_executed_scenario(simulation, inplace=True)
            #
            store_executed_scenario_to_output_folder(simulation.scenario, simulation_folder)

        except Exception as e:
            error_traceback = traceback.format_exc()  # This gets the entire error traceback
            current_time = datetime.now().strftime('%H:%M:%S')
            # Check if simulation is not None before trying to access current_timestep
            current_timestep = str(simulation.global_timestep) if simulation else "N/A"
            # TODO Log to msg_logger
            self.msg_logger.critical("Error time: " + str(current_time) + " ; " +
                  "In Scenario Timestep: " + current_timestep + " ; " +
                  "CODE ERROR: " + str(e) + error_traceback + "\n\n\n\n")
            raise e
        finally:
            try:
                # close sim_logger
                simulation.sim_logger.con.close()
                # close child processes
                simulation.close_processes()
            except:
                pass
        
        return simulation

    def _generate_planning_problems_from_simulation_state(self, 
                                                          scenario: Scenario, original_planning_problem_set: PlanningProblemSet,
                                                          agents_to_resume: List[Agent]) -> List[PlanningProblem]:
        
        # TODO Why can't we simply REUSE the same Agent objects !!!
        # TODO: Will this also change the reference path?!

        planning_problems = []
        
        if agents_to_resume:
            # TODO How to deal with the COLLIDED agents? For the moment, 
            #   we let them be and hope they will collide right away?
            # TODO Pay attention to the current_timestep!!
            for agent in agents_to_resume:
                original_planning_problem_for_agent = original_planning_problem_set.planning_problem_dict[agent.id]
                original_initial_state = original_planning_problem_for_agent.initial_state
                # The very last recorded state is the one compute during the latest step of the simulation, 
                # which is NOT the one we need. So -2

                # last_recorded_state_from_state_list = agent.record_state_list[-2]
                # This is the correct state because:
                #   agent.vehicle_history[0].initial_state is the same as original_planning_problem_for_agent.initial_state
                last_recorded_state = agent.vehicle_history[-1].initial_state
                # last_from_computed_trajectory = agent.computed_trajectories[-1].initial_state

                # Create the initial state to match the last state recorded by the agent
                updated_initial_state = deepcopy(original_initial_state)
                
                mandatory_fields = ["position", "steering_angle", "velocity", "orientation", "acceleration", "yaw_rate", "slip_angle", "time_step"]
                for field_name in mandatory_fields:
                    # ReactivePlannerState does not have slip_angle
                    try:
                        setattr(updated_initial_state, field_name, getattr(last_recorded_state, field_name))
                    except AttributeError as attr_err:
                        self.msg_logger.critical(f"Forcing attribute {field_name} missing in the initial state of agent {agent.id}!")
                        setattr(updated_initial_state, field_name, 0.0)

                # TODO Proper handling of collided agents shall be implemented
                # TODO Make sure we take the latest!
                if agent.agent_state.status is AgentStatus.COLLISION:
                    self.msg_logger.critical(f"Agent {agent.id} COLLIDED. last_recorded_state.time_step = {last_recorded_state.time_step} is not agent.current_timestep = {agent.current_timestep}")
                    assert updated_initial_state.time_step == max(last_recorded_state.time_step, agent.current_timestep)
                else:
                    assert last_recorded_state.time_step == agent.current_timestep, f"Time step mistmatch for agent {agent.id}"


                # Use the same id
                updated_planning_problem_id = original_planning_problem_for_agent.planning_problem_id
                # Use the same goal. TODO are those the same?
                updated_goal_region = deepcopy(original_planning_problem_for_agent.goal)

                updated_planning_problem_for_agent = PlanningProblem(updated_planning_problem_id, 
                                                                     updated_initial_state, 
                                                                     updated_goal_region)
                
                planning_problems.append(updated_planning_problem_for_agent)

        [self.msg_logger.critical(f"Agent {planning_problem.planning_problem_id} resuming execution.") for planning_problem in planning_problems]

        return planning_problems
    
    def _execute_as_simulation_with_macro_agents(self, scenario: Scenario, planning_problem_set: PlanningProblemSet, simulation_id: int, 
                                       max_duration: Optional[int] = None) -> Tuple[Dict, List[Simulation]]:
        """
        Use the MacroAgents instead of the base agents.
        A MacroAgent is an agent that must solve a sequence of consecutive goals. The implemented solution works like this:
        - monitor the execution of the simulation and "check" if the agent reached its goal
        - update the agent (or instantiate a new one replacing it) that resumes from that state but travel to the next goal
        - if an agent collides, remains so until the end of the scenario not matter the goals

        """

        meta_data = dict()
        
        expected_last_time_step = max([goal_state.time_step.end for planning_problem in planning_problem_set.planning_problem_dict.values() for goal_state in planning_problem.goal.state_list])
        initial_time_step = min([planning_problem.initial_state.time_step for planning_problem in planning_problem_set.planning_problem_dict.values()])

        meta_data["initial_time_step"] = initial_time_step
        meta_data["expected_last_time_step"] = expected_last_time_step

        if max_duration is not None:
            meta_data["max_duration"] = max_duration

        # Create the folder containing the simulation output and the tranches folder
        simulation_folder = os.path.join(self.output_folder, f"simulation_{str(simulation_id).rjust(5, '0')}")
        os.makedirs(simulation_folder, exist_ok=False)
        
        meta_data["simulation_folder"] = simulation_folder

        # Keep track of how many agents need to run - Not sure we need this
        ids_of_agents_to_run: List[int] = [pp.planning_problem_id for pp in planning_problem_set.planning_problem_dict.values()]

        # We keep the generic name since the folder already identifies the simulation id and tranche id
        scenario_name = "scenario"
        
        # Ensure the input scenario is where the Simulator class expects it. Note how we define scenario_file_name
        store_scenario_and_planning_problems_to_output_folder(scenario, planning_problem_set, simulation_folder, scenario_file_name=f"{scenario_name}.xml")
        # Plot the scenario and planning problems for reference
        self.visualize_the_scenario(scenario, planning_problem_set, simulation_folder)
        # Collect here the execution logs and the usual plots generated by Frenetix
        logs_folder = os.path.join(simulation_folder, "logs")
        os.makedirs(logs_folder, exist_ok=False)

        # Load the default simulation configuration from the Frenetix Motion Planner configuration module
        # config_sim = ConfigurationBuilder.build_sim_configuration(scenario_name, simulation_folder, root_path=self.frenetix_root, module="simulation")
        config_sim = PatchedConfigurationBuilder.build_sim_configuration(scenario_name, simulation_folder, root_path=self.frenetix_root, module="simulation")

        # Make sure we write the logs in the right folder
        config_sim.simulation.log_path = logs_folder
        
        # Load the default planner configuration from the Frenetix Motion Planner configuration module
        # Ideally, each vehicle should have its own planner...
        # config_planner = ConfigurationBuilder.build_frenetplanner_configuration(scenario_name, module="frenetix_motion_planner", root_path=self.frenetix_root)
        config_planner = PatchedConfigurationBuilder.build_frenetplanner_configuration(scenario_name, module="frenetix_motion_planner", root_path=self.frenetix_root)
        
        # Apply any custom provided overrides if any
        # TODO Ideally, we should not allow "important" configurations to be overridden...
        override_configuration(config_sim, self.override_config_sim)
        override_configuration(config_planner, self.override_config_planner)

        # TODO Move to utility method

        # All the configurations used for this execution will be stored in simulation.db, table meta, but we also store them in planning text
        pickled_configurations_folder = os.path.join(simulation_folder, "pickled_configurations")
        os.makedirs(pickled_configurations_folder, exist_ok=False)
        config_sim_pickled = os.path.join(pickled_configurations_folder, "config_sim.pickled")
        with open(config_sim_pickled, 'wb') as f:
            pickle.dump(config_sim, f)

        config_planner_pickled = os.path.join(pickled_configurations_folder, "config_planner.pickled")
        with open(config_planner_pickled, 'wb') as f:
            pickle.dump(config_planner, f)

        # Start the simulation
        simulation = None

        # TODO Replace print with msg_logger or similar
        try:
            # If any agent fails to start, this will trigger an exception, and stop the simulation
            initial_time_step = min([planning_problem.initial_state.time_step for planning_problem in planning_problem_set.planning_problem_dict.values()])
            
            simulation = MacroAgentSimulation(config_sim, config_planner)
            
            stop_simulation_after_simulation_steps = None if max_duration is None else max(0, initial_time_step) + max_duration
            
            self.msg_logger.critical(f"Simulation Initial Time Step = {initial_time_step} and it will stop after {stop_simulation_after_simulation_steps} steps")

            simulation.run_simulation(stop_simulation_after_simulation_steps=stop_simulation_after_simulation_steps)

            # Ensure that the data reported in the executed scenario refer only to agents' history and NOT their planning activities
            clip_executed_scenario(simulation, inplace=True)
            
            # TODO For some reason the scenario does not have all the attributes of the original scenario?!
            store_executed_scenario_to_output_folder(simulation.scenario, simulation_folder)

        except Exception as e:
            error_traceback = traceback.format_exc()  # This gets the entire error traceback
            current_time = datetime.now().strftime('%H:%M:%S')
            # Check if simulation is not None before trying to access current_timestep
            current_timestep = str(simulation.global_timestep) if simulation else "N/A"
            # TODO Log to msg_logger
            self.msg_logger.critical("Error time: " + str(current_time) + " ; " +
                  "In Scenario Timestep: " + current_timestep + " ; " +
                  "CODE ERROR: " + str(e) + error_traceback + "\n\n\n\n")
            raise e
        finally:
            try:
                # close sim_logger
                simulation.sim_logger.con.close()
                # close child processes
                simulation.close_processes()
            except:
                pass
        
        # We retun a List of simulations to be compliant with the other interface. In theory, execute as stitched simulation should return only a simulation
        #   object after merging several together which is NOT yet implemented (and possibly not needed)
        return meta_data, [simulation]

    def _execute_as_stiched_simulation(self, scenario: Scenario, planning_problem_set: PlanningProblemSet, simulation_id: int, 
                                       max_duration: Optional[int] = None) -> Tuple[Dict, List[Simulation]]:
        
        meta_data = dict()
        
        #
        # Compute the stitching information based on the planning_problem_set
        #
        
        expected_last_time_step_from_obstacles = max([0] + [state.time_step for obstacle in scenario.obstacles if isinstance(obstacle, DynamicObstacle) for state in obstacle.prediction.trajectory.state_list])
        expected_last_time_step_from_planning_problems = max([0] + [goal_state.time_step.end for planning_problem in planning_problem_set.planning_problem_dict.values() for goal_state in planning_problem.goal.state_list])
        expected_last_time_step = max(expected_last_time_step_from_obstacles, expected_last_time_step_from_planning_problems)
       
        # see: https://stackoverflow.com/questions/7604966/maximum-and-minimum-values-for-ints
        initial_time_step_from_obstacles = min([sys.maxsize * 2] + [obstacle.initial_state.time_step for obstacle in scenario.obstacles if isinstance(obstacle, DynamicObstacle)])
        initial_time_step_from_planning_problems = min([sys.maxsize * 2] + [planning_problem.initial_state.time_step for planning_problem in planning_problem_set.planning_problem_dict.values()])
        initial_time_step = min(initial_time_step_from_obstacles, initial_time_step_from_planning_problems)
       

        meta_data["initial_time_step"] = initial_time_step
        meta_data["expected_last_time_step"] = expected_last_time_step

        if max_duration is not None:
            meta_data["max_duration"] = max_duration
            # Ensure we do not execute MORE than max_duration
            expected_last_time_step = max_duration

        # Create the folder containing the simulation output and the tranches folder
        simulation_folder = os.path.join(self.output_folder, f"simulation_{str(simulation_id).rjust(5, '0')}")
        os.makedirs(simulation_folder, exist_ok=False)
        
        meta_data["simulation_folder"] = simulation_folder

        tranches_output_folder = os.path.join(simulation_folder, "tranches")

        # Keep track of how many agents need to run
        ids_of_agents_to_run: List[int] = [pp.planning_problem_id for pp in planning_problem_set.planning_problem_dict.values()]
        total_number_of_agents = len(ids_of_agents_to_run)

        agents_to_resume: List[Agent] = list()
        
        tranche_simulations: List[Simulation] = list()

        # By default there's only one tranche
        n_tranches = 1
        if self.tranche_size_time_step is not None:
            n_tranches = expected_last_time_step // self.tranche_size_time_step + (1 if expected_last_time_step % self.tranche_size_time_step != 0 else 0)

        # If there's only one tranche, its duration is the max duration of the scenario
        tranche_duration_time_step = self.tranche_size_time_step if self.tranche_size_time_step is not None else expected_last_time_step

        meta_data["n_tranches"] = n_tranches
        meta_data["tranche_duration_time_step"] = tranche_duration_time_step

        manager = enlighten.Manager()
        vehicles_pbar = manager.counter(desc='Tranches', total=n_tranches)

        # Execute one tranche after the other!
        for tranche_id in vehicles_pbar(range(n_tranches)):
            # TODO Pay attention to first and last timestep!
            # tranche_id = 0 -> 0 = 0 * 100, 1 -> 100
            initial_time_step = tranche_id * tranche_duration_time_step

            if max_duration is not None and initial_time_step >= max_duration:
                self.msg_logger.critical(f"Skipping Tranche {tranche_id} starting after max_duration {max_duration} and stopping the execution")
                continue
            
            msg = f" Executing Tranche {tranche_id} starting at time {initial_time_step} and ending at time {initial_time_step + tranche_duration_time_step}."
            banner = "=" * (len(msg) + 2)
            self.msg_logger.critical("\n".join([banner, msg, banner]))

            # TODO check boundary!
            # Filter out traffic that has not yet started but will start in this tranche
            tranche_planning_problem_list = [planning_problem for planning_problem in planning_problem_set.planning_problem_dict.values()
                                                if initial_time_step <= planning_problem.initial_state.time_step < initial_time_step + tranche_duration_time_step]
            [self.msg_logger.critical(f"Agent {planning_problem.planning_problem_id} starting") for planning_problem in tranche_planning_problem_list]
            # Include planning problems from the previous tranche that are still there
            tranche_planning_problem_list.extend(self._generate_planning_problems_from_simulation_state(scenario, planning_problem_set, agents_to_resume))
            # Create the PlanningProblemSet for the Single Simulation
            tranche_planning_problem_set = PlanningProblemSet(tranche_planning_problem_list)
            #
            tranche_exeuction_folder_name = str(tranche_id).rjust(5, '0')
            # This is under output_folder/tranches/{tranche_id}
            tranche_execution_folder = os.path.join(tranches_output_folder, tranche_exeuction_folder_name)
            
            # We keep the generic name since the folder already identifies the simulation id and tranche id
            scenario_name = "scenario"
            
            # We need to stop the simulation one instant before the last replanning?
            stop_simulation_after_simulation_steps = tranche_duration_time_step - 1
            
            if max_duration is not None:
                # Compute the remaining steps including the max duration
                end_of_tranche = tranche_id * tranche_duration_time_step + tranche_duration_time_step
                if end_of_tranche > max_duration:
                    offset = end_of_tranche - max_duration
                    stop_simulation_after_simulation_steps = stop_simulation_after_simulation_steps - offset

            # The scenario here is the global one, which is updated by each batch
            tranche_simulation = self._execute_as_single_simulation(scenario, tranche_planning_problem_set, tranche_execution_folder,
                                                    scenario_name, stop_simulation_after_simulation_steps, agents_to_resume=agents_to_resume)
            
            # Extract the current state (keep the agents that are still active by the end of the simulation)
            agents_to_resume = [ agent for agent in tranche_simulation.agents if agent.agent_state.status in [ AgentStatus.RUNNING, AgentStatus.COLLISION ]]

            tranche_simulations.append(tranche_simulation)

            # Remove the all_agents_to_run
            agents_that_terminated_in_the_tranche = [agent for agent in tranche_simulation.agents if agent.agent_state.status not in [AgentStatus.IDLE, AgentStatus.RUNNING]]

            # TODO Define a print banner method
            msgs = list()
            msgs += [f"Agents finished in the tranche {len(agents_that_terminated_in_the_tranche)} / {len(tranche_simulation.agents)}"]
                        
            # Compute how many agents are left to run
            [ids_of_agents_to_run.remove(agent.id) for agent in agents_that_terminated_in_the_tranche if agent.id in ids_of_agents_to_run]

            msgs += [f" Remaining agents to run {len(ids_of_agents_to_run)} / {total_number_of_agents}"]

            banner = "=" * (max([len(m) for m in msgs]) + 2)
            self.msg_logger.critical("\n".join([ banner ] + msgs + [banner]))

            if len(ids_of_agents_to_run) == 0:
                break

        # Instead of merging the data of each tranch and then evaluating them once, we evaluate each of them.
        # The idea is that all the metrics are punctual, so it does not really matter as long as each observation has the correct timestamp
        return meta_data, tranche_simulations

    def execute(self, scenario: Scenario, planning_problem_set: PlanningProblemSet, simulation_id: int,
                adjust_starting_time_steps: bool=True, max_duration: Optional[int] = None) -> Tuple[Dict, List[Simulation]]:
        """
        Return the original scenario, the simulated scenario, and additional information about the AVs
        if adjust_starting_time_steps delay the execution of the agents until the start with a planning cycle!
        """

        if adjust_starting_time_steps:
            for planning_problem in planning_problem_set.planning_problem_dict.values():
                original_initial_time = planning_problem.initial_state.time_step
                adjusted_initial_time = original_initial_time
                while adjusted_initial_time % self.replanning_frequency != 0:
                    adjusted_initial_time = adjusted_initial_time + 1

                if adjusted_initial_time != original_initial_time:
                    self.msg_logger.critical(f"Adjust the starting time of agent {planning_problem.planning_problem_id} from {original_initial_time} to {adjusted_initial_time}")
                    # Can we?
                    planning_problem.initial_state.time_step = adjusted_initial_time

        # Check if agents have multiple goal states
        use_macro_agents = False
        for planning_problem in planning_problem_set.planning_problem_dict.values():
            if len(planning_problem.goal.state_list) > 1:
                self.msg_logger.critical(f"Agent {planning_problem.planning_problem_id} has multiple goals")
                use_macro_agents = True
                break

        # Automatically switch to macro agents
        # This should be refactored better!
        if use_macro_agents:
            # Ensure we use the original implementation
            self.override_config_sim["simulation"]["used_planner_interface"] = "FrenetPlannerInterface"
            # Ensure we do not use parallelism at the agent level to avoid issues in RoutePlanner that gets stuck
            self.override_config_sim["simulation"]["multiprocessing"] = False

            meta_data, tranche_simulations = self._execute_as_simulation_with_macro_agents(scenario, planning_problem_set, simulation_id, max_duration=max_duration)
        else:
            # Ensure we use the custom implementation that allows forcing x_0 and reference_path
            self.override_config_sim["simulation"]["used_planner_interface"] = "CustomFrenetPlannerInterface"
            meta_data, tranche_simulations = self._execute_as_stiched_simulation(scenario, planning_problem_set, simulation_id, max_duration=max_duration)
        
        # Merge the results into the expected format
        simulation_folder = meta_data["simulation_folder"]

        store_scenario_and_planning_problems_to_output_folder(scenario, planning_problem_set, simulation_folder)

        # TODO This is a dictionary, maybe we can store it as yaml using OmegaConfig.toYaml()
        meta_data_pickled = os.path.join(simulation_folder, "meta_data.pickled")
        with open(meta_data_pickled, "wb") as f:
            pickle.dump(meta_data, f)
        
        execution_files = []        
        if not use_macro_agents:
            # This is a tranched execution so we need to look up all the files and merge them together
            # In case of macro agents the exeucted_scenario file is already produced at the top level
            # Collect the tranches/**/executed_scenario.xml
            if os.path.exists(os.path.join(simulation_folder, "tranches")):
                tranches_folder = os.path.join(simulation_folder, "tranches")
                execution_files.extend(sorted(glob(f'{tranches_folder}/**/executed_scenario.xml', recursive=True), key= lambda f: f))
            # Merge tranche executed_scenario into a whole executed_scenario.xml
            executed_scenario: Scenario = None

            for execution_file in execution_files:
                executed_scenario_tranche, _ = XMLFileReader(execution_file).open()
                executed_scenario = merge_scenarios(executed_scenario, executed_scenario_tranche)
            
            store_executed_scenario_to_output_folder(executed_scenario, simulation_folder)

        # TODO Merge the Simulation object. Is this even necessary? for running Metrics evaluation? Can't we do that from the DB or the

        return meta_data, tranche_simulations
        


   

