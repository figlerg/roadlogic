from typing import List

from commonroad.common.file_reader import CommonRoadFileReader
import numpy as np
import pandas as pd

import sys
import os

import itertools

# from osc2scenic.create_scenarios.draw import draw
# from plans.load_plans import df, df_by_time  # I use dataframes for now
from cr_scenario_handler.utils.utils_coordinate_system import CoordinateSystem
from types import SimpleNamespace
from commonroad.scenario.lanelet import LaneletNetwork
from commonroad.scenario.scenario import Scenario
from commonroad.common.util import Interval, AngleInterval

from commonroad.common.file_writer import CommonRoadFileWriter, OverwriteExistingFile
from commonroad.scenario.state import ExtendedPMState, InitialState, PMState, TraceState
from commonroad.geometry.shape import Rectangle
from commonroad.planning.goal import GoalRegion
from commonroad.planning.planning_problem import PlanningProblem, PlanningProblemSet
from commonroad.visualization.mp_renderer import MPRenderer
from commonroad.scenario.obstacle import DynamicObstacle, ObstacleType

from commonroad_extensions.plan_execution.project_to_polyline import project_to_polyline

from commonroad_extensions.plan_execution.id_hash import encode, decode

import os




from planning.asp.MyModel import MyModel

from vehiclemodels.vehicle_parameters import setup_vehicle_parameters
from commonroad.prediction.prediction import Trajectory, TrajectoryPrediction
from copy import deepcopy
import math

from commonroad_dc.feasibility.vehicle_dynamics import VehicleDynamics
from commonroad.common.solution import VehicleType
import commonroad_dc.feasibility.feasibility_checker as feasibility_checker
from commonroad.prediction.prediction import Trajectory
from typing import List, Dict, Tuple, Optional
from commonroad_extensions.common.collisions_checking import check_road_compliance, check_collisions_with_obstacles

import warnings


# TODO this is a constant here, specifically for the test maps.
padding_distance_left = 10  # start a bit inside the road. Note: I also made the road longer to the left, so it starts at s=0
warnings.warn(f"Padding distance of size {padding_distance_left} enabled (road is extended on the left). This is reflected in the monitors. It should be revisited once we move on from our test maps.")

no_lanes = 3
warnings.warn("The mapping from asp-model to planning problem is unfinished: It currently expects exactly three lanes. TODO enable a check which only maps to existing lanes.")

# ad 2

# create a dummy variable so it doesn't scream AttributeError
dummy_config_sim = SimpleNamespace(
    visualization=SimpleNamespace(ref_path_debug=False)
)

def get_orientation_from_xy(xy: np.ndarray, coordinate_system: CoordinateSystem) -> float:
    s, _ = coordinate_system.convert_to_curvilinear_coords(xy[0], xy[1])
    idx = np.argmin(np.abs(coordinate_system.ref_pos - s))
    return coordinate_system.ref_theta[idx]


