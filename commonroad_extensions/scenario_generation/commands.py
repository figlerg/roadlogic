import click
import os

from typing import Optional, List, Dict

from itertools import islice, combinations

from copy import deepcopy
from omegaconf import OmegaConf
from commonroad.common.file_reader import XMLFileReader
from commonroad.scenario.scenario import Scenario
from commonroad.planning.planning_problem import PlanningProblemSet, PlanningProblem

from commonroad_extensions.common.utils import store_scenario_and_planning_problems_to_output_folder
from commonroad_extensions.scenario_generation.utils import (
    replace_lanelet_network_in_scenario, 
    extend_the_incoming_lanelets_with_a_straight, 
    extend_the_outgoing_lanelets_with_a_straight
)
# from commonroad_extensions.scenario_generation.traffic_generation import generate_basic_traffic
from commonroad.visualization.mp_renderer import MPRenderer

from commonroad_extensions.common.utils import override_configuration, make_nested_dict

# TODO Move to generation.utils
def _extend_scenario_front(original_scenario: Scenario, planning_problem_set: PlanningProblemSet, extend_by: float) -> Scenario:
    # Extend the scenario by extending both incoming and existing lanelets
    # To avoid issues with floating point rounding the "extended" lanelets are replaced (fused) not linked to new lanelets

    scenario = deepcopy(original_scenario)
    replace_lanelet_network_in_scenario(scenario,
                                        # TODO Shall we implement fuse_lanelet?
        extend_the_outgoing_lanelets_with_a_straight(scenario,
                                                     planning_problem_set,
                                                     extension_distance=extend_by, 
                                                     fuse_lanelets=True,
                                                     keep_original_adj=True))
    return scenario

def _extend_scenario_back(original_scenario: Scenario, planning_problem_set: PlanningProblemSet, extend_by: float) -> Scenario:
    # Extend the scenario by extending both incoming and existing lanelets
    # To avoid issues with floating point rounding the "extended" lanelets are replaced (fused) not linked to new lanelets

    scenario = deepcopy(original_scenario)
    replace_lanelet_network_in_scenario(scenario, 
        extend_the_incoming_lanelets_with_a_straight(scenario,
                                                     planning_problem_set,
                                                     extension_distance=extend_by,
                                                     fuse_lanelets=True,
                                                     keep_original_adj=True))        # 
    
    return scenario


def _extend_scenario_by(original_scenario: Scenario, planning_problem_set: PlanningProblemSet, extend_by: float) -> Scenario:
    # Extend the scenario by extending both incoming and existing lanelets
    # To avoid issues with floating point rounding the "extended" lanelets are replaced (fused) not linked to new lanelets

    scenario = deepcopy(original_scenario)
    scenario = _extend_scenario_back(original_scenario, planning_problem_set, extend_by)
    scenario = _extend_scenario_front(original_scenario, planning_problem_set, extend_by)

    # replace_lanelet_network_in_scenario(scenario,
    #     extend_the_incoming_lanelets_with_a_straight(scenario,
    #                                                  planning_problem_set,
    #                                                  extension_distance=extend_by, 
    #                                                  fuse_lanelets=True,
    #                                                  # IS This is ignored ?
    #                                                  keep_original_adj=True))
    # # TODO Add fuse_lanelets parameter here !
    # replace_lanelet_network_in_scenario(scenario, 
    #     extend_the_outgoing_lanelets_with_a_straight(scenario,
    #                                                  planning_problem_set,
    #                                                  extension_distance=extend_by,
    #                                                  keep_original_adj=True))        # 
    
    return scenario

# TODO Move to common.utils
def _get_cmap(n, name='hsv'):
    import matplotlib.pyplot as plt
    """Returns a function that maps each index in 0, 1, ..., n-1 to a distinct
    RGB color; the keyword argument name must be a standard mpl colormap name."""
    return plt.cm.get_cmap(name, n)

