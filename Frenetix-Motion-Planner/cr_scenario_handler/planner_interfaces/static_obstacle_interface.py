__author__ = "Alessio Gambi"
__copyright__ = "AIT"
__version__ = "1.0"
__maintainer__ = "Alessio Gambi"
__email__ = "alessio.gambi@ait.ac.at"
__status__ = "Beta"

from copy import deepcopy
import numpy as np

from commonroad.geometry.shape import Rectangle
from commonroad.planning.planning_problem import PlanningProblem
from commonroad.scenario.obstacle import DynamicObstacle, ObstacleType
from commonroad.scenario.scenario import Scenario
import commonroad_route_planner.fast_api.fast_api as fast_api

import cr_scenario_handler.utils.multiagent_logging as lh
from behavior_planner.behavior_module import BehaviorModule
# from cr_scenario_handler.planner_interfaces.planner_interface import PlannerInterface
from cr_scenario_handler.planner_interfaces.frenet_interface import FrenetPlannerInterface

import cr_scenario_handler.utils.goalcheck as gc
from cr_scenario_handler.utils.utils_coordinate_system import smooth_ref_path, extend_ref_path_both_ends
from cr_scenario_handler.utils.velocity_planner import VelocityPlanner

from frenetix_motion_planner.reactive_planner import ReactivePlannerPython
from frenetix_motion_planner.reactive_planner_cpp import ReactivePlannerCpp
from frenetix_motion_planner.state import ReactivePlannerState

class StopVelocityPlanner(VelocityPlanner):
    def __init__(self, scenario, planning_problem, coordinate_system):
        self.scenario = scenario
        self.planning_problem = planning_problem
        self.DT = scenario.dt
        self.coordinate_system = coordinate_system
        
        # Do not move!
        self.default_goal_velocity = 0.0
        # Do not really care!
        self.used_goal_metric, self.goal_s_position, self.goal_centers, self.goal_shape = self._determine_goal_metrics(scenario,
                                                                                                      planning_problem)
                             
    def _determine_goal_metrics(self, scenario, planning_problem):
        """Determine the goal metrics based on planning problem attributes."""
        goal_metric = None
        goal_centers = []
        goal_s_position = None
        goal_shape = None

        return goal_metric, goal_s_position, goal_centers, goal_shape

    def set_new_scenario_and_planning_problem(self, scenario, planning_problem, coordinate_system):
        # Reinitializing with new scenario and planning problem
        self.__init__(scenario, planning_problem, coordinate_system)

    
    def calculate_desired_velocity(self, x_0, s_position) -> float:
        return 0.0

    def calc_remaining_time_steps(self, ego_state_time: float, t: float) -> int:
        """
        TODO Is this even used?!
        Calculate the minimum and maximum amount of remaining time steps.

        Args:
            ego_state_time (float): Current time of the state of the ego vehicle.
            t (float): Checked time.

        Returns:
            Tuple[int, int]: Minimum and maximum remaining time steps.
        """
        considered_time_step = int(ego_state_time + t / self.DT)
        if hasattr(self.planning_problem.goal.state_list[0], "time_step"):
            min_remaining_time = self.planning_problem.goal.state_list[0].time_step.start - considered_time_step
            max_remaining_time = self.planning_problem.goal.state_list[0].time_step.end - considered_time_step
            return int((max_remaining_time+min_remaining_time)/2)

class StaticObstaclePlannerInterface(FrenetPlannerInterface):

    """
    A planner that does not plan anything and never reaches the goal, thus keeping the vehicle where it is with 
    always the same attributes.
    """

    def __init__(self, agent_id: int, config_planner, config_sim, scenario: Scenario,
                 planning_problem: PlanningProblem, log_path: str, mod_path: str):

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
        self.msg_logger = lh.logger_initialization(self.config_plan, log_path, "Message_logger_" + str(self.id))
        self.msg_logger.critical("Vehicle ID: " + str(self.id) + " is a STATIC OBSTACLE")
        # Init and Goal State

        # Initialize planner - This will plan, but we will never implement its planning
        self.planner =  ReactivePlannerCpp(self.config_plan, self.config_sim, scenario, planning_problem, log_path, mod_path, self.msg_logger) \
            if self.config_plan.debug.use_cpp else \
              ReactivePlannerPython(self.config_plan, self.config_sim, scenario, planning_problem, log_path, mod_path, self.msg_logger)

        problem_init_state = planning_problem.initial_state

        # Set all the attributes to zero!
        problem_init_state.acceleration = 0.0
        problem_init_state.velocity = 0.0
        problem_init_state.slip_angle = 0.0
        problem_init_state.yaw_rate = 0.0

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

        # Keep this for backward compatibility
        # self.route_planner = RoutePlanner(lanelet_network=scenario.lanelet_network,
        #                                       planning_problem=planning_problem,
        #                                       scenario=scenario,
        #                                       extended_search=False)
        # shortest_route = self.route_planner.plan_routes().retrieve_shortest_route(retrieve_shortest=True)
        # reference_path = extend_ref_path_both_ends(shortest_route.reference_path)
        reference_path = fast_api.generate_reference_path_from_lanelet_network_and_planning_problem(lanelet_network=scenario.lanelet_network, planning_problem=planning_problem)
        self.reference_path = smooth_ref_path(reference_path.reference_path)

        self.goal_area = gc.get_goal_area_shape_group(planning_problem=planning_problem, scenario=scenario)

        # **************************
        # Set External Planner Setups
        # **************************
        self.planner.update_externals(x_0=self.x_0, reference_path=self.reference_path, goal_area=self.goal_area,
                                      occlusion_module=self.occlusion_module)
        self.x_cl = self.planner.x_cl

        # ***************************
        # Make sure the Velocity Planner always plan to stop!
        # ***************************
        self.velocity_planner = StopVelocityPlanner(scenario=scenario, planning_problem=planning_problem,
                                                coordinate_system=self.coordinate_system)