def map_plan(scenario:Scenario, plan_model:MyModel, anchor_lane_idx:int, save_path = None, config_sim=dummy_config_sim):

    predicates = plan_model.holds  # get only holds predicates

    # make dict out of it TODO these models and predicates are atrocious. This should be something like nameddicts
    structured = [
        {  # something like state(ego,loc(0,0),dyn(1,0))
            "agent": pred[0][0].name,
            "lon_pos": pred[0][1][0],
            "lat_pos": pred[0][1][1],
            "lon_vel": pred[0][2][0],
            "lat_vel": pred[0][2][1],
            "t": pred[1]
        }
        for pred in predicates
    ]

    # sort by time TODO I could do this without pandas, lazyness
    df = pd.DataFrame(structured)
    df_by_time = {t: group.drop(columns='t').set_index('agent') for t, group in df.groupby('t')}

    # Assert that no actor appears more than once at the same time step
    duplicates = df.duplicated(subset=["t", "agent"], keep=False)
    assert not duplicates.any(), (
        "Multiple positions for the same actor at the same time step:\n"
        f"{df.loc[duplicates, ['t', 'agent', 'lon_pos', 'lat_pos']]}"
    )


    agent_ids = df_by_time.get(0).index
    max_t = max(df_by_time.keys())


    lane_centerlines = {lane.lanelet_id:lane.center_vertices for lane in scenario.lanelet_network.lanelets}  # need a way to group the lanelets that a lane consists of

    anchor_lane = lane_centerlines[anchor_lane_idx]

    coordinate_system = CoordinateSystem(reference=anchor_lane, config_sim=config_sim)
    
    goals_sat_set = [pred for pred in plan_model if pred.name == 'goal']  # check at which times the goals are satisfied. this predicate holds the times where each of the subgoals is satisfied. 

    mode = 'optimize_longitudinal_distance'

    match mode:
        case 'first':
            # this is the barebones, just pick the first goals predicate that we find
    
            goals_sat = goals_sat_set[0]  # the original trivial way of doing it
            
            goal_times = list(dict.fromkeys(goals_sat[:]))
            if not (0 in goal_times):
                goal_times.insert(0,0)

        case 'optimize_longitudinal_distance':
            # now trying to find the optimal set of times by comparing all the goals predicates
            goals_sat = goals_sat_set[0] 


            get_goal_times = lambda goal : list(dict.fromkeys([0]+goal[:]))

            goal_times_set = [get_goal_times(x) for x in goals_sat_set]

            def compute_min_longitudinal_change_distance(goal_times):
                # we want to select one of the goal predicates that makes things easier to drive for the controller. 
                # this function takes a candidate and returns the minimum lane change distance, i.e. the sharpest turn

                lane_change_distance = float('inf')

                last_t = 0

                for t in goal_times:

                    if not t:
                        continue
                    
                    # current_pos_all = df_by_time[t]
                    # last_pos_all = df_by_time[last_t]

                    # compare for all actors
                    for actor in agent_ids:
                        last_lon, last_lat = df_by_time[last_t].loc[actor, ["lon_pos", "lat_pos"]]
                        lon, lat = df_by_time[t].loc[actor, ["lon_pos", "lat_pos"]]
                        
                        # print(lat-last_lat)
                        # print(lon-last_lon)

                        # we only care for lane changes (first condition) and then we update only if we find a sharper turn
                        dist = abs(lon-last_lon)
                        if lat-last_lat and dist < lane_change_distance:
                            lane_change_distance = dist
                    
                    last_t = t

                return lane_change_distance

            # now we select the goals predicate with the least sharp turn (maximum such distance) from among all candidates
            goal_times = max(goal_times_set, key=compute_min_longitudinal_change_distance)


    time_steps = goal_times  # just for clarity: one could also use different time steps

    # time_steps = list(range(max_t+1)) # TODO interesting. what would happen if we had better plans and chose all goals here?
    
    # print(time_steps)

    # print(df)
    # print(df_by_time)
    # I identify those times where a lane change has happened. This is to not overconstrain the planner. 
    # time_steps = [t + 1 for t in sorted(df[df["lat_vel"] != 0]["t"].unique())]
    # print(time_steps)

    # Collect planning problems by agent
    new_planning_problems = []

    for agent_id in agent_ids:
        goal_states = []
        initial_state = None
        for t in time_steps:
            frame = df_by_time.get(t)
            if agent_id not in frame.index:
                continue

            row = frame.loc[agent_id]
            lon_pos, lat_pos = row["lon_pos"], row["lat_pos"]
            assert np.isscalar(lon_pos) and np.isscalar(lat_pos), f"Non-scalar positions: lon={type(lon_pos)}, lat={type(lat_pos)}"

                    

            # # if it is out of map by a bit everything fails
            # if lon_pos ==0:
            #     lon_pos +=0.01

            # Each vehicle has a dimension, we need to ensure that the safety distance is computed correctly



            import warnings
            warnings.warn("The mapping from asp-model to planning problem is unfinished: It currently expects exactly three lanes. TODO enable a check which only maps to existing lanes.")

            xy_lon = coordinate_system.convert_to_cartesian_coords(lon_pos + padding_distance_left,0)
            (x, y), _ = project_to_polyline(xy_lon, lane_centerlines[lat_pos+2])  # +2 because we convert -1,0.1 to 1,2,3. (lanes are numbered from left to right)

            orientation = get_orientation_from_xy((x,y),coordinate_system)

            if t == 0:
                initial_state = InitialState(time_step=0, position=np.asarray([x, y]), velocity=0.0, acceleration=0.0, yaw_rate=0.0, slip_angle=0.0, orientation=orientation)
            else:
                time_unit = 10
                time_interval = (t*time_unit, t*time_unit + time_unit)  # +-1 second = +-10 time steps
                # rect = Rectangle(.5, .5, np.array([x, y]),orientation)  # planner cannot do these!
                # rect = Rectangle(3., 2., np.array([x, y]),orientation)  # work, but may mess with timing because too long
                rect = Rectangle(1., 2., np.array([x, y]),orientation)  # work, but may mess with timing because too long

                # goal_state_3 = ExtendedPMState(time_step=I3, position=R3, velocity=V3)
                goal_state = ExtendedPMState(time_step=Interval(*time_interval), position=rect, velocity=None)
                goal_states.append(goal_state)

        if initial_state is not None and goal_states:
            # new_planning_problem_2 = PlanningProblem(43,x0_2,GoalRegion([goal_state_1_2,goal_state_2_2,goal_state_3_2]))
            goal_region = GoalRegion(goal_states)
            pp = PlanningProblem(encode(agent_id), initial_state, goal_region)
            new_planning_problems.append(pp)

    # Replace planning problem set
    new_planning_problem_set = PlanningProblemSet(new_planning_problems)


    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fw = CommonRoadFileWriter(scenario, new_planning_problem_set, "Felix Gigler", "AIT")
        fw.write_to_file(save_path, OverwriteExistingFile.ALWAYS)


    return new_planning_problem_set




    # segment = 30
    # lane = -1  # 1 to right

    # lanes = {-1:left_lane, 0:anchor_lane, 1:right_lane}



    # long_xy = coordinate_system.convert_to_cartesian_coords(segment,0)
    # xy, idx = project_to_polyline(long_xy, lanes[lane])

    # for pp in planning_problem_set.planning_problem_dict.values():
    #     goal = pp.goal.state_list[0]
    #     if goal.position:
    #         goal.position.center = xy

    # draw(scenario, planning_problem_set)


