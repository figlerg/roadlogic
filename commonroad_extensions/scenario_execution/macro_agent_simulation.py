
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
from cr_scenario_handler.simulation.simulation import Simulation
from cr_scenario_handler.simulation.agent_batch import AgentBatch
from cr_scenario_handler.simulation.agent import Agent
from cr_scenario_handler.utils.agent_status import TIMEOUT, AgentStatus
# TODO Replace with einlighten
# Show the progress bar
# https://stackoverflow.com/questions/3160699/python-progress-bar

import os
import time
from multiprocessing import Process, Queue, Event
from queue import Empty
from typing import Optional, List, Any

from commonroad.scenario.scenario import Scenario
from commonroad.planning.planning_problem import InitialState
from cr_scenario_handler.utils.agent_status import AgentStatus, TIMEOUT
from cr_scenario_handler.simulation.agent_batch import AgentBatch

# standard imports
import inspect
import os
import time
from copy import deepcopy

# third party
import commonroad_dc.pycrcc as pycrcc
from commonroad.planning.planning_problem import PlanningProblem

# commonroad-io
from commonroad.scenario.scenario import Scenario

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


from commonroad_extensions.scenario_execution.stitched_execution import custom_visualize_multiagent_scenario_at_timestep

from shapely.geometry import Point

import matplotlib.pyplot as plt        
import math

