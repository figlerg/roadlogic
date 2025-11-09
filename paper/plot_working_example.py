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

import colorsys


from commonroad.scenario.scenario import Scenario, DynamicObstacle
from commonroad.planning.planning_problem import PlanningProblemSet, PlanningProblem, GoalRegion
from commonroad.common.file_reader import XMLFileReader
from commonroad.prediction.prediction import Trajectory, TrajectoryPrediction

from commonroad.visualization.mp_renderer import MPDrawParams, MPRenderer


# Plot the scenario as follow:
# - Given a timestep plot the past time steps using a transparent color
# - Plot the occupancy at time step normal
# - Plot the trajectory if needed

def get_cmap(n, name='hsv'):
    return plt.cm.get_cmap(name, n)

def alter_color(color, amount=0.5):
    """
    Lightens or darkens the given color by multiplying (1-luminosity) by the given amount.
    Input can be matplotlib color string, hex string, or RGB tuple.

    See: https://stackoverflow.com/questions/37765197/darken-or-lighten-a-color-in-matplotlib
    """
    try:
        c = colors.cnames[color]
    except:
        c = color
    c = colorsys.rgb_to_hls(*colors.to_rgb(c))
    return colorsys.hls_to_rgb(c[0], 1 - amount * (1 - c[1]), c[2])

def visualize_the_scenario(executed_scenario: Scenario,
                           planning_problem_set: PlanningProblemSet,
                           output_file: str,
                           target_time_step: int,
                           plot_at_times: List[int]):
    """
    Plot the scenario at the given time_step
    """

    obstacles = sorted(executed_scenario.obstacles, key= lambda o : o.obstacle_id)

    unique_colors = get_cmap(len(obstacles), 'rainbow')

    color_mapping = dict()
    for i, obstacle in enumerate(obstacles):
        color_mapping[obstacle.obstacle_id] = colors.to_hex(unique_colors(i))
    
    fig = plt.figure(figsize=(10,5))
    ax = fig.gca()
    rnd = MPRenderer(ax=ax)

    # Render the road
    executed_scenario.lanelet_network.draw(rnd)

    # Render the trajectory and initial state (transparent)
    for obstacle in obstacles:
        # Set obstacle parameters
        obs_params = MPDrawParams()
        obs_params.dynamic_obstacle.draw_icon = False
        obs_params.dynamic_obstacle.show_label = True
        
        obs_params.dynamic_obstacle.time_begin = 0
        obs_params.dynamic_obstacle.time_end = max([s.time_step for s in obstacle.prediction.trajectory.state_list])

        # Color
        obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.facecolor = color_mapping[obstacle.obstacle_id]
        obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.edgecolor = "black"
        
        # Ensure this is draw above everything else
        obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.zorder = 200
        # Make it transparent
        obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.opacity = 0.2

        # No additional visuals
        obs_params.dynamic_obstacle.draw_direction = False
        obs_params.dynamic_obstacle.draw_signals = False
        
        # Draw a line instead
        obs_params.dynamic_obstacle.trajectory.draw_trajectory = True
        obs_params.dynamic_obstacle.trajectory.draw_continuous = True
        # # Make it lighter
        obs_params.dynamic_obstacle.trajectory.facecolor = color_mapping[obstacle.obstacle_id] # "black"
        obs_params.dynamic_obstacle.trajectory.line_width = 0.4

        # Finally render it
        obstacle.draw(rnd, draw_params=obs_params)

    # Draw history at given timesteps
    for obstacle in obstacles:
        for t in plot_at_times:
             if obstacle.occupancy_at_time(t) is not None:
                # Set obstacle parameters
                obs_params = MPDrawParams()
                obs_params.dynamic_obstacle.draw_icon = False
                obs_params.dynamic_obstacle.show_label = False
                
                obs_params.dynamic_obstacle.time_begin = t
                obs_params.dynamic_obstacle.time_end = t

                # Color
                obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.facecolor = color_mapping[obstacle.obstacle_id]
                obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.edgecolor = "black"
                
                # Ensure this is draw above everything else
                obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.zorder = 200
                # Make it transparent
                obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.opacity = 0.4

                # No additional visuals
                obs_params.dynamic_obstacle.draw_direction = False
                obs_params.dynamic_obstacle.draw_signals = False
                
                # Draw a line instead
                obs_params.dynamic_obstacle.trajectory.draw_trajectory = True
                obs_params.dynamic_obstacle.trajectory.draw_continuous = True
                # # Make it lighter
                obs_params.dynamic_obstacle.trajectory.facecolor = color_mapping[obstacle.obstacle_id] # "black"
                obs_params.dynamic_obstacle.trajectory.line_width = 0.4

                # Finally render it
                obstacle.draw(rnd, draw_params=obs_params)
    
    # Draw selected state
    for obstacle in obstacles:
        draw_at = target_time_step
        if target_time_step == -1:
            draw_at = max([s.time_step for s in obstacle.prediction.trajectory.state_list])

        if obstacle.occupancy_at_time(draw_at) is not None:
            # Set obstacle parameters
            obs_params = MPDrawParams()
            obs_params.dynamic_obstacle.draw_icon = True
            obs_params.dynamic_obstacle.show_label = False
            
            obs_params.dynamic_obstacle.time_begin = draw_at
            obs_params.dynamic_obstacle.time_end = draw_at

            # Color
            obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.facecolor = color_mapping[obstacle.obstacle_id]
            obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.edgecolor = "black"
            
            # Ensure this is draw above everything else
            # This is the right parameter when using the draw_icon
            obs_params.dynamic_obstacle.zorder = 230
            # obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.zorder = 220
            # obs_params.dynamic_obstacle.vehicle_shape.occupancy.shape.opacity = 1.0

            # No additional visuals
            obs_params.dynamic_obstacle.draw_direction = False
            obs_params.dynamic_obstacle.draw_signals = False
            
            # Do not draw the trajectory
            obs_params.dynamic_obstacle.trajectory.draw_trajectory = False

            # Finally render it
            obstacle.draw(rnd, draw_params=obs_params)

    # Render the scenario onto the plot
    rnd.render()

    # Add the waypoints as markers
    for obstacle in obstacles:
        if obstacle.obstacle_id in planning_problem_set.planning_problem_dict:
        
            planning_problem = planning_problem_set.planning_problem_dict[obstacle.obstacle_id]
            goal_region = planning_problem.goal

            for goal_state_index, goal_state in enumerate(goal_region.state_list):
                original_color = color_mapping[obstacle.obstacle_id]
                darker_color = alter_color(original_color, 1.5)
                marker_position_x, marker_position_y = goal_state.position.center[0], goal_state.position.center[1]
                ax.plot(marker_position_x, marker_position_y, "o", color=darker_color, ms=6, zorder=210)


    ax.set_xlim((-5, 55))

    plt.savefig(f"{output_file}", bbox_inches='tight')
    plt.close()

if __name__ == "__main__":

    current_folder = os.path.dirname(os.path.realpath(__file__))
    original_scenario_file = os.path.join(current_folder, "scenario.xml")
    executed_scenario_file = os.path.join(current_folder, "executed_scenario.xml")

    _, planning_problem_set = XMLFileReader(original_scenario_file).open()
    executed_scenario, _ = XMLFileReader(executed_scenario_file).open()

    output_file = os.path.join(current_folder, "working-example.png")

    target_time_step = -1 # Last timestep
    
    # Plot the past shaded boxes at those timesteps
    plot_at_times = [10, 20, 30, 40, 50, 60, 65]

    # Plot the figure to file
    visualize_the_scenario(executed_scenario, planning_problem_set, output_file, target_time_step, plot_at_times)