def get_position_and_orientation_at_time(agent_id, df_by_time,coordinate_system,lane_centerlines,anchor_lane_idx, t):
    frame = df_by_time.get(t)
    
    if agent_id not in frame.index:
        return None

    row = frame.loc[agent_id]
    lon_pos, lat_pos = row["lon_pos"], row["lat_pos"]

    # if it is out of map by a bit everything fails
    if lon_pos ==0:
        lon_pos +=0.01

    safety_distance = 10  # start a bit inside the road. Note: I instead made the road longer


    xy_lon = coordinate_system.convert_to_cartesian_coords(lon_pos+safety_distance,0)
    
    # print(f"{t} - {xy_lon}")

    (x, y), _ = project_to_polyline(xy_lon, lane_centerlines[lat_pos+anchor_lane_idx])
    # The downstream validation cannot handle the fact that np.
    orientation = float(get_orientation_from_xy((x,y),coordinate_system))

    return (x, y), orientation


def get_covered_cell(plan_model: MyModel, up_to_time: Optional[float], per_agent=False):
    # Transform the planning in a list of DynamicObstacles with trajectories
    predicates = plan_model.holds  # get only holds predicates

    # make dict out of it TODO these models and predicates are atrocious. This should be something like nameddicts
    structured = [
        {  # something like state(ego,loc(0,0),dyn(1,0))
            "agent": pred[0][0].name,
            "lon_pos": pred[0][1][0],
            "lat_pos": pred[0][1][1],
            "lon_vel": pred[0][2][0],
            "lat_vel": pred[0][2][1],
            "t": pred[1]
        }
        for pred in predicates
    ]

    # sort by time TODO I could do this without pandas, lazyness
    df = pd.DataFrame(structured)

    # up_to_time
    if up_to_time is not None:
        # Filter data by time
        df = df[df["t"] <= up_to_time]

    per_agent_covered_cell = dict()
    for agent in df["agent"].unique().tolist():
        # Get consecutive states
        observations = list(df[ df["agent"] == agent].sort_values(["t"])[["lon_pos", "lat_pos"]].itertuples(index=False, name=None))
        interpolated_observations = set()
        [interpolated_observations.add(o) for o in observations]
        # In case there is more than one observation, we can interpolate them
        # TODO Consider to use the trajectory interpolation we use elsewhere (feasibility checking)
        for (lon_pos, lane_number), (lon_pos_2, lane_number_2) in zip(observations[:-1], observations[1:]):
            # Interpolate the states longitudinally
            long_states = list(range(lon_pos, lon_pos_2+1))
            mid_point = int(len(long_states)/2)
            # Split in half
            lane_numbers = [lane_number for s in long_states[:mid_point]] + [lane_number_2 for s in long_states[mid_point:]]
            
            assert len(long_states) == len(lane_numbers), "Something wrong with the interpolation"

            [interpolated_observations.add((long, lat)) for long, lat in zip(long_states, lane_numbers) if (long, lat) not in interpolated_observations]
        
        # Here's we have the agent covered cell
        per_agent_covered_cell[agent] = interpolated_observations
    
    if per_agent:
        return per_agent_covered_cell
    else:
        # Merge them together
        union_of_cells = set()
        for agent_cell in per_agent_covered_cell.values():
            union_of_cells = union_of_cells.union(set(agent_cell))

        return union_of_cells


def compute_pairwise_similarity(plan_model_a: MyModel, plan_model_b: MyModel) -> float:
    """
    Compute similarity between plans as Intersection over Union of cells covered by the agents in the scenario
    """
    cell_covered_in_plan_a = get_covered_cell(plan_model_a)
    cell_covered_in_plan_b = get_covered_cell(plan_model_b)

    # Compute the interesection over the union
    intersection_of_cells = cell_covered_in_plan_a.intersection(cell_covered_in_plan_b)
    union_of_cells= cell_covered_in_plan_a.union(cell_covered_in_plan_b)

    return float(len(intersection_of_cells)) / float (len(union_of_cells))

def start_end_times(plan_model: MyModel) -> Tuple[float, float]:
    # Transform the planning in a list of DynamicObstacles with trajectories
    predicates = plan_model.holds  # get only holds predicates

    # make dict out of it TODO these models and predicates are atrocious. This should be something like nameddicts
    structured = [
        {  # something like state(ego,loc(0,0),dyn(1,0))
            "agent": pred[0][0].name,
            "lon_pos": pred[0][1][0],
            "lat_pos": pred[0][1][1],
            "lon_vel": pred[0][2][0],
            "lat_vel": pred[0][2][1],
            "t": pred[1]
        }
        for pred in predicates
    ]

    # sort by time TODO I could do this without pandas, lazyness
    df = pd.DataFrame(structured)
    start_time = float(df["t"].min())
    end_time = float(df["t"].max())
    
    return start_time, end_time

