from typing import Optional, List, Dict, Tuple

import subprocess
import click
import os
import glob
import csv
import enlighten
import inspect
import sys

import matplotlib.pyplot as plt
import matplotlib.colors as colors
import matplotlib.colors as mc

import colorsys


from commonroad.scenario.scenario import Scenario, DynamicObstacle
from commonroad.planning.planning_problem import PlanningProblemSet, PlanningProblem, GoalRegion
from commonroad.common.file_reader import XMLFileReader
from commonroad.prediction.prediction import Trajectory, TrajectoryPrediction

from commonroad.visualization.mp_renderer import MPDrawParams, MPRenderer


# TODO Move to common.utils
# CODE CLONE!
def _get_cmap(n, name='hsv'):
    """Returns a function that maps each index in 0, 1, ..., n-1 to a distinct
    RGB color; the keyword argument name must be a standard mpl colormap name."""
    return plt.cm.get_cmap(name, n)

def alter_color(color, amount=0.5):
    """
    Lightens or darkens the given color by multiplying (1-luminosity) by the given amount.
    Input can be matplotlib color string, hex string, or RGB tuple.

    See: https://stackoverflow.com/questions/37765197/darken-or-lighten-a-color-in-matplotlib
    """
    try:
        c = mc.cnames[color]
    except:
        c = color
    c = colorsys.rgb_to_hls(*mc.to_rgb(c))
    return colorsys.hls_to_rgb(c[0], 1 - amount * (1 - c[1]), c[2])