# TODO Move to common.utils or scenario visualization module?!
def visualize_the_scenario(scenario: Scenario, planning_problem_set: PlanningProblemSet, output_folder: str, scenario_plot_file: str):
    """
    Visualize and plot the initial scenario
    """

    import matplotlib.pyplot as plt
    import matplotlib.colors as colors

    drawable_objects = list()
    drawable_objects.extend(planning_problem_set.planning_problem_dict.values())
    drawable_objects.extend(scenario.dynamic_obstacles)

    drawable_objects.sort(key= lambda idrawable : idrawable.planning_problem_id if type(idrawable)==PlanningProblem else idrawable.obstacle_id)
    # planning_problems = sorted(planning_problem_set.planning_problem_dict.values(), key= lambda pp : pp.planning_problem_id)

    unique_colors = _get_cmap(len(drawable_objects), 'rainbow')
    
    # figsize = (self.plot_height, self.plot_width)
    # rnd = MPRenderer(figsize=figsize)
    rnd = MPRenderer()

    time_begin = 0

    # set renderer draw params
    rnd.draw_params.time_begin = time_begin
    # rnd.draw_params.dynamic_obstacle.draw_icon = True

    # Draw Road and Obstacles at time stamp
    scenario.draw(rnd)
    
    # NOTE: Those are sorted!
    for i, drawable_object in enumerate(drawable_objects):
        from commonroad.visualization.drawable import IDrawable

        drawable_object: IDrawable
        drawable_object_id = drawable_object.planning_problem_id if type(drawable_object) == PlanningProblem else drawable_object.obstacle_id
        
        # set renderer draw params if planning problem
        rnd.draw_params.planning_problem.initial_state.state.facecolor = colors.to_hex(unique_colors(i))
        rnd.draw_params.planning_problem.initial_state.state.draw_arrow = True
        rnd.draw_params.planning_problem.initial_state.state.radius = 0.5
        # Add labels
        rnd.draw_params.planning_problem.initial_state.label= f"{drawable_object_id}" # - {planning_problem.initial_state.velocity}"
        rnd.draw_params.planning_problem.goal_region.shape.facecolor = colors.to_hex(unique_colors(i))
        rnd.draw_params.planning_problem.goal_region.shape.opacity = 0.5
        # set renderer draw params if dynamic obstacle
        rnd.draw_params.dynamic_obstacle.draw_icon = True
        rnd.draw_params.dynamic_obstacle.draw_initial_state = True

        rnd.draw_params.dynamic_obstacle.draw_icon = True
        rnd.draw_params.dynamic_obstacle.show_label = True
        
        # We need both otherwise begin and end otherwise it will not show it
        rnd.draw_params.dynamic_obstacle.time_begin = time_begin
        # rnd.draw_params.dynamic_obstacle.time_end = time_begin

        rnd.draw_params.dynamic_obstacle.vehicle_shape.occupancy.shape.facecolor = colors.to_hex(unique_colors(i))
        rnd.draw_params.dynamic_obstacle.vehicle_shape.occupancy.shape.edgecolor = "black"
        # Ensure this is draw above everything else
        rnd.draw_params.dynamic_obstacle.vehicle_shape.occupancy.shape.zorder = 100
        rnd.draw_params.dynamic_obstacle.vehicle_shape.occupancy.shape.opacity = 1

        rnd.draw_params.dynamic_obstacle.draw_direction = True
        rnd.draw_params.dynamic_obstacle.draw_signals = True
        
        # Draw a line instead of a set of points using the same color of the vehicle
        # Highlight better the planned trajectories (bold lines)
        rnd.draw_params.dynamic_obstacle.trajectory.draw_trajectory = True
        rnd.draw_params.dynamic_obstacle.trajectory.draw_continuous = True
        rnd.draw_params.dynamic_obstacle.trajectory.facecolor = colors.to_hex(unique_colors(i))
        rnd.draw_params.dynamic_obstacle.trajectory.line_width = 1.0

        # Include the arrow here!
        drawable_object.draw(rnd)

    # Render the plot
    rnd.render()

    plt.savefig(f"{output_folder}/{scenario_plot_file}", bbox_inches='tight')

import inspect
import sys

from commonroad_extensions.scenario_generation.traffic_generation import TrafficGenerator
from commonroad_extensions.scenario_generation.strategies import * 

ALL_TRAFFIC_GENERATORS = [ (measure_name, measure_cls) for measure_name, measure_cls in inspect.getmembers(sys.modules[__name__], inspect.isclass) if issubclass(measure_cls, TrafficGenerator) and measure_cls != TrafficGenerator]

