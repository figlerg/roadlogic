import math

from typing import Tuple, List, Any

from shapely.geometry import Point, LineString

from omegaconf import OmegaConf

from commonroad.common.file_reader import XMLFileReader
from commonroad.common.file_writer import XMLFileWriter
from commonroad.scenario.lanelet import Lanelet, LaneletNetwork, LaneletType
from commonroad.scenario.scenario import Scenario, DynamicObstacle
from commonroad.planning.planning_problem import PlanningProblem, PlanningProblemSet
from commonroad.planning.goal import GoalRegion, Interval
from commonroad.geometry.shape import Rectangle, Polygon
from commonroad.scenario.state import CustomState, InitialState
from commonroad.common.file_writer import OverwriteExistingFile

import commonroad_crime.utility.logger as utils_log
import commonroad_crime.utility.solver as utils_sol
import commonroad_crime.utility.general as utils_gen

import logging

def patch_TTC():

    import commonroad_crime.measure.time.ttc as patched_metric_module
    logger = logging.getLogger(patched_metric_module.__name__)

    def patched_compute(self, vehicle_id: int, time_step: int = 0, verbose: bool = True):
    
        if not self.validate_update_states_log(vehicle_id, time_step, verbose):
            return np.nan
        state = self.ego_vehicle.state_at_time(time_step)
        state_other = self.other_vehicle.state_at_time(time_step)
        lanelet_id = self.sce.lanelet_network.find_lanelet_by_position(
            [self.ego_vehicle.state_at_time(time_step).position]
        )[0]

        # In some cases the lanelets have narrow gaps, so we approximate this using the shape of the vehicle
        if len(lanelet_id) == 0:
            lanelet_id = self.sce.lanelet_network.find_lanelet_by_shape(self.ego_vehicle.occupancy_at_time(time_step).shape)

        """
        Using https://www.diva-portal.org/smash/get/diva2:617438/FULLTEXT01.pdf 
        "Collision Avoidance Theory with Application to Automotive Collision Mitigation" formula 5.26
        """

        # distance along the lanelet
        delta_d = self._hw_object.compute(vehicle_id, time_step, verbose)

        if delta_d == math.inf:
            self.value = math.inf
        else:
            # orientation of the ego vehicle and the other vehicle

            try:
                ego_orientation = utils_sol.compute_lanelet_width_orientation(
                    self.sce.lanelet_network.find_lanelet_by_id(lanelet_id[0]),
                    self.ego_vehicle.state_at_time(time_step).position,
                )[1]
            except ValueError as e:
                utils_log.print_and_log_warning(
                    logger,
                    f"* <TTC> During the projection of the ego vehicle {self.ego_vehicle.obstacle_id} "
                    f"at time step {self.time_step}: {e}",
                )
                self.value = math.nan
            else:
                try:
                    other_orientation = utils_sol.compute_lanelet_width_orientation(
                        self.sce.lanelet_network.find_lanelet_by_id(lanelet_id[0]),
                        self.other_vehicle.state_at_time(time_step).position,
                    )[1]
                except ValueError as e:
                    utils_log.print_and_log_warning(
                        logger,
                        f"* <TTC> During the projection of the vehicle {self.other_vehicle.obstacle_id} "
                        f"at time step {self.time_step}: {e}",
                    )
                    # out of projection domain: the other vehicle is far away
                    self.value = math.inf
                else:
                    # actual velocity and acceleration of both vehicles along the lanelet
                    v_ego = (
                        np.sign(state.velocity)
                        * math.sqrt(state.velocity**2 + state.velocity_y**2)
                        * math.cos(ego_orientation)
                    )
                    # include the directions
                    a_ego = (
                        np.sign(state.acceleration)
                        * math.sqrt(state.acceleration**2 + state.acceleration_y**2)
                        * math.cos(ego_orientation)
                    )
                    if isinstance(self.other_vehicle, DynamicObstacle):
                        v_other = math.sqrt(
                            state_other.velocity**2 + state_other.velocity_y**2
                        ) * math.cos(other_orientation)
                        a_other = math.sqrt(
                            state_other.acceleration**2 + state_other.acceleration_y**2
                        ) * math.cos(other_orientation)
                    else:
                        v_other = 0.0
                        a_other = 0.0
                    delta_v = v_other - v_ego
                    delta_a = a_other - a_ego

                    if delta_v < 0 and abs(delta_a) <= 0.1:
                        self.value = utils_gen.int_round(-(delta_d / delta_v), 2)
                    elif delta_v**2 - 2 * delta_d * delta_a < 0:
                        self.value = math.inf
                    elif (delta_v < 0 and delta_a != 0) or (delta_v >= 0 > delta_a):
                        first = -(delta_v / delta_a)
                        second = np.sqrt(delta_v**2 - 2 * delta_d * delta_a) / delta_a
                        self.value = utils_gen.int_round(first - second, 2)
                    else:  # delta_v >= 0 and delta_a >= 0
                        self.value = math.inf

        utils_log.print_and_log_info(
            logger, f"*\t\t {self.measure_name} = {self.value}", verbose
        )
        return self.value

    return patched_compute