class MacroAgent(Agent):
    """
    This agent can replan and change its goal during the simulation.
    """

    def _setup_planning_problem(self):
        
        msg = f"Agent {self.id} setting new planning problem"
        banner = '=' * (len(msg) + 2 )
        self.msg_logger.critical("\n".join([banner, msg, banner]))
        
        initial_state = None
        precomputed_planner_interface_x_0 = None

        # Initialize Planner
        used_planner = self.config_simulation.used_planner_interface

        if self.current_goal_index == 0:
            # Base case the initial state is the one in the original planning problem
            initial_state = deepcopy(self.original_planning_problem.initial_state)
        else:
            # In-Simulation case. Take the first state of the last planned trajectory?
            # TODO This is missing the slip_angle... WHY?!
            # initial_state = deepcopy(self.vehicle_history[-1].prediction.trajectory.state_list[0])
            # initial_state = initial_state.convert_state_to_state(InitialState())
            # Extract this one before resetting the planner_interface!
            # TODO Maybe there's no need to reinstantiate it, just update it?!
            # precomputed_planner_interface_x_0 = deepcopy(self.planner_interface.record_state_list[-1])
            precomputed_planner_interface_x_0 = deepcopy(self.planner_interface.x_0)
            initial_state = precomputed_planner_interface_x_0.convert_state_to_state(InitialState())

        # Initialize Planning Problem based on the initial state and the optionally provided x_0
        if not hasattr(initial_state, 'acceleration'):
            print("Force default acceleration")
            initial_state.acceleration = 0.
        if not hasattr(initial_state, 'slip_angle') or initial_state.slip_angle is None:
            print("Force default slip angle")
            initial_state.slip_angle = 0.

        x_0 = deepcopy(initial_state)
        self.collision_objects = list()
        self._create_collision_object(x_0, initial_state.time_step)

        # Create a "local" planning problem to get to the next goal state, and use it to initialize the 
        # Planners and other components.
        sub_goal_region = GoalRegion([self.original_planning_problem.goal.state_list[self.current_goal_index]])

        self.planning_problem = PlanningProblem(self.original_planning_problem.planning_problem_id, initial_state, sub_goal_region)

        # Base initialization of the planner interface and planner
        if self.is_static_object:
            self.msg_logger.critical(f"Agent {self.id} will play STATIC OBSTACLE")
            planner_interface = [cls for _, module in inspect.getmembers(planner_interfaces, inspect.ismodule)
                                    for name, cls in inspect.getmembers(module, inspect.isclass) if
                                    issubclass(cls, PlannerInterface)
                                    and name == "StaticObstaclePlannerInterface"][0]
        else:
            try:
                planner_interface = [cls for _, module in inspect.getmembers(planner_interfaces, inspect.ismodule)
                                    for name, cls in inspect.getmembers(module, inspect.isclass) if
                                    issubclass(cls, PlannerInterface)
                                    and name == used_planner][0]
            except:
                raise ModuleNotFoundError(f"No such planner class found in planner_interfaces: {used_planner}")
        
        # This updates the reference path (as the refernce path is linked to the planner_interface.reference path!)
        self.planner_interface = planner_interface(self.id, self.config_planner, self.config, self.scenario,
                                                   self.planning_problem, self.log_path, self.mod_path)
        # TODO: Make the goal area longer
        def scale_goal_area_by(planning_problem: PlanningProblem):
            """
            Make the goal area twice as long, but keep the position of the left side as it was originally            
            """
            original_goal_state = planning_problem.goal.state_list[0]
            new_goal_state = deepcopy(original_goal_state)
            original_goal_position: Rectangle = original_goal_state.position
            origina_center = original_goal_position.center
            new_center = np.array([origina_center[0] + math.cos(original_goal_position.orientation) * original_goal_position.length / 2.0, 
                                origina_center[1] + math.sin(original_goal_position.orientation) * original_goal_position.length / 2.0])
            new_goal_position = Rectangle(length= 2.0 * original_goal_position.length, width=original_goal_position.width, orientation=original_goal_position.orientation, center=new_center)
            # copy all attributes but position
            new_goal_state.position = new_goal_position
            new_goal_region = GoalRegion([new_goal_state])
            return PlanningProblem(planning_problem.planning_problem_id, planning_problem.initial_state, new_goal_region)
        
            # def plot_me():
            #     plt.figure()

            #     xs, ys = original_goal_position.shapely_object.exterior.xy
            #     plt.plot(xs, ys, color="red")
            #     plt.plot(origina_center[0], origina_center[1], "o", color="red")

            #     xs, ys = new_goal_position.shapely_object.exterior.xy
            #     plt.plot(xs, ys, color="blue")
            #     plt.plot(new_center[0], new_center[1], "o", color="blue")

            #     plt.savefig("tmp-plot.png")

        planning_problem_with_scaled_goal_area = scale_goal_area_by(self.planning_problem)


        # Tell the agent to check completion with the new goal area
        self.agent_state = AgentState(planning_problem=planning_problem_with_scaled_goal_area, reference_path=self.reference_path,
                                      coordinate_system=self.coordinate_system)
        
        

        if self.planning_problem.initial_state.time_step == 0:
            self.agent_state.log_running(0)

        # Update the internal states if necessary
        if self.current_goal_index > 0:
            print(f"Forcing precomputed planner state {precomputed_planner_interface_x_0}")

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


    def __init__(self, agent_id: int, planning_problem: PlanningProblem,
                 scenario: Scenario, config_planner, config_sim, msg_logger, log_path: str, mod_path: str):

        # Agent id, equals the id of the dummy obstacle
        self.dt = scenario.dt
        self.id = agent_id

        # The original plannign problem may contain multiple goal states
        self.original_planning_problem = planning_problem
      
        # Remeber which goal the agent is currently trying to achieve
        self.current_goal_index = 0

        self.msg_logger = msg_logger

        self.is_static_object = False

        for index, goal_state in enumerate(self.original_planning_problem.goal.state_list):
            distance_to_goal = Point(planning_problem.initial_state.position).distance(Point(goal_state.position.center))
            self.msg_logger.critical(f"Agent {self.id} must reach goal {index} within time {goal_state.time_step.start} and {goal_state.time_step.end} at distance {distance_to_goal}")
            # TODO An vehicle can be static only for a period/goal. But for the moment, it's ALL OR NOTHING!
            self.is_static_object = distance_to_goal <= 1e-2



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
        self.max_time_steps_scenario = int(multiplier * self.original_planning_problem.goal.state_list[-1].time_step.end)
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

        # Agent removes itself from the global scenario
        self.scenario = hf.scenario_without_obstacle_id(scenario=deepcopy(scenario), obs_ids=[self.id])

        self.prediction_disabled = hasattr(self.config_planner, "perception") and self.id in self.config_planner.perception.disabled
        if self.prediction_disabled:
            self.msg_logger.critical(f"Agent {self.id} will NOT use perception")
            self.scenario = hf.scenario_without_obstacle_id(self.scenario, obs_ids=[obstacle.obstacle_id for obstacle in self.scenario.obstacles])


        # TODO CR-Reach/Spot/ Occlusion / Sensor

        self.planning_times = list()

        self.predictions = None
        self.visible_area = None

        # Make this parametric?
        # initial_state = planning_problem.initial_state
        # goal_state = planning_problem.goal.state_list[self.current_goal_index]
        # x_0 = None

        self._all_trajectories = None

        self._setup_planning_problem()

    def update_agent(self, scenario: Scenario, time_step: int, global_predictions: dict,
                     collision: bool = False):
        """ 
        Ensure to remove all the obstacles from the scenario if needed before moving on and disable the prediction for this agent
        """
        if self.prediction_disabled:
            self.scenario = hf.scenario_without_obstacle_id(scenario=deepcopy(scenario), obs_ids=[obstacle.obstacle_id for obstacle in self.scenario.obstacles if obstacle.obstacle_id != self.id])
            global_predictions = {}

        super().update_agent(self.scenario, time_step, global_predictions, collision)

    def step_agent(self, time_step):
        """ Execute one planning step.

        """
        # Check for collisions in previous timestep
        if self.agent_state.status == AgentStatus.COLLISION:
            self.msg_logger.critical(f"Timestep {time_step} Agent {self.id} collided")
            self.planning_times.append(0)
            if self.config.evaluation.collision_report:
                coll_report(self.vehicle_history, self.planner_interface.planner, self.scenario, self.planning_problem,
                            self.agent_state.last_timestep, self.config, self.log_path)
            self.postprocessing()

        elif time_step > self.max_time_steps_scenario:
            self.msg_logger.critical(f"Timestep {time_step} Agent {self.id} reached max_time_steps {self.max_time_steps_scenario}")
            self.planning_times.append(0)
            self.agent_state.log_timelimit(time_step)
            self.postprocessing()

        elif (self.planner_interface.planner.x_cl[0][0] -
              self.planner_interface.planner.x_0.velocity * self.scenario.dt >
              self.agent_state.goal_checker.last_goal_position):
            self.msg_logger.critical(f"Timestep {time_step} Agent {self.id} has passed the goal position {self.agent_state.goal_checker.last_goal_position}")
            self.agent_state.log_max_s_position(time_step)
            self.planning_times.append(0)
            self.postprocessing()

        else:
            # check for completion of this agent current goal !
            # TODO: This sets the agent_state properties: self.running, self.status, self.goal_checker_status, self.message 
            #   and possibly other properties of other objects!
            self.agent_state.check_goal_reached(self.record_state_list, self.planner_interface.planner.x_cl)

            if self.agent_state.status is not AgentStatus.RUNNING:
                self.msg_logger.critical(f"Completed goal {self.current_goal_index} out of {len(self.original_planning_problem.goal.state_list) - 1} ")

            # Was this the last goal, then exit
            if self.agent_state.status is not AgentStatus.RUNNING and self.current_goal_index == len(self.original_planning_problem.goal.state_list) - 1:
                # This was the LAST goal to reach, we finished the job!
                self.msg_logger.critical(f"Completed all goals!")
                self.planning_times.append(0)
                self.agent_state.log_finished(time_step)
                self.postprocessing()
                # Exit this method
                return
            else:
                if self.agent_state.status is not AgentStatus.RUNNING and self.current_goal_index < len(self.original_planning_problem.goal.state_list) - 1:
                    # We reconfigure the agent to follow the next goal insted  and planning again
                    # This is what matters, all the other states are stored withing the planner, planner interface, and agent
                    self.current_goal_index += 1
                    self.msg_logger.critical(f"Moving on to the next goal {self.current_goal_index}")
                    self._setup_planning_problem()
                # else:
                #  usual behavior

                self.msg_logger.info(f"Agent {self.id} current time step: {time_step}")

                # **************************
                # Cycle Occlusion Module
                # **************************
                # if config.occlusion.use_occlusion_module:
                #     occlusion_module.step(predictions=predictions, x_0=planner.x_0, x_cl=planner.x_cl)
                #     predictions = occlusion_module.predictions

                # **************************
                # Set Planner Subscriptions
                # **************************
                self.planner_interface.update_planner(self.scenario, self.predictions)

                # **************************
                # Execute Planner
                # **************************
                comp_time_start = time.time()
                trajectory, replanning_counter = self.planner_interface.step_interface(time_step)
                comp_time_end = time.time()
                # END TIMER
                self.planning_times.append(comp_time_end - comp_time_start)
                self.msg_logger.info(f"Agent {self.id}: Total Planning Time: \t\t{self.planning_times[-1]:.5f} s")

                if trajectory:

                    self._create_collision_object(self.vehicle_history[-1].initial_state,
                                                  self.vehicle_history[-1].initial_state.time_step)
                    self.agent_state.log_running(time_step)

                    # plot own view on scenario
                    if (self.save_plot or self.show_plot or self.gif or ((self.config_visu.save_plots or
                                                                          self.config_visu.show_plots) and
                                                                         not self.config.simulation.use_multiagent)):
                        visualize_agent_at_timestep(self.scenario, self.planning_problem,
                                                    self.vehicle_history[-1], time_step,
                                                    self.config, self.log_path,
                                                    traj_set=self.all_trajectories,
                                                    optimal_traj=self.planner_interface.trajectory_pair[0],
                                                    ref_path=self.planner_interface.reference_path,
                                                    predictions=self.predictions,
                                                    visible_area=self.visible_area,
                                                    plot_window=self.config_visu.plot_window_dyn,
                                                    behavior_module_state=self.planner_interface.behavior_module_state,
                                                    save=self.save_plot,
                                                    show=self.show_plot, gif=self.gif,
                                                    replanning_counter=replanning_counter)

                else:
                    self.msg_logger.critical(
                        f"Agent {self.id}: No Kinematic Feasible and Optimal Trajectory Available!")
                    self.agent_state.log_error(time_step)
                    self.postprocessing()