def visualize_the_scenario(scenario: Scenario, planning_problem_set: PlanningProblemSet, output_folder: str,
                           time_step: int, last_time_step: int,
                           size_inch: int, format: str,
                           x_lim: Tuple[float, float], y_lim: Tuple[float, float],
                           focus_on: Optional[int] = None,
                           focus_range: float = 30.0):
    """
    Plot the scenario at the given time_step
    """

    obstacles = sorted(scenario.obstacles, key= lambda o : o.obstacle_id)

    unique_colors = _get_cmap(len(obstacles), 'rainbow')

    color_mapping = dict()
    for i, obstacle in enumerate(obstacles):
        color_mapping[obstacle.obstacle_id] = colors.to_hex(unique_colors(i))
    
    figsize = (size_inch, size_inch)
    fig = plt.figure(figsize=figsize)
    ax = fig.gca()
    rnd = MPRenderer(ax=ax)

    # set renderer draw params - This is important if there are traffic lights in the scenario
    rnd.draw_params.time_begin = time_step
    rnd.draw_params.time_end = last_time_step

    # Draw the road but not the obstacles
    # TODO We do not have reference path, do we? -> Actually we have them in the tranches!
    scenario.lanelet_network.draw(rnd)

    # Draw Occupancy of the vehicles using the appropriate colors.
    for obstacle in obstacles:

        if obstacle.occupancy_at_time(time_step) is not None:
            # Set obstacle parameters
            obs_params = MPDrawParams()
            obs_params.dynamic_obstacle.draw_icon = True
            obs_params.dynamic_obstacle.show_label = True
            
            # We need both otherwise begin and end otherwise it will not show it
            obs_params.dynamic_obstacle.time_begin = time_step
            obs_params.dynamic_obstacle.time_end = last_time_step

            obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.facecolor = color_mapping[obstacle.obstacle_id]
            obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.edgecolor = "black"
            # Ensure this is draw above everything else
            obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.zorder = 100
            obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.opacity = 1

            obs_params.dynamic_obstacle.draw_direction = True
            obs_params.dynamic_obstacle.draw_signals = True
            
            # Draw a line instead of a set of points using the same color of the vehicle
            # Highlight better the planned trajectories (bold lines)
            obs_params.dynamic_obstacle.trajectory.draw_trajectory = True
            obs_params.dynamic_obstacle.trajectory.draw_continuous = True
            obs_params.dynamic_obstacle.trajectory.facecolor = color_mapping[obstacle.obstacle_id] # "black"
            obs_params.dynamic_obstacle.trajectory.line_width = 1.0

            # Static obstacles have always the same color
            # obs_params.static_obstacle.show_label = True
            # obs_params.static_obstacle.occupancy.shape.facecolor = "#A30000"
            # obs_params.static_obstacle.occupancy.shape.edgecolor = "#756F61"

            # Finally render it
            obstacle.draw(rnd, draw_params=obs_params)

            # Plot all the goal areas and highlight the one the agent should aim to at this time_step
            # if there are any
            if obstacle.obstacle_id in planning_problem_set.planning_problem_dict:
                
                planning_problem = planning_problem_set.planning_problem_dict[obstacle.obstacle_id]
                goal_region = planning_problem.goal

                for goal_state_index, goal_state in enumerate(goal_region.state_list):

                    sub_goal = GoalRegion(state_list=[goal_state])
                    goal_region_params = MPDrawParams()
                    # Ensure we plot stuff also after time step 200
                    goal_region_params.time_begin = time_step
                    goal_region_params.time_end = max(last_time_step, goal_state.time_step.end)
                    # Match the color with the vehicle
                    goal_region_params.goal_region.shape.facecolor = color_mapping[obstacle.obstacle_id]
                    # Highlight the goal if active:
                    # - Current time_step before goal timeout
                    # - No other goal is in between

                    # Compute active zone for this goal state
                    active_zone_start = 0 if goal_state_index == 0 else goal_region.state_list[goal_state_index-1].time_step.end + 1
                    active_zone_end = goal_state.time_step.end
                    
                    if time_step > active_zone_end:
                        # Past way points
                        goal_region_params.goal_region.shape.opacity = 0.2
                    elif active_zone_start <= time_step <= active_zone_end:
                        # Current way points
                        goal_region_params.goal_region.shape.opacity = 0.6
                    else:
                        # Next way points
                        goal_region_params.goal_region.shape.opacity = 0.4

                    # goal_region.draw(rnd, draw_params=goal_region_params)
                    sub_goal.draw(rnd, draw_params=goal_region_params)
                

    # Render the scenario onto the plot
    rnd.render()
    
    # Add decorations

    # Show time/timesteps
    middle_x = 0.5
    top_y = 0.9
    ax.text(middle_x, top_y, f"Time: {str(round(float(time_step * scenario.dt), 1)).rjust(5,' ')} sec", horizontalalignment='center', verticalalignment='center', transform=ax.transAxes)

    # Focus on the specified vehicle instead of showing the entire road
    skip_bbox_inches = False
    if focus_on is not None:
        obstacle_in_focus = scenario.obstacle_by_id(focus_on)
        if obstacle_in_focus is not None:
            state_of_obstacle_in_focus = obstacle_in_focus.state_at_time(time_step)
            if state_of_obstacle_in_focus is not None:
                position_x = state_of_obstacle_in_focus.position[0]
                position_y = state_of_obstacle_in_focus.position[1]
                x_lim = [ position_x - focus_range, position_x + focus_range]
                y_lim = [ position_y - focus_range, position_y + focus_range]
                skip_bbox_inches = True
            else:
                # If the obstacle disappear, do not generate any plot
                return
        else:
            # If the obstacle disappear, do not generate any plot
            return

    ax.set_xlim(x_lim)
    ax.set_ylim(y_lim)

    # TODO Make the format configurable if needed
    plot_file = os.path.join(output_folder, f"frame_{str(time_step).rjust(5, '0')}.{format}")
    # Changing the focus causes the resulting figures to be of different size with bbox_inches 
    if skip_bbox_inches:
        plt.savefig(f"{plot_file}")
    else:
        plt.savefig(f"{plot_file}", bbox_inches='tight')
    plt.close()