def patch_Latj():

    import commonroad_crime.measure.jerk.lat_j as patched_metric_module
    logger = logging.getLogger(patched_metric_module.__name__)
    
    def patched_compute(self, time_step: int, vehicle_id: int = None, verbose: bool = True):
        if not self.validate_update_states_log(vehicle_id, time_step, verbose):
            return np.nan
        lanelet_id = self.sce.lanelet_network.find_lanelet_by_position(
            [self.ego_vehicle.state_at_time(time_step).position]
        )[0]

        # In some cases the lanelets have narrow gaps, so we approximate this using the shape of the vehicle
        if len(lanelet_id) == 0:
            lanelet_id = self.sce.lanelet_network.find_lanelet_by_shape(self.ego_vehicle.occupancy_at_time(time_step).shape)

        # orientation of the ego vehicle and the other vehicle
        ego_orientation = utils_sol.compute_lanelet_width_orientation(
            self.sce.lanelet_network.find_lanelet_by_id(lanelet_id[0]),
            self.ego_vehicle.state_at_time(time_step).position,
        )[1]
        evaluated_state = self.ego_vehicle.state_at_time(self.time_step)
        self.value = utils_gen.int_round(
            abs(evaluated_state.jerk * math.sin(ego_orientation)), 2
        )
        return self.value

    return patched_compute

def patch_Longj():
    
    import commonroad_crime.measure.jerk.long_j as patched_metric_module
    logger = logging.getLogger(patched_metric_module.__name__)
    
    def patched_compute(self, time_step: int, vehicle_id: int = None, verbose: bool = True):
        if not self.validate_update_states_log(vehicle_id, time_step, verbose):
            return np.nan
        evaluated_state = self.ego_vehicle.state_at_time(self.time_step)
        lanelet_id = self.sce.lanelet_network.find_lanelet_by_position(
            [self.ego_vehicle.state_at_time(time_step).position]
        )[0]

        # In some cases the lanelets have narrow gaps, so we approximate this using the shape of the vehicle
        if len(lanelet_id) == 0:
            lanelet_id = self.sce.lanelet_network.find_lanelet_by_shape(self.ego_vehicle.occupancy_at_time(time_step).shape)
            
        # orientation of the ego vehicle and the other vehicle
        ego_orientation = utils_sol.compute_lanelet_width_orientation(
            self.sce.lanelet_network.find_lanelet_by_id(lanelet_id[0]),
            self.ego_vehicle.state_at_time(time_step).position,
        )[1]
        self.value = utils_gen.int_round(
            abs(evaluated_state.jerk * math.cos(ego_orientation)), 2
        )
        utils_log.print_and_log_info(
            logger, f"*\t\t {self.measure_name} = {self.value}", verbose
        )
        return self.value

    return patched_compute