@click.command
@click.pass_context
@click.option("--input-scenario-file", required=True, type=click.Path(exists=True, file_okay=True), help="The input CommonRoad scenario containing the road segment to use")
@click.option("--scenario-name", required=False, type=str, default="scenario", help="The name of the scenario file that will be created (without .xml extension)")
@click.option('--extend/--no-extend', default=False, help='Extend the road segments in front and back') # such that the vehicle is not at the very begoal area is not at the very end of the (original) road')
@click.option('--extend-by', required=False, type=float, default=200.0, help='How much to extend the road segments in front and back') # such that the vehicle is not at the very begoal area is not at the very end of the (original) road')
@click.option('--extend-direction', required=False, type=click.Choice(["front", "back", "both"]), default="both", help='In which direction to extend the road segments') # such that the vehicle is not at the very begoal area is not at the very end of the (original) road')
@click.option('--traffic-generator', "traffic_generator_name", required=False, multiple=False, type=click.Choice([n for n, cls in ALL_TRAFFIC_GENERATORS]), help='Strategy (class name) to generate the traffic') 
@click.option('--overwrite/--no-overwrite', "user_confirm", default=False, help='Ask user permission to overwrite existing files') 
@click.option('--max-duration', "max_duration_time_step", required=False, type=int, default=400, help='Max duration (in time steps) of the simulation')
def generate_scenario(ctx, input_scenario_file:str, scenario_name: str, extend: bool, extend_by: float, extend_direction: str, traffic_generator_name: Optional[str], user_confirm: bool, max_duration_time_step: int):
    
    # TODO Validatino can be pushed inside click option with a lambda
    if extend:
        assert extend_by > 0.0, "Invalid value for extend by, must be a positive float"

    # Write to file, ask the user to confirm if existing file is found
    scenario_file_name =  None if scenario_name is None else f"{scenario_name}.xml"

    # Extract the options from ctx
    output_folder = ctx.obj["output_folder"]
    verbose = ctx.obj["verbose"]
    random_seed = ctx.obj["random_seed"]
    configuration_overrides = ctx.obj["configuration_overrides"]
    
    if verbose:
        click.echo(f"Generating scenario {scenario_file_name} into {output_folder}")

    #############################
    # Somewhat this breaks everything even it should not?
    # import math
    # import numpy as np
    # original_scenario.translate_rotate(np.array([0.0, 0.0]), math.radians(40.0))
    # XMLFileWriter(scenario=original_scenario, planning_problem_set=None).write_scenario_to_file("./rotated-scenario.xml")

    # TODO Find a better way to deal with this. Maybe we can have a default one in a standard location (module) and overrided from 
    # CLI?
    config = OmegaConf.create()
    config.random_seed = random_seed # This is mostly for traceability

    config.initial_state = OmegaConf.create()    
    config.initial_state.distance_from_beginning_m = 5.0

    # TODO Consider replacing this with size_m such that it is adapted to the shape of the lanelet!
    config.goal_region = OmegaConf.create()
    config.goal_region.length_m = 10.0
    config.goal_region.width_m = 3.0
    config.goal_region.distance_from_end_m = config.goal_region.length_m * 0.5
    # How many time step each agent has to complete the goal    
    config.goal_region.min_duration_time_step = 400
    config.goal_region.max_duration_time_step = 600

    config.simulation = OmegaConf.create()
    # Overall duration of the simulation
    config.simulation.max_duration_time_step = max_duration_time_step

    # Configure the speed limits
    config.speed_limit = OmegaConf.create()
    config.speed_limit.highway = OmegaConf.create()
    config.speed_limit.highway.min_initial_velocity_mps = 90.0 / 3.6
    config.speed_limit.highway.max_initial_velocity_mps = 110.0 / 3.6
    
    config.speed_limit.urban_road = OmegaConf.create()
    config.speed_limit.urban_road.min_initial_velocity_mps = 5.0 / 3.6
    config.speed_limit.urban_road.max_initial_velocity_mps = 50.0 /3.6
        
    config.speed_limit.access_ramp = OmegaConf.create()
    config.speed_limit.access_ramp.min_initial_velocity_mps = 30.0 / 3.6
    config.speed_limit.access_ramp.max_initial_velocity_mps = 70.0 / 3.6

    # Defaul speed limit - Urban
    config.speed_limit.min_initial_velocity_mps = config.speed_limit.urban_road.min_initial_velocity_mps
    config.speed_limit.max_initial_velocity_mps = config.speed_limit.urban_road.max_initial_velocity_mps

    # Generate the problem set using a (hardcoded) traffic generator on the original map
    config.traffic_flow = OmegaConf.create()
    config.traffic_flow.min_vehicles = 4
    config.traffic_flow.max_vehicles = 10
    ################################################################################
    
    override_config_from_cli_dict = make_nested_dict(configuration_overrides)
    override_config_sim_from_cli = OmegaConf.create(override_config_from_cli_dict)
    override_configuration(config, override_config_sim_from_cli)

    original_scenario, _ = XMLFileReader(input_scenario_file).open()
    

    # Empty set.
    planning_problem_set = PlanningProblemSet()

    # Traffic generator happens on the original scenario, so before any extension. If you need to work on an extend scenario, generate it before.
    traffic_generator = None
    if traffic_generator_name is not None:

        # HARDCODED ! TODO Move this to an actual parameter
        # 20 seconds
        config.traffig_generation = OmegaConf.create()
        config.traffig_generation.last_agent_starts_at_time_step = 200

        # This will alter the id_counter inside the original scenario
        traffic_generator_cls = next(iter(tfc for tfn, tfc in ALL_TRAFFIC_GENERATORS if tfn == traffic_generator_name))
        traffic_generator = traffic_generator_cls(config, original_scenario)
        planning_problem_set, traffic_meta_data = traffic_generator.generate()

    if extend_direction == "front":
        extended_scenario = original_scenario if not extend else _extend_scenario_front(original_scenario, planning_problem_set, extend_by)
    elif extend_direction == "back":
        extended_scenario = original_scenario if not extend else _extend_scenario_back(original_scenario, planning_problem_set, extend_by)
    elif extend_direction == "both":
        extended_scenario = original_scenario if not extend else _extend_scenario_by(original_scenario, planning_problem_set, extend_by)
    else:
        raise AssertionError("Extend direction is wrong")
    
    store_scenario_and_planning_problems_to_output_folder(extended_scenario, planning_problem_set, output_folder, scenario_file_name, user_confirm=user_confirm)

    if verbose:
        if traffic_generator is not None:
            # Print to console
            traffic_generator.summarize(planning_problem_set, traffic_meta_data)
            # Plot visualizations
            traffic_generator.visualize(planning_problem_set, traffic_meta_data, output_folder)
        
        if extend:
            # Keep track of the original as "-original"
            original_scenario_plot_file = f"{scenario_name}-original.jpg"
            visualize_the_scenario(original_scenario, planning_problem_set, output_folder, original_scenario_plot_file)
            # Store it with the common name
            extended_scenario_plot_file = f"{scenario_name}.jpg"
            visualize_the_scenario(extended_scenario, planning_problem_set, output_folder, extended_scenario_plot_file)
        else:
            # There is no extensions here, so the original name is file
            original_scenario_plot_file = f"{scenario_name}.jpg"
            visualize_the_scenario(extended_scenario, planning_problem_set, output_folder, original_scenario_plot_file)

