import click
import os
from typing import Optional, List
from omegaconf import OmegaConf 

from commonroad.common.file_reader import XMLFileReader
from commonroad.scenario.obstacle import DynamicObstacle

from commonroad_extensions.scenario_execution.stitched_execution import FrenetixScenarioExecution
from commonroad_extensions.common.utils import override_configuration, make_nested_dict
from commonroad_extensions.common.utils import create_planning_problems_from_dynamic_obstacles

@click.command()
@click.pass_context
@click.option("--scenario-file", required=True, type=click.Path(exists=True, file_okay=True), help="The XML file containing the CommonRoad scenario to execute")
@click.option("--simulation-id", required=False, type=int, help="The (Unique) ID Assigned to the simulated scenario")
@click.option("--tranche-size", "tranche_size_time_step", required=False, type=int, help="The size of each tranche of simulation in simulation steps.")
@click.option("--max-duration", required=False, type=int, help="The max duration of the execution in time steps")
@click.option("--prediction-mode", required=False, default="walenet", type=click.Choice(["walenet", "none"],case_sensitive=False))
@click.option("--convert", "list_of_dynamic_obstacles_to_convert", required=False, type=int, multiple=True, help="The list of ids of dynamic obstacles to convert to planning problems. -1 will convert them all")
@click.option("--disable-perception-of", "list_of_disable_perception_ids", required=False, type=int, multiple=True, help="The list of ids of ego vehicles without a perception module.  -1 will disable perception for all")
def execute_scenario(ctx, scenario_file: str, simulation_id: int, tranche_size_time_step: Optional[int], max_duration: Optional[int], prediction_mode:str, list_of_dynamic_obstacles_to_convert: Optional[List[int]], list_of_disable_perception_ids: Optional[List[int]]):
    # Extract common options
    output_folder = ctx.obj["output_folder"]
    verbose = ctx.obj["verbose"]
    frenetix_root = ctx.obj["frenetix_root"]
    configuration_overrides = ctx.obj["configuration_overrides"]

    # Include additional configurations that will over write the default ones from command line parameters
    # # This is taken from the provided main.py file! Those variables are not in the yml files but not setting them crashes the system
    if simulation_id is None:
        from datetime import datetime
        td = datetime.now() # today()
        # int(now.timestamp())
        simulation_id = int(td.timestamp())

    # Locally redefined configurations

    # self.config = deepcopy(config_sim)
    # self.config.evaluation.collision_report
    additional_config = OmegaConf.create({
        "driving_agent_name": "frenetix",
        # This control debug/verbose in the Executor
        "debug": verbose,
        "verbose": verbose,
        "tranche_size_time_step": tranche_size_time_step,
        # Initial Visualization
        "plot_format": "jpg",
        "plot_height": 25,
        "plot_width": 25,
        # Those overrides Simulation configurations
        "config_sim": {
            "debug": {
                    "msg_log_mode": "CRITICAL"
            },
            "simulation": {
                "used_planner_interface": "CustomFrenetPlannerInterface", # We must force our planner interface, which forces the reference path instead of recomputing it!
                "multiprocessing": True, #  False force sequential execution
                # Originally this option was to transform existing obstacles in AVs, but 
                # Setting this to False creates tons of issues including overriding scenario plots.
                "use_multiagent": True 

            },
            # Runtime Visualization - This should be use the same colors as the initial one
            "visualization": {
                "save_gif": False,
                "save_plots": False,
                "plot_format": "png",
                "plot_height": 25,
                "plot_width": 25,

                # Linear prediction visualization
                # "draw_predicted_positions": True
            },
            "prediction": {
                "mode": None if prediction_mode == "none" else prediction_mode 
            }, # TODO felix: we changed this manually, decide which it should be
            # # Force the agents involved in a collision to generate a collision report
            # # TODO: Should this be part of the analysis instead of the execution?
            # "evaluation": {
            #     "collision_report": True
            # }
        },
        "config_planner": {
            "debug" : {
                "use_cpp": True,
                "msg_log_mode": "CRITICAL",
                # NOTE: Putting this to False means skipping creating logs.csv files for the agents
                "activate_logging": True
            },
            # NOTE: there must be an entry in this configuration before we can host the overrides. 
            # ATM, it does not seem that we do not have a way to create the automatically
            "planning" : {},
            "cost": {
                "cost_weights" : {}
            },
        }
    })

    if max_duration is not None:
        additional_config["config_sim"]["simulation"]["max_duration"] = max_duration

    if verbose:
        additional_config["config_planner"]["debug"]["msg_log_mode"] = "DEBUG"
        additional_config["config_sim"]["simulation"]["msg_log_mode"] = "DEBUG"
        additional_config["config_sim"]["visualization"]["save_plots"] = True
    
    # Load scenario and planning problems from the file
    scenario, planning_problem_set = XMLFileReader(scenario_file).open(lanelet_assignment=True)
    
    # Convert selected dynamic obstacles to planning problems
    convert_all = any([ the_id == -1 for the_id in list(list_of_dynamic_obstacles_to_convert)])
    if convert_all:
        list_of_dynamic_obstacles_to_convert = [do.obstacle_id for do in scenario.obstacles if isinstance(do, DynamicObstacle)]

    # This feature is usueful when we need to repeat a scenario made entirely by "obstacles" (e.g., HighD dataset, JARI)
    list_of_dynamic_obstacles_to_convert = list(list_of_dynamic_obstacles_to_convert)
    new_planning_problems = create_planning_problems_from_dynamic_obstacles(list_of_dynamic_obstacles_to_convert, scenario, planning_problem_set)
    dynamic_obstacle_ids = [do.obstacle_id for do in scenario.dynamic_obstacles]
    for new_planning_problem in [pp for pp in new_planning_problems if pp.planning_problem_id in dynamic_obstacle_ids]:
        dynamic_obstacle = next(iter([do for do in scenario.dynamic_obstacles if do.obstacle_id == new_planning_problem.planning_problem_id]))
        scenario.remove_obstacle(dynamic_obstacle)
        planning_problem_set.add_planning_problem(new_planning_problem)

    # Disable perception of some/all agents
    # Ensure only ego vehicles are disabled
    disable_perception_for_all = any([ the_id == -1 for the_id in list(list_of_disable_perception_ids)])
    if disable_perception_for_all:
        list_of_disable_perception_ids = list(planning_problem_set.planning_problem_dict.keys())
    else:
        list_of_disable_perception_ids = [planning_problem_id for planning_problem_id in planning_problem_set.planning_problem_dict.keys() if planning_problem_id in list_of_disable_perception_ids]
    
    # Inject the values in a new configuration object
    additional_config["config_planner"]["perception"] = dict()
    additional_config["config_planner"]["perception"]["disabled"] = list_of_disable_perception_ids

    #  Override the default configuration read from the files
    override_config_sim_from_cli_dict = make_nested_dict(configuration_overrides)
    override_config_sim_from_cli = OmegaConf.create(override_config_sim_from_cli_dict)
    override_configuration(additional_config, override_config_sim_from_cli)

    scenario_executor = FrenetixScenarioExecution(output_folder, frenetix_root, additional_config)

    # Start the execution    
    scenario_executor.execute(scenario, planning_problem_set, simulation_id, adjust_starting_time_steps=True, max_duration=max_duration)

    

   

    