def patch_ALongReq():
    import commonroad_crime.measure.acceleration.a_long_req as patched_metric_module
    
    logger = logging.getLogger(patched_metric_module.__name__)
    
    
    def patched_compute(self, vehicle_id: int, time_step: int = 0, verbose: bool = True):
        if not self.validate_update_states_log(vehicle_id, time_step, verbose):
            return np.nan
        if self._except_obstacle_in_same_lanelet(expected_value=0.0, verbose=verbose):
            # no negative acceleration is needed for avoiding a collision
            utils_log.print_and_log_info(
                logger, f"*\t\t {self.measure_name} = {self.value}", verbose
            )
            return self.value
        lanelet_id = self.sce.lanelet_network.find_lanelet_by_position(
            [self.ego_vehicle.state_at_time(time_step).position]
        )[0]

        # In some cases the lanelets have narrow gaps, so we approximate this using the shape of the vehicle
        if len(lanelet_id) == 0:
            lanelet_id = self.sce.lanelet_network.find_lanelet_by_shape(self.ego_vehicle.occupancy_at_time(time_step).shape)



        # orientation of the ego vehicle and the other vehicle
        ego_orientation = utils_sol.compute_lanelet_width_orientation(
            self.sce.lanelet_network.find_lanelet_by_id(lanelet_id[0]),
            self.ego_vehicle.state_at_time(time_step).position,
        )[1]
        try:
            other_orientation = utils_sol.compute_lanelet_width_orientation(
                self.sce.lanelet_network.find_lanelet_by_id(lanelet_id[0]),
                self.other_vehicle.state_at_time(time_step).position,
            )[1]
        except ValueError as e:
            utils_log.print_and_log_warning(
                logger,
                f"* <A_LONG_REQ> During the projection of the vehicle {self.other_vehicle.obstacle_id} "
                f"at time step {self.time_step}: {e}",
                verbose,
            )
            # out of projection domain: the other vehicle is far away
            a_req = 0.0
        else: # This refers to the except above
            # acceleration of the other vehicle along the lanelet
            a_obj = math.sqrt(
                self.other_vehicle.state_at_time(time_step).acceleration ** 2
                + self.other_vehicle.state_at_time(time_step).acceleration_y ** 2
            ) * math.cos(other_orientation)
            # compute the headway (relative distance) along the lanelet
            x_rel = self._hw_object.compute(vehicle_id, time_step, verbose=verbose)

            # The required longitudinal acceleration measures the longitudinal acceleration required to bring the relative
            # velocity to zero at the time of the collision.
            # If the velocity is already zero ALongReq could be zero (or should be Nan?)
            
            a_req = 0.0
            
            if x_rel > 0.0:
                # compute the vehicles' velocity along the lanelet direction
                v_ego_long = math.sqrt(
                    self.ego_vehicle.state_at_time(time_step).velocity ** 2
                    + self.ego_vehicle.state_at_time(time_step).velocity_y ** 2
                ) * math.cos(ego_orientation)
                v_other_long = math.sqrt(
                    self.other_vehicle.state_at_time(time_step).velocity ** 2
                    + self.other_vehicle.state_at_time(time_step).velocity_y ** 2
                ) * math.cos(other_orientation)
                if self.configuration.acceleration.acceleration_mode == 1:
                    # constant acceleration using (8) in "Using extreme value theory for vehicle level safety validation and
                    # implications for autonomous vehicles." is in correct
                    v_rel = v_other_long - v_ego_long
                    utils_log.print_and_log_info(
                        logger, f"*\t\t relative velocity is {v_rel}", verbose
                    )
                    a_req = min(a_obj - v_rel**2 / (2 * x_rel), 0.0)
                else:
                    # piecewise constant motion using (5.39) in "Collision Avoidance Theory with Application to Automotive
                    # Collision Mitigation"
                    a_req = -(v_ego_long**2) / (2 * (x_rel - v_other_long**2 / 2 * a_obj))
        if a_req > 0:  # the object is non-closing
            self.value = 0.0
        else:
            self.value = utils_gen.int_round(a_req, 2)
        utils_log.print_and_log_info(
            logger, f"*\t\t {self.measure_name} = {self.value}", verbose
        )
        return self.value

    return patched_compute