@click.command
@click.pass_context
@click.option("--input-scenario-file", required=True, type=click.Path(exists=True, file_okay=True), help="The input CommonRoad scenario containing the road segment to use")
@click.option("--n-vehicles", required=True, type=int, help="How many vehicles to include in the scenario")
@click.option("--limit", required=False, type=int, default=-1, help="How many scenario generates. -1 means no limit")
def generate_baseline_scenarios(ctx, input_scenario_file:str, n_vehicles: int, limit: int):
    # TODO Consider to define a strategy for this one... 
    # Given an input map, generate all possible scenarios involving a vehicle
    #   - Initial position is fixed at X meters in front of the incoming lane
    #   - Goal position is fixed at Y meters before the end of the outgoing lane
    #   - Extend the outgoing lanes by Z meters
    #   - Initial speed is the speed limit if the type of lane is specified or 0.0 otherwise

    # Extract the options from ctx
    output_folder = ctx.obj["output_folder"]
    verbose = ctx.obj["verbose"]
    random_seed = ctx.obj["random_seed"]

    if verbose:
        click.echo(f"Generating baseline scenarios with {n_vehicles} vehicles into {output_folder}")

    original_scenario, _ = XMLFileReader(input_scenario_file).open()

    config = OmegaConf.create()
    config.random_seed = random_seed # This is mostly for traceability

    config.initial_state = OmegaConf.create()    
    config.initial_state.distance_from_beginning_m = 5.0

    # TODO Consider replacing this with size_m such that it is adapted to the shape of the lanelet!
    config.goal_region = OmegaConf.create()
    config.goal_region.length_m = 10.0
    config.goal_region.width_m = 3.0
    config.goal_region.distance_from_end_m = config.goal_region.length_m * 0.5

    config.simulation = OmegaConf.create()
    config.simulation.max_duration_time_step = 400

    # Configure the speed limits
    config.speed_limit = OmegaConf.create()
    config.speed_limit.highway = OmegaConf.create()
    config.speed_limit.highway.min_initial_velocity_mps = 90.0 / 3.6
    config.speed_limit.highway.max_initial_velocity_mps = 110.0 / 3.6
    
    config.speed_limit.urban_road = OmegaConf.create()
    config.speed_limit.urban_road.min_initial_velocity_mps = 5.0 / 3.6
    config.speed_limit.urban_road.max_initial_velocity_mps = 50.0 /3.6
        
    config.speed_limit.access_ramp = OmegaConf.create()
    config.speed_limit.access_ramp.min_initial_velocity_mps = 30.0 / 3.6
    config.speed_limit.access_ramp.max_initial_velocity_mps = 70.0 / 3.6

    # Defaul speed limit - Urban
    config.speed_limit.min_initial_velocity_mps = config.speed_limit.urban_road.min_initial_velocity_mps
    config.speed_limit.max_initial_velocity_mps = config.speed_limit.urban_road.max_initial_velocity_mps

    # Generate the problem set using a (hardcoded) traffic generator on the original map
    
    # Empty set. This is only to generate IDs... use scenario.get_next_id()
    planning_problem_set = PlanningProblemSet()

    # Traffic generator happens on the original scenario, so before any extension. If you need to work on an extend scenario, generate it before.
    
    # Create a new lanelat network extended by 
    extend_by_m = 100.0 #m
    extended_scenario = _extend_scenario_front(original_scenario, planning_problem_set, extend_by_m)
    
    # Analyze the map to get input and reacheable output lanelets
    feasible_paths = compute_feasible_paths(original_scenario)

    def sample_path():
        # Get only the info about in/out lanelets
        shuffled_feasible_path_keys = list(feasible_paths.keys())
        random.shuffle(shuffled_feasible_path_keys)
        
        # Sample combinations of paths without duplicate paths
        for next_path_id in combinations(range(len(shuffled_feasible_path_keys)),n_vehicles):
            # Get the corrending path
            next_path = [shuffled_feasible_path_keys[i] for i in next_path_id]
            # Check that no two vehicles start from the same lanelet
            all_incoming_lanelet_ids = [path[0] for path in next_path]
            if len(set(all_incoming_lanelet_ids)) == len(all_incoming_lanelet_ids):
                yield next_path
            else:
                continue

    # Ensure we sample only up to the limit, if one is given
    sample_path_iterator = (islice(sample_path(), limit)) if limit > 0 else (sample_path())
    
    for baseline_id, selected_paths in enumerate(sample_path_iterator):
        # Define the Planning problem on the original scenario, which shares with the extended scenario the id of the lanelets
        planning_problem_set = PlanningProblemSet()
        
        # Add a planning problem for each vehicle
        for feasible_path in selected_paths:
            incoming_lanelet_id, outgoing_lanelet_id = feasible_path
            
            incoming_lanelet = original_scenario.lanelet_network.find_lanelet_by_id(incoming_lanelet_id)
            outgoing_lanelet = original_scenario.lanelet_network.find_lanelet_by_id(outgoing_lanelet_id)
            # Get the corresponding goal region
            goal_region =  get_goal_region_on_lanelet(outgoing_lanelet, config)
            # This will automatically assign the id to the planning problems based on what is in the scenario
            start_agent_at_time_step = 0
            # Note: Use need to use the extended scenario to ensure IDs of the planning problems are correct
            planning_problem = generate_planning_problem_at_timestep(start_agent_at_time_step, config,
                                                                    incoming_lanelet, outgoing_lanelet,
                                                                    goal_region, extended_scenario)
            planning_problem_set.add_planning_problem(planning_problem)

        # Define the scenario
        scenario_name = f"scenario_baseline_with_{n_vehicles}_agents-{baseline_id}"

        print(f"Generating scenario {scenario_name}")

        scenario_file_name = f"{scenario_name}.xml"
        store_scenario_and_planning_problems_to_output_folder(extended_scenario, planning_problem_set,
                                                              output_folder, scenario_file_name)

        original_scenario_plot_file = f"{scenario_name}-original.jpg"
        visualize_the_scenario(original_scenario, planning_problem_set, output_folder, original_scenario_plot_file)

        extended_scenario_plot_file = f"{scenario_name}.jpg"
        visualize_the_scenario(extended_scenario, planning_problem_set, output_folder, extended_scenario_plot_file)