# focus the plotting on a specific vehicle (or replot for a specific vehicle)
@click.command()
@click.pass_context
@click.option("--simulation-folder", required=True, type=click.Path(exists=True, dir_okay=True), help="The folder containing the simulated scenario")
@click.option("--start-from", required=False, type=int, help="The time_step at which plotting starts")
@click.option("--end-at", required=False, type=int, help="The time_step at which plotting ends")
@click.option('--size', "size_inch", required=False, type=int, default=10, help='Size of the (squared) figure in inches')
@click.option('--format', "format", required=False, type=click.Choice(["png", "svg", "pdf", "jpg", "jpeg"]), default="png", help='format of the plot')
@click.option('--focus-on', required=False, type=int, help='The id of the vehicle to keep in focus')
@click.option('--focus-range', required=False, type=float, help='The vision range when focus is active.')
# Implement this only if needed
# @click.option("--vehicle-id", "selected_vehicles", required=False, multiple=True, type=int, help="The id of the vehicles to plot")
def plot_simulation(ctx, simulation_folder: str, start_from: Optional[int], end_at: Optional[int], size_inch: int, format: str, focus_on: Optional[int], focus_range: Optional[float]): #, selected_vehicles: Optional[List[int]]):
    # Extract the options from ctx
    output_folder = ctx.obj["output_folder"]
    verbose = ctx.obj["verbose"]
    
    # Executed scenario should only have obstacles that correspond to the monitored behavior of vehicles during the simulation
    # so we need to look up the "input" scenario. However, this is Optional
    
    # Default in case no scenario is available
    planning_problem_set = PlanningProblemSet(list())
    try:
        scenario_file = os.path.join(simulation_folder, "scenario.xml")
        _, planning_problem_set = XMLFileReader(scenario_file).open(lanelet_assignment=True)
    except:
        pass
    # # Extract the last time, the last planning problem should be completed
    # last_time_step = max([gs.time_step.end for pp in planning_problem_set.planning_problem_dict.values() for gs in pp.goal.state_list])
    
    executed_scenario_file = os.path.join(simulation_folder, "executed_scenario.xml")
    executed_scenario, _ = XMLFileReader(executed_scenario_file).open(lanelet_assignment=True)

    first_time_step = min([o.initial_state.time_step for o in executed_scenario.obstacles])
    # Take the latest time between execution and goal states (in case the execution stops before)
    last_time_step = max([s.time_step for o in executed_scenario.obstacles for s in o.prediction.trajectory.state_list])

    # Set intervals for plotting
    initial_time_step = first_time_step if start_from is None else start_from
    assert first_time_step <= initial_time_step, "We cannot plot starting before the scenario starts"
    final_time_step = last_time_step if end_at is None else end_at
    assert last_time_step >= final_time_step, "We cannot plot after the scenario ends"

    manager = enlighten.Manager()
    frame_pbar = manager.counter(desc='Generated Frames', total=(final_time_step-initial_time_step))

    if verbose:
        click.echo(f"Plotting scenario {executed_scenario_file} between {initial_time_step} and {final_time_step}")
        click.echo(f"Plots will be stored at {output_folder}")

    # Compute the limits once for all

    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    for time_step in range(first_time_step, last_time_step):
        for obstacle in executed_scenario.obstacles:
            state = obstacle.state_at_time(time_step)
            if state is not None:
                position_x, position_y = state.position
                min_x = position_x if position_x < min_x else min_x
                min_y = position_y if position_y < min_y else min_y
                max_x = position_x if position_x > max_x else max_x
                max_y = position_y if position_y > max_y else max_y
    
    # Make sure we visualize all the goals as well
    for goal_state in [gs for pp in planning_problem_set.planning_problem_dict.values() for gs in pp.goal.state_list]:
        position_x, position_y = goal_state.position.center
        min_x = position_x if position_x < min_x else min_x
        min_y = position_y if position_y < min_y else min_y
        max_x = position_x if position_x > max_x else max_x
        max_y = position_y if position_y > max_y else max_y
        
    margin = 10
    x_lim = (min_x - margin, max_x + margin)
    y_lim = (min_y - margin, max_y + margin)

    # For each agent, compute the metrics
    for time_step in frame_pbar(range(initial_time_step, final_time_step+1)):
        visualize_the_scenario(executed_scenario, planning_problem_set, output_folder, time_step, last_time_step, size_inch, format, x_lim, y_lim,
                               focus_on=focus_on, focus_range=focus_range)


def _is_tool(name):
    """Check whether name is on PATH and marked as executable."""
    from shutil import which
    return which(name) is not None

@click.command()
@click.pass_context
# TODO Add an option to create the plots before?
#  @click.option("--simulation-folder", required=False, type=click.Path(exists=True, dir_okay=True), help="The folder containing the simulated scenario")
@click.option("--plots-folder", required=True, type=click.Path(exists=True, dir_okay=True), help="The folder containing the plots to use")
@click.option("--frames-per-second", required=False, type=int, help="The framerate of the gif")
@click.option("--output-name", required=False, default="simulation", help="Name of the output gif file (without .gif)")
def animate_simulation(ctx, plots_folder: str, frames_per_second: Optional[int], output_name: str):
    # Extract the options from ctx
    output_folder = ctx.obj["output_folder"]
    verbose = ctx.obj["verbose"]

    assert _is_tool("gifski"), "Gifski is not available on the PATH. Install and add it to the path"
    
    # Single process
    # gifski -o simulation_1741866740.gif simulation_1741866740/tranches/00000/logs/plots/*.png
    output_file = os.path.join(output_folder, f"{output_name}.gif")

    gif_options = list()
    gif_options += ["-o", f"{output_file}"]
    if frames_per_second is not None:
        gif_options += ["--fps", f"{frames_per_second}"]
    gif_options += [f"{plots_folder}/*.png"]

    exit_code = subprocess.check_call(f"gifski {' '.join(gif_options)}", shell=True)
    
    assert exit_code == 0, "Something went wrong while generating the gif"