def patch_ALatReq():
    import commonroad_crime.measure.acceleration.a_lat_req as patched_metric_module
    logger = logging.getLogger(patched_metric_module.__name__)

    def patched_compute(self, vehicle_id: int, time_step: int = 0, verbose: bool = True):
        if not self.validate_update_states_log(vehicle_id, time_step, verbose):
            return np.nan

        if self._except_obstacle_in_same_lanelet(expected_value=0.0, verbose=verbose):
            # no negative acceleration is needed for avoiding a collision
            return self.value

        lanelet_id = self.sce.lanelet_network.find_lanelet_by_position(
            [self.ego_vehicle.state_at_time(time_step).position]
        )[0]

        # In some cases the lanelets have narrow gaps, so we approximate this using the shape of the vehicle
        if len(lanelet_id) == 0:
            lanelet_id = self.sce.lanelet_network.find_lanelet_by_shape(self.ego_vehicle.occupancy_at_time(time_step).shape)

        # orientation of the ego vehicle and the other vehicle
        ego_orientation = utils_sol.compute_lanelet_width_orientation(
            self.sce.lanelet_network.find_lanelet_by_id(lanelet_id[0]),
            self.ego_vehicle.state_at_time(time_step).position,
        )[1]
        try:
            other_orientation = utils_sol.compute_lanelet_width_orientation(
                self.sce.lanelet_network.find_lanelet_by_id(lanelet_id[0]),
                self.other_vehicle.state_at_time(time_step).position,
            )[1]
        except ValueError as e:
            utils_log.print_and_log_warning(
                logger,
                f"* <A_LAT_REQ> During the projection of the vehicle {self.other_vehicle.obstacle_id} "
                f"at time step {self.time_step}: {e}",
                verbose,
            )
            # out of projection domain: the other vehicle is far away
            self.value = 0.0
        else:
            ttc = self._ttc_object.compute(vehicle_id, time_step, verbose=verbose)
            utils_log.print_and_log_info(
                logger, f"*\t\t TTC is equal to {ttc}", verbose
            )
            if ttc == math.inf:
                # no lateral acceleration is needed for avoiding a collision
                self.value = 0.0
                return self.value
            a_obj_lat = math.sqrt(
                self.other_vehicle.state_at_time(time_step).acceleration_y ** 2
                + self.other_vehicle.state_at_time(time_step).acceleration ** 2
            ) * math.sin(other_orientation)

            # compute the headway distance
            d_rel_lat = utils_sol.compute_clcs_distance(
                self.clcs,
                self.ego_vehicle.state_at_time(time_step).position,
                self.ego_vehicle.state_at_time(time_step).position,
            )[1]
            v_rel_lat = (
                math.sqrt(
                    self.other_vehicle.state_at_time(time_step).velocity ** 2
                    + self.other_vehicle.state_at_time(time_step).velocity_y ** 2
                )
                * math.sin(other_orientation)
                - math.sqrt(
                    self.ego_vehicle.state_at_time(time_step).velocity ** 2
                    + self.ego_vehicle.state_at_time(time_step).velocity_y ** 2
                )
            ) * math.sin(ego_orientation)
            self.value = min(
                abs(self._compute_a_lat(a_obj_lat, d_rel_lat, v_rel_lat, ttc, "left")),
                abs(self._compute_a_lat(a_obj_lat, d_rel_lat, v_rel_lat, ttc, "right")),
            )
        if self.value != math.inf:
            self.value = utils_gen.int_round(self.value, 2)

        utils_log.print_and_log_info(
            logger, f"*\t\t {self.measure_name} = {self.value}", verbose
        )
        return self.value
    
    return patched_compute












# TODO Move to utils.py
def flatten(xss: List[List[Any]]) -> List[Any]:
    return [x for xs in xss for x in xs]

# TODO Move to utils.py
def cut(line: LineString, distance: float) -> List[LineString]:
    # cuts a line in two at distance from its starting point
    if distance <= 0.0 or distance >= line.length:
        return [line]
    coords = list(line.coords)
    for i, p in enumerate(coords):
        pd = line.project(Point(p))
        if pd == distance:
            return [
                LineString(coords[:i + 1]),
                LineString(coords[i:])]
        if pd > distance:
            cp = line.interpolate(distance)
            return [
                LineString(coords[:i] + [(cp.x, cp.y)]),
                LineString([(cp.x, cp.y)] + coords[i:])]

# TODO Move to utils.py
def speed_interval_for_lanelet(config: OmegaConf, lanelet: Lanelet) -> Tuple[float, float]:
    lanelet_min_speed = config.speed_limit.min_initial_velocity_mps
    lanelet_max_speed = config.speed_limit.max_initial_velocity_mps
    
    # One lanelet may have multiple types!
    # Check the most restrictive last

    if LaneletType.URBAN in lanelet.lanelet_type:
        lanelet_min_speed = config.speed_limit.urban_road.min_initial_velocity_mps
        lanelet_max_speed = config.speed_limit.urban_road.max_initial_velocity_mps
        

    if LaneletType.ACCESS_RAMP in lanelet.lanelet_type:
        lanelet_min_speed = config.speed_limit.access_ramp.min_initial_velocity_mps
        lanelet_max_speed = config.speed_limit.access_ramp.max_initial_velocity_mps

    return lanelet_min_speed, lanelet_max_speed


def get_orientation_by_coords(first_point: Tuple[float, float], next_point: Tuple[float, float]):
    a_x, a_y = next_point
    b_x, b_y = first_point
    # compute orientation: https://stackoverflow.com/questions/42258637/how-to-know-the-angle-between-two-vectors
    return math.atan2(a_y - b_y, a_x - b_x)

from typing import Union
from PIL import Image
import os
import imageio.v3 as iio
import numpy as np
from tqdm import tqdm
import contextlib