@click.command
@click.pass_context
@click.option("--scenario-name", required=False, type=str, default="scenario", help="The name of the scenario file that will be created (without .xml extension)")
@click.option("--simulation-folder", required=False, type=click.Path(exists=True,dir_okay=True,file_okay=False), help="The folder containing the original and executed scenarios (e.g. simulation_00001)")
# Mutation Operators: -1 means ALL
@click.option("--keep-planning-problem", "_planning_problem_ids_to_keep", required=False, default=[-1], type=int, multiple=True, help="The ID of the planning problem to execute")
@click.option("--remove-obstacle", "_obstacle_ids_to_remove", required=False, type=int, default=[],  multiple=True, help="The ID of the obstacles to remove")
@click.option('--overwrite/--no-overwrite', "user_confirm", default=False, help='Ask user permission to overwrite existing files') 
def generate_from_simulation(ctx, scenario_name: str, simulation_folder: str, _planning_problem_ids_to_keep: Tuple[int], _obstacle_ids_to_remove: Tuple[int], user_confirm: bool):
    """
    Takes some planning problems from the scenario file and the remaining obstacles from the executed scenarios. 
    Ensures that dynamic obstacles that correspond to the planning problems are removed.
    This is to make the merge between different scenarios + executed_scenarios
    """
    # Assume they are indeed the same scenarios!
    # Consistency is assumed!
    # TODO Validate...

    scenario_file_name =  None if scenario_name is None else f"{scenario_name}.xml"

    # Extract the options from ctx
    output_folder = ctx.obj["output_folder"]
    verbose = ctx.obj["verbose"]
    random_seed = ctx.obj["random_seed"]


    scenario_file = os.path.join(simulation_folder, "scenario.xml")
    executed_scenario_file = os.path.join(simulation_folder, "executed_scenario.xml")
    original_scenario, original_planning_problem_set = XMLFileReader(scenario_file).open()
    executed_scenario, executed_planning_problem_set = XMLFileReader(executed_scenario_file).open()

    planning_problem_ids_to_keep = list(_planning_problem_ids_to_keep)
    if -1 in _planning_problem_ids_to_keep:
        planning_problem_ids_to_keep.clear()
        [planning_problem_ids_to_keep.append(planning_problem.plannig_problem_id) for planning_problem in original_planning_problem_set.planning_problem_dict.keys()]

    obstacle_ids_to_remove = list(_obstacle_ids_to_remove)
    if -1 in obstacle_ids_to_remove:
        obstacle_ids_to_remove.clear()
        [obstacle_ids_to_remove.append(obstacle.obstacle_id) for obstacle in executed_scenario.dynamic_obstacles]

    if verbose:
        click.echo(f"Generating scenario {scenario_file_name} into {output_folder} from {simulation_folder} " \
                   f"keeping planning problems {planning_problem_ids_to_keep} while removing "\
                   f"obstacles {obstacle_ids_to_remove}")

    filtered_scenario = deepcopy(executed_scenario)
    
    # Remove the obstacles in the list or all if the list contains -1
    for obstacle_id in obstacle_ids_to_remove:
        filtered_scenario.remove_obstacle(filtered_scenario.obstacle_by_id(obstacle_id))

    # Add the planning problems from the list (ensure that the corresponding obstacle is not there)
    filtered_planning_problem_list = list()
    for planning_problem_id in planning_problem_ids_to_keep:
        # Copy over the selected planning problem
        filtered_planning_problem_list.append(original_planning_problem_set.planning_problem_dict[planning_problem_id])
        # Remove the obstacles corresponding to the selected planning problem
        if filtered_scenario.obstacle_by_id(planning_problem_id) is not None:
            filtered_scenario.remove_obstacle(filtered_scenario.obstacle_by_id(planning_problem_id))

    # Write the resulting mashup scenario
    filtered_planning_problem_set = PlanningProblemSet(filtered_planning_problem_list)
    store_scenario_and_planning_problems_to_output_folder(filtered_scenario, filtered_planning_problem_set, output_folder, scenario_file_name, user_confirm=user_confirm)

    if verbose:
        scenario_plot_file = f"{scenario_name}.jpg"
        visualize_the_scenario(filtered_scenario, filtered_planning_problem_set, output_folder, scenario_plot_file)
        # Keep track of the original as "-original"
        original_scenario_plot_file = f"{scenario_name}-original-scenario.jpg"
        visualize_the_scenario(original_scenario, original_planning_problem_set, output_folder, original_scenario_plot_file)
        # Store it with the common name
        executed_scenario_plot_file = f"{scenario_name}-executed-scenario.jpg"
        visualize_the_scenario(executed_scenario, executed_planning_problem_set, output_folder, executed_scenario_plot_file)