def compute_progressive_similarity_matrix(plan_models: List[MyModel]) -> Tuple[Dict[int, List[List[float]]], Dict[int, Dict[int, List[List[float]]]]]:
    """
    Compute the similarity matrix for each time step
    """
    progressive_similarity_matrix = dict()
    per_agent_progressive_similarity_matrix = dict()

    # Find the min and max time
    min_time = sys.maxsize
    max_time = - sys.maxsize
    for plan_model in plan_models:
        start_time, end_time = start_end_times(plan_model)
        
        start_time = int(start_time)
        end_time = int(end_time)

        min_time = min(min_time, start_time)
        max_time = max(max_time, end_time)

    for t in range(min_time, max_time + 1):
        progressive_similarity_matrix[t] = compute_similarity_matrix(plan_models, t)
        per_agent_progressive_similarity_matrix[t] = compute_per_agent_similarity_matrix(plan_models, t)

    return progressive_similarity_matrix, per_agent_progressive_similarity_matrix

def compute_per_agent_similarity_matrix(plan_models: List[MyModel], up_to_time: float) -> List[List[float]]:
    # Compute this once for all
    
    # List[Dict[agent, Set[Covered_Cells]]]
    cell_covered_in_the_plans_by_each_agent = [ get_covered_cell(plan_model, up_to_time, per_agent=True) for plan_model in plan_models ]
    
    # For each agent at each time compute the similarity
    similarity_matrix_per_agent = dict()
    for agent in cell_covered_in_the_plans_by_each_agent[0].keys():
        # Extract per agent data
        cell_covered_by_the_plans = [ cell_dict[agent] for cell_dict in cell_covered_in_the_plans_by_each_agent]

        similarity_matrix = np.ones([len(cell_covered_by_the_plans), len(cell_covered_by_the_plans)])

        for i, j in itertools.product(range(0, len(cell_covered_by_the_plans)), repeat=2):
            # Compute the interesection over the union
            cell_covered_in_plan_a = cell_covered_by_the_plans[i]
            cell_covered_in_plan_b = cell_covered_by_the_plans[j]
            intersection_of_cells = cell_covered_in_plan_a.intersection(cell_covered_in_plan_b)
            union_of_cells= cell_covered_in_plan_a.union(cell_covered_in_plan_b)
            iou = float(len(intersection_of_cells)) / float (len(union_of_cells))
            similarity_matrix[i, j] = iou
    
        similarity_matrix_per_agent[agent] = similarity_matrix
    
    return similarity_matrix_per_agent


def compute_similarity_matrix(plan_models: List[MyModel], up_to_time: float) -> List[List[float]]:
    # TODO Ensure that if a planning does not last long enough we defatul to Nan or something
    """
    Compute similarity between each pair of plans as Intersection over Union of cells covered by the agents in the scenario
    """
    # Compute this once for all
    cell_covered_by_the_plans = [ get_covered_cell(plan_model, up_to_time) for plan_model in plan_models ]

    similarity_matrix = np.ones([len(cell_covered_by_the_plans), len(cell_covered_by_the_plans)])

    for i, j in itertools.product(range(0, len(cell_covered_by_the_plans)), repeat=2):
        # Compute the interesection over the union
        cell_covered_in_plan_a = cell_covered_by_the_plans[i]
        cell_covered_in_plan_b = cell_covered_by_the_plans[j]
        intersection_of_cells = cell_covered_in_plan_a.intersection(cell_covered_in_plan_b)
        union_of_cells= cell_covered_in_plan_a.union(cell_covered_in_plan_b)
        iou = float(len(intersection_of_cells)) / float (len(union_of_cells))
        similarity_matrix[i, j] = iou
    
    return similarity_matrix