def make_gif_for_stitched_simulatoin(simulation_folder: str, duration: float = 0.1, output_file_names_to_list: bool = False):
    """ 
    Create an animated GIF from saved image files in a Stitched simulation.

    Images are assumed to be saved as <log_path>/plots/<scenario_id>_<timestep>.png
    in the tranches folder (not duplicated files should be removed)

    Does not check the plotting configuration in order to simplify independent
    configurations on agent and simulation level. This has to be done by the caller.

    """

    print("Generating GIF")
    images = []
    filenames = []

    tranches_folder = os.path.join(simulation_folder, "tranches")

    # Collect all the image files in all the tranches
    for tranche_folder in sorted(os.path.join(tranches_folder, f) for f in os.listdir(tranches_folder)):
        
        if not os.path.isdir(tranche_folder): 
            continue

        print(f"Collecting plots for tranche {tranche_folder}")

        path_images = os.path.join(tranche_folder, "logs", "plots")

        # Time steps are not padded!
        for im_path in sorted([os.path.join(path_images, f) for f in os.listdir(path_images)], key = lambda pf : int(pf.split(".png")[0].split("_")[-1])):
            if not os.path.isfile(im_path) or not im_path.endswith(".png"):
                continue
            if len(filenames) == 0 or int(im_path.split(".png")[0].split("_")[-1]) != int(filenames[-1].split(".png")[0].split("_")[-1]):
                filenames.append(im_path)
                # print(f"Found {im_path}")

    def crop(filename, img_width, img_height, pbar):
        
        # print(f"Cropping {filename}")

        img = Image.open(filename)
        width, height = img.size

        # Calculate the area to crop
        left = 0
        top = 0
        right = img_width if width != img_width else width
        bottom = img_height if height != img_height else height

        # Crop the image
        img_cropped = img.crop((left, top, right, bottom))

        pbar.update(1)
        
        return img_cropped
    # Processing the images
    # img_width = 0
    # img_height = 0
    # use exit stack to automatically close opened images

    if output_file_names_to_list:
        output_file_list = os.path.join(simulation_folder, "input_files.txt")
        with open(output_file_list, 'w') as f:
            for line in filenames:
                f.write(f"file '{line}'\n")
        
    img = Image.open(filenames[0])
    width, height = img.size

    img_width = width
    img_height = height
    with tqdm(total = len(filenames)) as pbar:
        with contextlib.ExitStack() as stack:

            # lazily load images
            imgs = (stack.enter_context(crop(f, img_width, img_height, pbar)) for f in filenames[:600])

            # extract  first image from iterator
            img = next(imgs)

            # https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#gif
            output_gif = os.path.join(simulation_folder, "simulation.gif")
            duration_in_milliseconds = duration * 1000.0
            img.save(fp=output_gif, format='GIF', append_images=imgs,
                    save_all=True, duration=duration_in_milliseconds, loop=0)

    # This failes for large number of images
    # print("Cropping images")
    # with tqdm(total = len(filenames)) as pbar:
    #     for filename in filenames:
    #         img = Image.open(filename)
    #         width, height = img.size

    #         if not img_width:
    #             img_width = width
    #             img_height = height

    #         # Calculate the area to crop
    #         left = 0
    #         top = 0
    #         right = img_width if width != img_width else width
    #         bottom = img_height if height != img_height else height

    #         # Crop the image
    #         img_cropped = img.crop((left, top, right, bottom))

    #         # Convert the PIL image to an array for imageio
    #         img_array = np.array(img_cropped)
    #         images.append(img_array)

    #         img.close()
    #         pbar.update(1)

    # print(f"Generating the simulation using {len(images)} images. Overall duration of the gif {len(images) * duration} seconds")

    # iio.imwrite(os.path.join(simulation_folder, "simulation.gif"),
    #             images, duration=duration)

import os
import shutil

from typing import Dict, Any

from copy import deepcopy
from importlib.resources import files

# Copied from condi/frenetix_utils. We need either a common package for handling configurations or at least
# decouple the testing infrastructure from the test subject!
from cr_scenario_handler.utils.configuration_builder import ConfigurationBuilder
from cr_scenario_handler.simulation.simulation import Simulation

from commonroad.scenario.scenario import Scenario
from commonroad.prediction.prediction import Trajectory, TrajectoryPrediction

from collections import namedtuple

SimulationMetaData = namedtuple('SimulationMetaData', ['config_sim', 'config_planner'])
RelevantInterval = namedtuple('RelevantInterval', ['start', 'end'])