class MacroAgentBatch(AgentBatch):

    def _update_batch(self):
        # We do not track scores here
        for agent in reversed(self.running_agent_list):
            if agent.status > AgentStatus.RUNNING:
                self.terminated_agent_list.append(agent)
                self.running_agent_list.remove(agent)
                # with (open(os.path.join(self.mod_path, "logs", "score_overview.csv"), 'a') as file):
                #     msg = "Success" if agent.status == AgentStatus.COMPLETED_SUCCESS else "Failed"
                #     line = str(agent.scenario.scenario_id) + ";" + str(agent.id) + ";" + str(agent.current_timestep) + ";" + \
                #            str(agent.status) + ";" + str(agent.agent_state.message) + ";" + msg + "\n"
                #     file.write(line)

            self.out_queue_dict[agent.id] = {"agent_state": agent.agent_state,
                                             "collision_objects": agent.collision_objects[-1],
                                             "vehicle_history": agent.vehicle_history[-1],
                                             "record_state_list": agent.record_state_list[-1],
                                             "record_input_list": agent.record_input_list[-1],
                                             "planning_times": agent.planning_times[-1],
                                             }


class MacroAgentSimulation(Simulation):
    # TODO IMplemente stop_simulation_after_simulation_steps=stop_simulation_after_simulation_steps !!
    """
    Use MacroAgent for simulating
    """
    def _create_agent_batches(self, config_planner):
        
        """ Ensure we use the MacroAgents here"""

        batch_list: List[AgentBatch] = []

        agents = []
        agent_ids = self.agent_id_list
        to_be_removed = []
        for agent_id in agent_ids:
            try:
                # Precompute the reference paths for each goal and possibly a different configuration for each 
                agents.append(MacroAgent(agent_id, self.planning_problem_set.find_planning_problem_by_id(agent_id),
                                    self.scenario, config_planner, self.config, self.msg_logger, self.log_path,
                                    self.mod_path))

            except Exception as e:
                # catch if agents can be created eg check if valid ref-path is available
                error_traceback = traceback.format_exc()
                to_be_removed.append(agent_id)
                self.msg_logger.critical(f"Ignore Agent {agent_id} because of error: \n {str(e)}: {error_traceback}")
                logfile = os.path.join(os.path.dirname(self.log_path), "log_failures_agents.csv")
                with open(logfile, 'a', newline='') as f:
                    writer = csv.writer(f)
                    current_time = datetime.now().strftime('%H:%M:%S')
                    # Check if simulation is not None before trying to access current_timestep
                    current_timestep = "0"
                    writer.writerow(["Scenario Name: " + str(self.scenario.scenario_id) + " ; " +
                                     "Error time: " + str(current_time) + " ; " +
                                     "In Scenario Timestep: " + current_timestep + " ; " +
                                     "Agent: " + str(agent_id) + " ; " +
                                     "CODE ERROR: " + str(e) + error_traceback + "\n\n" +
                                     "CONTINUE SIMULATION WITHOUT THIS AGENT!"])
        for agent_id in to_be_removed:
            self.agent_id_list.remove(agent_id)

        if not self._multiproc or self._num_procs < 3 \
                or len(self.agent_id_list) < 2:

            # Multiprocessing disabled or useless, run single process
            # Use our custom implementation that does not track score_overview
            batch_list.append(MacroAgentBatch(agents, self.global_timestep, self.msg_logger, self.log_path, self.mod_path))

        else:
            # We need at least one agent per batch, and one process for the main simulation

            chunk_size = ceil(len(self.agent_id_list) / (self._num_procs))
            chunks = [agents[ii * chunk_size:
                             min(len(agents), (ii + 1) * chunk_size)] for ii in
                      range(0, self._num_procs)]
            for i, chunk in enumerate(chunks):
                if not chunk:
                    # no empty chucks allowed
                    continue
                inqueue = Queue()
                outqueue = Queue()
                # Use our custom implementation that does not track score_overview
                batch_list.append(MacroAgentBatch(chunk, self.global_timestep, self.msg_logger, self.log_path, self.mod_path,
                                             outqueue, inqueue, self.event))

        return batch_list, agents

    def __init__(self, config_sim, config_planner):
        # TODO: Does this really implement something different than the base class? CHECK!

        # Configuration
        init_time_start = time.perf_counter()

        self.config = config_sim
        self.config_planner = config_planner
        self.config_simulation = config_sim.simulation
        self.config_visu = config_sim.visualization
        self.config_eval = None

        self.event = Event()

        self.mod_path = self.config_simulation.mod_path
        self.log_path = self.config_simulation.log_path

        self._multiproc = self.config_simulation.multiprocessing
        # use specified number of processors, else use all physical cores (-1 bc of the main process)
        self._num_procs = self.config_simulation.num_procs if not self.config_simulation.num_procs == -1 else (
                psutil.cpu_count(logical=False) - 1)

        # initialize simulation logger
        self.msg_logger = multi_agent_log.logger_initialization(config_sim, self.log_path, "Simulation_logger")
        self.msg_logger.critical("Simulating Scenario: " + self.log_path.split("/")[-1])
        self.sim_logger = multi_agent_log.SimulationLogger(self.config)

        # Create and preprocess the scenario, create planning problems and find agent-IDs
        self.global_timestep = -1
        self.replanning_counter = 0
        scenario, self.planning_problem_set = self._open_scenario()
        self.original_agent_id = list(self.planning_problem_set.planning_problem_dict.keys())
        
        # Do not create agents from obstacles (this is a change, but not that relevant)
        if self.config_simulation.use_multiagent:
            self.msg_logger.critical("Do not create planning problems from obstacles!")

        # Get all agents IDs
        self.agent_id_list = list(self.planning_problem_set.planning_problem_dict.keys())

        self.scenario = self._preprocess_scenario(scenario)

        # Additional external Modules
        self._predictor = None
        self._occlusion = None
        self._reach_set = None

        # load additional external modules
        self._load_external_modules()

        # create list with agent batches for parallel batch-wise processing
        self.batch_list, self.agents = self._create_agent_batches(config_planner)

        # prepare global collision checker
        self._cc_dyn = None
        self._cc_stat = None
        self._set_collision_check()

        # initialize prediction horizon and horizon
        self.global_predictions = None
        # get prediction horizon if specified in planner-configuration, else use 2 seconds by default
        self.prediction_horizon = config_planner.planning.planning_horizon if (hasattr(config_planner, "planning")
                                                                               and hasattr(config_planner.planning,
                                                                                           "planning_horizon")) else 2

        self.process_times = dict()

        if self.config.evaluation.evaluate_simulation or self.config.evaluation.evaluate_runtime:
            # if logging is activated log meta data of simulation
            self.sim_logger.log_meta(agent_ids=self.agent_id_list,
                                     original_planning_problem_id=self.original_agent_id,
                                     batch_names={batch.name: batch.agent_ids for batch in self.batch_list},
                                     duration_init=time.perf_counter() - init_time_start,
                                     config_sim=self.config,
                                     config_planner=config_planner)
            
        self.initial_time_step = min([planning_problem.initial_state.time_step for planning_problem in self.planning_problem_set.planning_problem_dict.values()])
        self.expected_last_time_step = max([goal_state.time_step.end for planning_problem in self.planning_problem_set.planning_problem_dict.values() for goal_state in planning_problem.goal.state_list])

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

    def run_simulation(self, stop_simulation_after_simulation_steps : Optional[int] = None):
        """ 
        Extends the basic behavior by optionally forcing to stop the simulation after some time
        TODO For the agents to resume ensure that reference path is given and state is maintained if COLLISION 
        """

        if stop_simulation_after_simulation_steps:
            new_expected_duration = self.initial_time_step + stop_simulation_after_simulation_steps
            self.msg_logger.critical(f"Forcing to stopping the simulation at {new_expected_duration}. {stop_simulation_after_simulation_steps} steps after {self.initial_time_step}")
            # self.expected_last_time_step = min(self.expected_last_time_step, new_expected_duration)
            # If we specify a duration, we try to enforce it.
            self.expected_last_time_step = new_expected_duration
            self.msg_logger.critical(f"New expected simulation duration is {self.expected_last_time_step}")

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