def _from_plan_to_dynamic_obstacles(scenario:Scenario, plan_model:MyModel, anchor_lane_idx:int, config_sim=dummy_config_sim):
    # This one has issues with computing velocity and the like, which we do not really need to validate the trajectory at this level
    #   as only position and time is enough!
    # Transform the planning in a list of DynamicObstacles with trajectories
    predicates = plan_model.holds  # get only holds predicates

    # make dict out of it TODO these models and predicates are atrocious. This should be something like nameddicts
    structured = [
        {  # something like state(ego,loc(0,0),dyn(1,0))
            "agent": pred[0][0].name,
            "lon_pos": pred[0][1][0],
            "lat_pos": pred[0][1][1],
            "lon_vel": pred[0][2][0],
            "lat_vel": pred[0][2][1],
            "t": pred[1]
        }
        for pred in predicates
    ]

    # sort by time TODO I could do this without pandas, lazyness
    df = pd.DataFrame(structured)
    df_by_time = {t: group.drop(columns='t').set_index('agent') for t, group in df.groupby('t')}

    max_t = max(df_by_time.keys())

    lane_centerlines = [lane.center_vertices for lane in scenario.lanelet_network.lanelets]  # need a way to group the lanelets that a lane consists of

    anchor_lane = lane_centerlines[anchor_lane_idx]

    coordinate_system = CoordinateSystem(reference=anchor_lane, config_sim=config_sim)

    # goals_sat = [pred for pred in plan_model if pred.name == 'goal'][0]  # check at which times the goals are satisfied. this predicate holds the times where each of the subgoals is satisfied. 
    # print(goals_sat)
    # time_steps = [0] + list(dict.fromkeys(goals_sat[1:])) + [max_t]  # get the unique time points. there may be duplicates because we allow that several goals are satisfied at the same time TODO should we?
    
    # Collect planning problems by agent
    obstacles = dict()
    from vehiclemodels.vehicle_parameters import setup_vehicle_parameters
    from commonroad.prediction.prediction import Trajectory, TrajectoryPrediction
    from copy import deepcopy
    import math

    for aidx, agent_id in enumerate(df_by_time.get(0).index, start=1000):
        list_of_states = list()
        list_of_velocities = list()
        
        # We need to approximate velocity so we iterate over pairs of states
        time_steps = sorted(df_by_time.keys())
        initial_state = None
        
        # Initial state - V0 = 0

        current_t = time_steps[0]
        initial_position, initial_orientation = get_position_and_orientation_at_time(agent_id, df_by_time,coordinate_system,lane_centerlines,anchor_lane_idx, current_t)
        initial_state = InitialState(time_step=current_t, position=np.array(initial_position), orientation=initial_orientation, velocity=0.0, acceleration=0.0, yaw_rate=0.0, slip_angle=0.0)
        initial_state_as_PM = PMState(time_step=current_t, position=np.array(initial_position), velocity=0.0, velocity_y=0.0)
        list_of_states.append(initial_state_as_PM)
        list_of_velocities.append(0.0)

        # Compute the other states using the classical formulae:
        # V = Vo + a*t
        # S = Vo*t + a(t*t)/2
        # What is the speed at which the vehilce travels in the second point?
        # We get the acceleration value, knowing t = 1.0
        # S = v0 + a / 2
        # 2S = 2v0 + a
        # a = 2S - 2v0
        # Knowing a and t=1.0 we can compute the speed:
        # V = v0 + (2S - 2V0) = 2S - v0

        for current_t, before_t in zip(time_steps[1:], time_steps[:-1]):
            current_position, current_orientation = get_position_and_orientation_at_time(agent_id, df_by_time,coordinate_system,lane_centerlines,anchor_lane_idx, current_t)
            before_position, _ = get_position_and_orientation_at_time(agent_id, df_by_time,coordinate_system,lane_centerlines,anchor_lane_idx, before_t)

            # Compute velocity and velocity_y
            distance_between_points_m = ( (current_position[0]-before_position[0]) ** 2 + (current_position[1]-before_position[1]) ** 2 ) ** 0.5
            # Distance on Y axis
            distance_between_points_m_y = (current_position[1]-before_position[1])
            
            # This is the average speed beetween the points and not the speed at which the car will travel in the next state
            # velocity_m_p_s = distance_between_points_m / time_between_points_s
            interpolated_orientation = math.asin(distance_between_points_m_y/distance_between_points_m)

            # V = v0 + (2S - 2V0) = 2S - v0

            v0 = list_of_velocities[-1]
            velocity_m_p_s = 2 * distance_between_points_m - v0
            
            velocity_y = math.sin(interpolated_orientation) * velocity_m_p_s
            velocity_x = math.cos(interpolated_orientation) * velocity_m_p_s

            list_of_states.append(PMState(time_step=int(current_t / scenario.dt), position=np.array(current_position), velocity=velocity_x, velocity_y=velocity_y))
            list_of_velocities.append(velocity_m_p_s)

        vehicle_parameters = setup_vehicle_parameters(vehicle_id=2)
        # shape = Rectangle(self.config.vehicle.length, self.config.vehicle.width)
        shape = Rectangle(vehicle_parameters.l, vehicle_parameters.w)
        # initial_custom_state = deepcopy(list_of_states[0])
        # This probably fails because we do not have enough data
        # initial_state = initial_state
        #
        trajectory_prediction = TrajectoryPrediction(
                Trajectory(initial_time_step=list_of_states[0].time_step, state_list=list_of_states),
                shape ) # TOOD Relevant?, center_lanelet_assignment=lanelet_assigned)
        obstacles[agent_id] = DynamicObstacle(obstacle_id=aidx, obstacle_type=ObstacleType.CAR, obstacle_shape=shape, initial_state=initial_state, prediction=trajectory_prediction)

    def debug():
        import matplotlib.pyplot as plt
        from commonroad.visualization.mp_renderer import MPDrawParams, MPRenderer
        rnd = MPRenderer()
        # set renderer draw params - This is important if there are traffic lights in the scenario
        # rnd.draw_params.time_begin = 0
        # rnd.draw_params.time_end = 300
        scenario.draw(rnd)
        for agent_id, obstacle in obstacles.items():
            obstacle: DynamicObstacle
            
            if agent_id != "ego":
                continue

            for t in [s.time_step for s in obstacle.prediction.trajectory.state_list]:
                occupancy = obstacle.occupancy_at_time(t)
                occupancy.draw(rnd)
                state = next(iter([s for s in obstacle.prediction.trajectory.state_list if s.time_step == t]))
                state.draw(rnd)
                # # Set obstacle parameters
                # obs_params = MPDrawParams()
                # obs_params.dynamic_obstacle.draw_icon = True
                # obs_params.dynamic_obstacle.show_label = False
                
                # # We need both otherwise begin and end otherwise it will not show it
                # obs_params.dynamic_obstacle.time_begin = t
                # obs_params.dynamic_obstacle.time_end = 300

                # obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.facecolor = "red" if agent_id == "ego" else "blue"
                # obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.edgecolor = "black"
                # # Ensure this is draw above everything else
                # obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.zorder = 100 + t
                # obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.opacity = 1

                # obs_params.dynamic_obstacle.draw_direction = True
                # obs_params.dynamic_obstacle.draw_signals = True
                
                # # Draw a line instead of a set of points using the same color of the vehicle
                # # Highlight better the planned trajectories (bold lines)
                # obs_params.dynamic_obstacle.trajectory.draw_trajectory = True
                # obs_params.dynamic_obstacle.trajectory.draw_continuous = True
                # obs_params.dynamic_obstacle.trajectory.facecolor = "red" if agent_id == "ego" else "blue"
                # obs_params.dynamic_obstacle.trajectory.line_width = 1.0
                # obstacle.draw(rnd, draw_params=obs_params)

        rnd.render()
        plt.show()

    # debug()

    return obstacles