def setup_simulation_of_scenario(scenario_file: str, output_folder: str, simulation_name: str):
        simulation_folder = os.path.join(output_folder, simulation_name)
        logs_path = os.path.join(simulation_folder, "logs")
        os.makedirs(simulation_folder, exist_ok=True)

        # Default name for the input scenario file
        scenario_name = "scenario"
        # Copy the input scenario in the scenario folder
        shutil.copyfile(scenario_file, os.path.join(simulation_folder, f"{scenario_name}.xml"))

        # Prepare the default configurations
        config_sim = generate_default_simulation_configuration_from_package(scenario_name, simulation_folder)
        config_planner = generate_default_planner_configuration_from_package(scenario_name)

        apply_custom_configurations(config_sim, config_planner, logs_path=logs_path, simulation_folder=simulation_folder)

        return SimulationMetaData(config_sim, config_planner)

def generate_default_planner_configuration_from_package(scenario_name: str):
    """
    Force the scenario name into the default configuration of the planner
    """
    #  Load the planner conf are packaged within the cr_scenario_handler_utils package
    root_path = files('cr_scenario_handler_utils')
    return ConfigurationBuilder.build_frenetplanner_configuration(scenario_name, root_path)


def generate_default_simulation_configuration_from_package(scenario_name: str, scenario_folder: str):
    """
    Force the scenario name and the simulation (output) folder into the default configuration of the simulation
    """
    # Load the simulation configuration from the installed package
    root_path = files('cr_scenario_handler')
    config_sim = ConfigurationBuilder.build_sim_configuration(
        scenario_name=scenario_name,
        scenario_folder=scenario_folder,
        root_path=root_path,
    )
    return config_sim

def override_configuration(config, overrides: Dict[Any, Any]):
    # This is a very specific code...
    # print(f"Overriding {config}")
    for key, value in overrides.items():
        if type(value) == dict and hasattr(config, key):
            # Recursively try to set dict/nested config
            override_configuration(getattr(config, key), value)
        elif hasattr(config, key):
            print(f"Forcing {value} on {key}")
            setattr(config, key, value)

def apply_custom_configurations(config_sim, config_planner, **kwargs):
    """
    Group here a bunch of configuration overwrites and additional properties that are needed for later processing
    """
    config_sim.simulation.use_multiagent = False
    if "logs_path" in kwargs:
        config_sim.simulation.log_path = kwargs["logs_path"]

    if "simulation_folder" in kwargs:
        config_sim.simulation.simulation_folder = kwargs["simulation_folder"]

    config_sim.evaluation.evaluate_simulation = False

    config_sim.visualization.plot_window_dyn = 50
    config_sim.visualization.save_plots = False
    # Force to store PNG
    config_sim.visualization.save_gif = False

    config_planner.debug.use_cpp = True
    config_planner.debug.msg_log_mode = "INFO" #"DEBUG"
    
    # Not sure what's the difference between those...
    # But they control whether the planner tries to stick to the desired speed or not
    
    # Can this be a FIXED cost if velocity is not met?
    config_planner.cost.cost_weights.velocity = 1.0
    # Can this be a VARIABLE cost that depends on how far we are from the target velocity?
    config_planner.cost.cost_weights.velocity_offset = 1.0


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



##############################################################################################################################

from copy import deepcopy
from functools import reduce

from omegaconf import OmegaConf, DictConfig
from cr_scenario_handler.utils.helper_functions import find_lanelet_by_position_and_orientation

def store_scenario_and_planning_problems_to_output_folder(scenario: Scenario, planning_problem_set: PlanningProblemSet, 
                                                          output_folder: str, scenario_file_name: str = "scenario.xml", 
                                                          user_confirm: bool = False,
                                                          leave_obstacles: bool = False):

    assert os.path.exists(output_folder), f"Output folder {output_folder} does not exist!"

    # Store the executed scenario in the output folder
    scenario_without_obstacles = deepcopy(scenario)
    
    # TODO Is this really needed?!
    if leave_obstacles:
        # Remove all the obstacles unless told otherwise
        [ scenario_without_obstacles.remove_obstacle(obs) for obs in scenario_without_obstacles.obstacles[:]]

    scenario_file = os.path.join(output_folder, scenario_file_name)
    # Decimal precision is a tricky parameter because I am not sure what is read by the XMLFileReader
    mode = OverwriteExistingFile.ALWAYS if not user_confirm else OverwriteExistingFile.ASK_USER_INPUT
    XMLFileWriter(scenario_without_obstacles, planning_problem_set, decimal_precision=20).write_to_file(scenario_file, mode, check_validity=True)


def store_executed_scenario_to_output_folder(executed_scenario: Scenario, output_folder: str, executed_scenario_file_name: str = "executed_scenario.xml"):
    """
    Note: this does not store the planning problems!
    """
    assert os.path.exists(output_folder), f"Output folder {output_folder} does not exist!"

    # Store the executed scenario in the output folder
    executed_scenario_file = os.path.join(output_folder, executed_scenario_file_name)
    XMLFileWriter(executed_scenario, None, decimal_precision=20).write_scenario_to_file(executed_scenario_file)


def override_configuration(config, overrides: Dict[Any, Any]):
    """
    Override Frenetix configuration objects trying to match the given dictionary
    """
    from cr_scenario_handler.utils.configuration import SubConfiguration
    # This is a very specific code...
    for key, value in overrides.items():
        if (type(value) == DictConfig or type(value) == dict) and hasattr(config, key):
            # Recursively try to set dict/nested config
            # print(f"Overriding configuration {key}")
            override_configuration(getattr(config, key), value)
        elif hasattr(config, key):
            # print(f"Overwriting {key} with {value}")
            setattr(config, key, value)
        else:
            if (type(value) == DictConfig or type(value) == dict):
                # This entire subtree does not exist, create one using the dictionary
                value_as_config = SubConfiguration(DictConfig(value))
                # print(f"Forcing {key} with {value_as_config}")
                setattr(config, key, value_as_config)
                pass
            else:
                # print(f"Forcing {key} with {value}")
                setattr(config, key, value)

def make_nested_dict(configuration_overrides: List[Tuple[str, str]]):
    # Adapted from: https://stackoverflow.com/questions/66994061/convert-list-of-file-paths-to-a-nested-dictionary-similar-to-a-json-file
    # Sort so deepest paths are first
    # the deepest is also the one who contains the value
    sorted_configuration_override_and_values = [f"{t[0]}={t[1]}" for t in sorted(configuration_overrides, key = lambda t: len(t[0].lstrip('.').split('.')), reverse = True)]
    sorted_configuration_override = [co.split("=")[0] for co in sorted_configuration_override_and_values]
    sorted_configuration_override_values = [co.split("=")[1] for co in sorted_configuration_override_and_values]

    tree_path = dict()
    for path, value in zip(sorted_configuration_override, sorted_configuration_override_values):
        # Split into list and remove leading '.' if present
        levels = path.lstrip('.').split(".")
        # value = levels.pop()
        acc = tree_path
        for i, p in enumerate(levels, start = 1):
            if i == len(levels):
                # Reached termination of a path
                if value == "True" or value == "False":
                    acc[p] = bool(value)
                else:
                    for t in [int, float, str]:
                        try:
                            acc[p] = t(value)
                            break
                        except:
                            continue
                
                
                # Use current terminal object is present, else use list
                # acc[p] = acc[p] if p in acc else conf_value
                # if isinstance(acc[p], list):
                #     # Only append if we are at a list
                #     acc[p].append(file)
            else:
                # Expand with dictionary by default
                acc.setdefault(p, {})
            acc = acc[p]

    # Now we need to include the values in the right position by navigating into them...
    
    return tree_path


def ensure_lanelet_assignment(scenario: Scenario) -> None:
    # Ensure that the lanelet assignment is there for all the obstacles at least for initial_state
    # TODO Should this be recomputed for all time_steps?
    for obstacle in scenario.obstacles:
        
        if obstacle.prediction.center_lanelet_assignment is None:
            initial_state = obstacle.initial_state
            lanelet_assigned = {
                0: find_lanelet_by_position_and_orientation(scenario.lanelet_network,initial_state.position, initial_state.orientation)
            }
            obstacle.initial_center_lanelet_ids = lanelet_assigned