def from_plan_to_dynamic_obstacles(scenario:Scenario, plan_model:MyModel, anchor_lane_idx:int, config_sim=dummy_config_sim, interpolate=False):
    """
    Return a collection of Dynamic Obstacles whose state is the one obtained by the models, i.e., position and time, interpolated linearly
    using the CommonRoad trajectory machinery
    """ 
    predicates = plan_model.holds  # get only holds predicates
    structured = [
        {  # something like state(ego,loc(0,0),dyn(1,0))
            "agent": pred[0][0].name,
            "lon_pos": pred[0][1][0],
            "lat_pos": pred[0][1][1],
            "lon_vel": pred[0][2][0],
            "lat_vel": pred[0][2][1],
            "t": pred[1]
        }
        for pred in predicates
    ]
    df = pd.DataFrame(structured)
    df_by_time = {t: group.drop(columns='t').set_index('agent') for t, group in df.groupby('t')}
    lane_centerlines = [lane.center_vertices for lane in scenario.lanelet_network.lanelets]  # need a way to group the lanelets that a lane consists of
    anchor_lane = lane_centerlines[anchor_lane_idx]
    coordinate_system = CoordinateSystem(reference=anchor_lane, config_sim=config_sim)

    # Keep track of which obstacle implements which agent
    obstacles = dict()

    for aidx, agent_id in enumerate(df_by_time.get(0).index, start=1000):
        list_of_states = list()
        time_steps = sorted(df_by_time.keys())

        # current_t is time step or seconds?
        for current_t in time_steps:
            position, orientation = get_position_and_orientation_at_time(agent_id, df_by_time,coordinate_system,lane_centerlines,anchor_lane_idx, current_t)
            # velocity -> velocity_x !
            # initial_state_as_PM = PMState(time_step=current_t, position=np.array(position), velocity=None, velocity_y=None)
            # initial_state_as_PM = ExtendedPMState(time_step=current_t, position=np.array(position), orientation=orientation)
            state_as_PM = ExtendedPMState(position=np.array(position), orientation=orientation)
            list_of_states.append(state_as_PM)

        vehicle_parameters = setup_vehicle_parameters(vehicle_id=2)
        # shape = Rectangle(self.config.vehicle.length, self.config.vehicle.width)
        shape = Rectangle(vehicle_parameters.l, vehicle_parameters.w)
        # initial_custom_state = deepcopy(list_of_states[0])
        # This probably fails because we do not have enough data
        # initial_state = initial_state
        
        initial_state = deepcopy(list_of_states[0])
        initial_state = initial_state.convert_state_to_state(InitialState())
        # Set the time_step!
        initial_state.time_step = int(min(time_steps)/scenario.dt)
        
        if interpolate:
            # Do a linear interpolation of all the attributes
            # NOTE: Because the orientation is always relative to the road, the vehicle does not "steer" but "translate"
            interpolated_trajectory = Trajectory.resample_continuous_time_state_list(
                                                       list_of_states, 
                                                       np.array([float(t) for t in time_steps]),
                                                       scenario.dt,
                                                       int(max(time_steps)/scenario.dt))

        trajectory_prediction = TrajectoryPrediction(
                interpolated_trajectory,
                # Trajectory(initial_time_step=list_of_states[0].time_step, state_list=list_of_states),
                shape ) # TOOD Relevant?, center_lanelet_assignment=lanelet_assigned)
        obstacles[agent_id] = DynamicObstacle(obstacle_id=aidx, obstacle_type=ObstacleType.CAR, obstacle_shape=shape, initial_state=initial_state, prediction=trajectory_prediction)

    return obstacles