def merge_scenarios(scenario_a: Scenario, scenario_b: Scenario) -> Scenario:
    assert scenario_a is not None or scenario_b is not None, "One scenario must exist"

    if scenario_a is not None and scenario_b is None:
        return deepcopy(scenario_a)
    
    if scenario_a is None and scenario_b is not None:
        return deepcopy(scenario_b)
    
    # Extract all the obstacles from the scenarios
    all_obstacles = dict()
    for obstacle in scenario_a.obstacles + scenario_b.obstacles:
        if obstacle.obstacle_id not in all_obstacles:
            all_obstacles[obstacle.obstacle_id] = list()

        if obstacle.obstacle_id in all_obstacles:
            all_obstacles[obstacle.obstacle_id].append(obstacle)

    # Sort the obstacles by initial timestep
    [ list_of_obstacles.sort(key=lambda o: o.initial_state.time_step) for list_of_obstacles in all_obstacles.values()]

    # For each obstacle, create a new obstacle whose trajectory is the merge of the trajectories of the two other obstacles
    merged_obstacles = list()
    for obstacle_in_tranches in all_obstacles.values():
        
        # The first one in the list corresponds to the first tranche
        obs = deepcopy(obstacle_in_tranches[0])
        # The initial timestep and lanelet_assigned are the original one
        shape = obs.obstacle_shape
        
        ini_state = obs.initial_state
        
        # We need this one otherwise the criticality metrics do not work...
        # scenario_a and scenario_b are assumed to have the same lanelet_network!
        lanelet_assigned = {0: find_lanelet_by_position_and_orientation(scenario_a.lanelet_network,
                                                                        ini_state.position, ini_state.orientation)
                            }

        # We merge all the trajectories and remove the overlapping element
        merged_state_list = reduce(lambda obs_prev_state_list, obs_next_state_list: obs_prev_state_list + obs_next_state_list, [ obs.prediction.trajectory.state_list for obs in obstacle_in_tranches])
        
        # We recreate the prediction using the merged state list
        # Note the prediction does NOT include the initial know state obs.initial_state
        obs.prediction = TrajectoryPrediction(
            Trajectory(initial_time_step=merged_state_list[0].time_step, state_list=merged_state_list), 
            shape,
            center_lanelet_assignment=lanelet_assigned)
    
        merged_obstacles.append(obs)

    merged_scenario = deepcopy(scenario_a)
    # Remove existing obstacles
    [merged_scenario.remove_obstacle(obs) for obs in merged_scenario.obstacles[:]]
    # Add merged obstacles
    merged_scenario.add_objects(merged_obstacles)

    return merged_scenario


def create_planning_problems_from_dynamic_obstacles(multi_agent_id_list, scenario: Scenario, planning_problem_set: PlanningProblemSet):

        """ 
        Creates the missing planning problems for agents that should be
        created from dynamic obstacles.

        The goal state is defined as a small area around the final state of the
        trajectory of the dynamic obstacle.
        The allowed deviations from this state are:
            time: +/- 20 time steps from final time step
            position: Circle with 3m diameter around final state

        :return: planning_problem_list with all created problems
        """

        planning_problem_list = []
        for agent_id in multi_agent_id_list:
            if not agent_id in planning_problem_set.planning_problem_dict.keys():
                # get dynamic obstacle of selected agent
                obstacle = scenario.obstacle_by_id(agent_id)
                
                # define initial state for planning problem
                initial_state = obstacle.initial_state
                if not hasattr(initial_state, 'acceleration'):
                    initial_state.acceleration = 0.0

                # define goal state for planning problem from the final state of the obstacle
                
                # Find the lanelet
                final_state = obstacle.prediction.trajectory.final_state
                lanelet_id = find_lanelet_by_position_and_orientation(scenario.lanelet_network, final_state.position, final_state.orientation)
                lanelet = scenario.lanelet_network.find_lanelet_by_id(lanelet_id[0])

                # Place the goal area by the end of that lanlet
                goal_center_coords, _, _, _ = lanelet.interpolate_position( (lanelet.distance[-1] - 100) )
                last_point_coords, _, _, _ = lanelet.interpolate_position( (lanelet.distance[-1] - 100 + 1) )
 
                goal_center = Point(goal_center_coords)
                last_point = Point(last_point_coords)

                orientation = get_orientation_by_coords((goal_center.x, goal_center.y), (last_point.x, last_point.y))

                #
                goal_area = Rectangle(10, 5, np.array([goal_center.x, goal_center.y]), orientation)
                
                goal_state = CustomState(time_step=Interval(0, final_state.time_step), position=goal_area)
                
                # create planning problem
                problem = PlanningProblem(agent_id, initial_state, GoalRegion(list([goal_state])))
                planning_problem_list.append(problem)

        return planning_problem_list

if __name__ == "__main__":
    simulation_folder = "/home/gambia/francescolomio/dynamic-traffic/traffic-simulations/00001"
    make_gif_for_stitched_simulatoin(simulation_folder, output_file_names_to_list=True)