import matplotlib.pyplot as plt
from commonroad.visualization.draw_params import ShapeParams

def plot_all(scenario_with_obstacles, output_file):
    # Plot each occupancy using different colors
    for t in [s.time_step for s in scenario_with_obstacles.obstacles[0].prediction.trajectory.state_list]:
        # I cannot see why there should be not a collision
        rnd = MPRenderer()
        # Plot the road
        scenario_with_obstacles.lanelet_network.draw(rnd)
    
        for obstacle, color in zip(scenario_with_obstacles.obstacles, ["orange", "blue"]):
            # Set obstacle parameters
            shape_params = ShapeParams()
            shape_params.facecolor = color
            shape_params.edgecolor = "#003359"
            shape_params.opacity = 0.4
            # elif isinstance(draw_params, MPDrawParams):
            # draw_params = draw_params.shape and not occupancy.shape !
            obstacle.occupancy_at_time(t).shape.draw(rnd, draw_params=shape_params)
        # Render the plot
        rnd.render()
        # Save the plot
        plt.tight_layout()
        plt.savefig(f"{output_file}_{t}.png")
        plt.close()

def plot_scenario(scenario_with_obstacles, output_file):
    # I cannot see why there should be not a collision
    rnd = MPRenderer()
    # Plot the road
    scenario_with_obstacles.lanelet_network.draw(rnd)
    # Plot each occupancy using different colors
    for t in [s.time_step for s in scenario_with_obstacles.obstacles[0].prediction.trajectory.state_list]:
        for obstacle, color in zip(scenario_with_obstacles.obstacles, ["orange", "blue"]):
            # Set obstacle parameters
            shape_params = ShapeParams()
            shape_params.facecolor = color
            shape_params.edgecolor = "#003359"
            shape_params.opacity = 0.4
            # elif isinstance(draw_params, MPDrawParams):
            # draw_params = draw_params.shape and not occupancy.shape !
            obstacle.occupancy_at_time(t).shape.draw(rnd, draw_params=shape_params)
    # Render the plot
    rnd.render()
    # Save the plot
    plt.tight_layout()
    plt.savefig(output_file)

def plot_collision(scenario_with_obstacles, output_file, time_of_collision):
    # I cannot see why there should be not a collision
    rnd = MPRenderer()
    # Plot the road
    scenario_with_obstacles.lanelet_network.draw(rnd)
    # Plot each occupancy using different colors
    for t in [s.time_step for s in scenario_with_obstacles.obstacles[0].prediction.trajectory.state_list]:
        for obstacle, color in zip(scenario_with_obstacles.obstacles, ["orange", "blue"]):
            # Set obstacle parameters
            shape_params = ShapeParams()
            if t == time_of_collision:
                shape_params.facecolor = "red"
                shape_params.edgecolor = "#000000"
                shape_params.opacity = 0.9
            else:
                shape_params.facecolor = color
                shape_params.edgecolor = "#003359"
                shape_params.opacity = 0.1
            # elif isinstance(draw_params, MPDrawParams):
            # draw_params = draw_params.shape and not occupancy.shape !
            obstacle.occupancy_at_time(t).shape.draw(rnd, draw_params=shape_params)
    # Render the plot
    rnd.render()
    # Save the plot
    plt.tight_layout()
    plt.savefig(output_file)
    plt.close()
    


# This method takes a planning and check whethere the resulting trajectory is feasible according to the commonroad model
def validate_plan(scenario:Scenario, plan_model:MyModel, anchor_lane_idx:int, output_folder=None, config_sim=dummy_config_sim) -> Tuple[bool, Optional[List[int]]]:
    """
    Validation has two aspects:
    - Collisions Checking
    - Physical Feasibility - Not yet implemented
    Returns a tuple: validity flag, time of collision or None
    """
    dynamic_obstacles_dict: Dict[str, DynamicObstacle] = from_plan_to_dynamic_obstacles(scenario, plan_model, anchor_lane_idx, config_sim, interpolate=True)

    from commonroad_dc.collision.collision_detection.pycrcc_collision_dispatch import create_collision_object, create_collision_checker
    from commonroad_dc.boundary.boundary import create_road_boundary_obstacle

    if output_folder is not None:
        scenario_plot_file = os.path.join(output_folder, f"scenario.png")
        scenario_with_obstacles = deepcopy(scenario)
        scenario_with_obstacles.add_objects(list(dynamic_obstacles_dict.values()))
        plot_scenario(scenario_with_obstacles, scenario_plot_file)


    # Create collision checking machinery using the scenario without obstacles
    # cc = create_collision_checker(scenario)
    cobjs = dict()
    # Create a collision object for each obstacle using their trajectories
    for agent, obstacle in dynamic_obstacles_dict.items():
        cobjs[agent] = create_collision_object(obstacle)

    # Check whether at any time any of the objects collided with any other object
    list_of_agent_tuples = list(cobjs.items())

    already_collided = set()
    collisions = []
    
    # create collision checker from scenario without obstacles
    cc = create_collision_checker(scenario)
    # create the road boundary object
    _, road_boundary = create_road_boundary_obstacle(scenario)
    # add road boundary to collision checker
    cc.add_collision_object(road_boundary)
    for one_agent, one_agent_co in [(a, co) for (a, co) in list_of_agent_tuples[:-1] if a not in already_collided]:
        for t in range(one_agent_co.time_start_idx(), one_agent_co.time_end_idx()+1):
            if cc.collide(one_agent_co.obstacle_at_time(t)):
                print(f"{one_agent} collided with the road at time step {t}")
                already_collided.add(one_agent)
                # The scenario is NOT valid at time t
                collisions.append((False, t))
                
                if output_folder is not None:
                    collision_plot_file = os.path.join(output_folder, f"collision.png")
                    plot_collision(scenario_with_obstacles, collision_plot_file, t)
    
                break # Exit the for t loop
               
    # Check collisions between vehicles. Note collisions must be symmetric
    for one_agent, one_agent_co in [(a, co) for (a, co) in list_of_agent_tuples[:-1] if a not in already_collided]:
        for the_other_agent, the_other_agent_co in [(a, co) for (a, co) in list_of_agent_tuples[1:] if a not in already_collided]:
            for t in range(one_agent_co.time_start_idx(), one_agent_co.time_end_idx()+1):
                if one_agent_co.obstacle_at_time(t).collide(the_other_agent_co.obstacle_at_time(t)):
                    print(f"{one_agent} collided with {the_other_agent} at time step {t}")
                    # Pedantic
                    assert the_other_agent_co.obstacle_at_time(t).collide(one_agent_co.obstacle_at_time(t)), "One side collision"
                    already_collided.add(one_agent)
                    already_collided.add(the_other_agent)
                    # The scenario is NOT valid at time t
                    collisions.append((False, t))

                    if output_folder is not None:
                        collision_plot_file = os.path.join(output_folder, f"collision.png")
                        plot_collision(scenario_with_obstacles, collision_plot_file, t)

                    break # Exit the for t loop
            else:
                # https://stackoverflow.com/questions/653509/breaking-out-of-nested-loops
                continue # Execute this if t loop does not break
            break # Execute this if "for t loop" breaks
    
    # The planning is valid only if there are no collisions
    return (True, None) if len(collisions) == 0 else (False, [c[1] for c in collisions])

    #             
    #         # The planning is NOT valid, because there's a collision
    #         # return (False, time_step_of_collision)
    #         collisions.append((False, time_step_of_collision))
    

    # # The planning is valid, because there are no collisions
    # return (True, None) if len(collisions) == 0 else (False, [c[1] for c in collisions])


def plot_similarity_matrix(plans, output_directory):
    # Compute the diversity of the generated plans at each time step
    progressive_similarity_matrix, per_agent_progressive_similarity_matrix = compute_progressive_similarity_matrix(plans)

    # Plot the similarity and the similarity per agent
    similarity_output_folder = os.path.join(output_directory, f"similarity")
    os.makedirs(similarity_output_folder, exist_ok=True)

    for t in sorted(progressive_similarity_matrix.keys()):
        similarity_matrix = progressive_similarity_matrix[t]
        similarity_matrix_per_agent = per_agent_progressive_similarity_matrix[t]
        
        similarity_output_file = os.path.join(similarity_output_folder, f"time_{t}.txt")
        np.savetxt(similarity_output_file, similarity_matrix, fmt='%f')
        plt.figure()
        plt.imshow(similarity_matrix, vmin=0.0, vmax=1.0, cmap='hot', interpolation='nearest')
        plt.colorbar()
        plt.title(f"Similarity at time {t}")
        plt.tight_layout()
        similarity_plot_file = os.path.join(similarity_output_folder, f"similarity_{t}.png")
        plt.savefig(similarity_plot_file)
        plt.close()

        for agent, similarity_matrix in similarity_matrix_per_agent.items():
            similarity_output_file = os.path.join(similarity_output_folder, f"time_{t}_{agent}.txt")
            np.savetxt(similarity_output_file, similarity_matrix, fmt='%f')
            plt.figure()
            plt.imshow(similarity_matrix, vmin=0.0, vmax=1.0, cmap='hot', interpolation='nearest')
            plt.colorbar()
            plt.title(f"Similarity at time {t} - agent {agent}")
            plt.tight_layout()
            similarity_plot_file = os.path.join(similarity_output_folder, f"similarity_{t}_{agent}.png")
            plt.savefig(similarity_plot_file)
            plt.close()