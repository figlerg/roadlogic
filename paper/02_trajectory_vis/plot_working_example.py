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

from matplotlib import rcParams
import xml.etree.ElementTree as ET
import shutil



# LaTeX-friendly settings (vector fonts, serif)
rcParams.update({
    "text.usetex": True,
    "font.family": "serif",
    "font.serif": ["Computer Modern Roman"],
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})


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

# Mapping für Lanelets
lanelet_id_map = {
    "3": "13",
    "2": "12",
    "1": "11",
}

# Mapping für dynamische Hindernisse
dyn_obs_id_map = {
    "6645615": "1",
    "1667330609": "2",
    "161867879": "3"
}


def remap_commonroad_ids(path_in: str, path_out: str):
    tree = ET.parse(path_in)
    root = tree.getroot()

    # --- Lanelet-IDs und ihre Referenzen anpassen ---
    for lanelet in root.findall(".//lanelet"):
        lid = lanelet.get("id")
        if lid in lanelet_id_map:
            lanelet.set("id", lanelet_id_map[lid])

        # adjacentLeft/Right ref anpassen
        for adj_tag in ("adjacentLeft", "adjacentRight"):
            for adj in lanelet.findall(adj_tag):
                ref = adj.get("ref")
                if ref in lanelet_id_map:
                    adj.set("ref", lanelet_id_map[ref])

    # --- dynamicObstacle-IDs anpassen ---
    for dyn in root.findall(".//dynamicObstacle"):
        did = dyn.get("id")
        if did in dyn_obs_id_map:
            dyn.set("id", dyn_obs_id_map[did])

    # (Optional) planningProblem-IDs mitziehen, falls gewünscht:
    for pp in root.findall(".//planningProblem"):
        pid = pp.get("id")
        if pid in dyn_obs_id_map:
            pp.set("id", dyn_obs_id_map[pid])

    tree.write(path_out, encoding="UTF-8", xml_declaration=True)

def remap_commonroad_ids_inplace(path: str, keep_backup: bool = True):
    tmp_path = path + ".tmp"
    bak_path = path + ".bak"

    # write remapped XML to tmp
    remap_commonroad_ids(path, tmp_path)

    # optional backup
    if keep_backup:
        if not os.path.exists(bak_path):
            shutil.copy2(path, bak_path)

    # atomic replace
    os.replace(tmp_path, path)



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


    ax.set_xlim((-5, 70))

    plt.savefig(f"{output_file}", bbox_inches='tight')
    plt.close()

if __name__ == "__main__":

    ### PLOT 1: overtake scenario
    # scenario_file = os.path.join("paper/02_trajectory_vis/01_overtake_scenario.xml")
    # executed_scenario_file = os.path.join("paper/02_trajectory_vis/01_overtake_executed_scenario.xml")
    # scenario_file = os.path.join("paper/02_trajectory_vis/01_overtake/out/cr_simulations/scenario_0002/simulation_00001/scenario.xml")
    # executed_scenario_file = os.path.join("paper/02_trajectory_vis/01_overtake/out/cr_simulations/scenario_0002/simulation_00001/executed_scenario.xml")
    scenario_file = os.path.join("paper/02_trajectory_vis/01_overtake/out/cr_simulations/scenario_0002/simulation_00001/scenario.xml")
    executed_scenario_file = os.path.join("paper/02_trajectory_vis/01_overtake/out/cr_simulations/scenario_0002/simulation_00001/executed_scenario.xml")

    remap_commonroad_ids_inplace(scenario_file)
    remap_commonroad_ids_inplace(executed_scenario_file)

    _, planning_problem_set = XMLFileReader(scenario_file).open()
    executed_scenario, _ = XMLFileReader(executed_scenario_file).open()

    # output_file = os.path.join("paper/02_trajectory_vis/01_overtake_trajectory.pdf")
    output_file = os.path.join("paper/figures/Fig_1_alt.pdf")

    target_time_step = 80  # Last timestep

    # Plot the past shaded boxes at those timesteps
    plot_at_times = [10, 20, 30, 40, 50, 60, 70]

    # Plot the figure to file
    visualize_the_scenario(executed_scenario, planning_problem_set, output_file, target_time_step, plot_at_times)


    ### PLOT 1 ORIGINAL
    scenario_file = os.path.join("paper/bckp/01_overtake_scenario.xml")
    executed_scenario_file = os.path.join("paper/bckp/01_overtake_executed_scenario.xml")

    remap_commonroad_ids_inplace(scenario_file)
    remap_commonroad_ids_inplace(executed_scenario_file)

    _, planning_problem_set = XMLFileReader(scenario_file).open()
    executed_scenario, _ = XMLFileReader(executed_scenario_file).open()

    # output_file = os.path.join("paper/02_trajectory_vis/01_overtake_trajectory.pdf")
    output_file = os.path.join("paper/figures/Fig_1.pdf")

    target_time_step = 90  # Last timestep

    # Plot the past shaded boxes at those timesteps
    plot_at_times = [10, 20, 30, 40, 50, 60, 70, 80]

    # Plot the figure to file
    visualize_the_scenario(executed_scenario, planning_problem_set, output_file, target_time_step, plot_at_times)



    ### PLOT 2: overtake scenario (fake overtake)
    # Remap in place in the simulation folder so animations keep working with better labels
    scenario_file_src = os.path.join(
        "paper/02_trajectory_vis/02_fake_overtake/out/cr_simulations/scenario_0001/simulation_00001/scenario.xml"
    )
    executed_scenario_file_src = os.path.join(
        "paper/02_trajectory_vis/02_fake_overtake/out/cr_simulations/scenario_0001/simulation_00001/executed_scenario.xml"
    )

    remap_commonroad_ids_inplace(scenario_file_src)
    remap_commonroad_ids_inplace(executed_scenario_file_src)

    _, planning_problem_set = XMLFileReader(scenario_file_src).open()
    executed_scenario, _ = XMLFileReader(executed_scenario_file_src).open()

    output_file = os.path.join("paper/figures/Fig_9.pdf")

    target_time_step = 68  # Last timestep

    # Plot the past shaded boxes at those timesteps
    plot_at_times = [10, 20, 30, 40, 50, 60]

    # Plot the figure to file
    visualize_the_scenario(executed_scenario, planning_problem_set, output_file, target_time_step, plot_at_times)



    ### PLOT 3: diversity comparison

    ### PLOT 3a
    scenario_file_src = os.path.join(
        "paper/02_trajectory_vis/03_similarity/out/cr_simulations/"
        "scenario_change_dur_3__init_distance_11__max_acceleration_while_turning_0__"
        "max_braking_speed_while_turning_2__max_lane_3__max_segment_300__safety_distance_5/"
        "simulation_00001/scenario.xml"
    )
    executed_scenario_file_src = os.path.join(
        "paper/02_trajectory_vis/03_similarity/out/cr_simulations/"
        "scenario_change_dur_3__init_distance_11__max_acceleration_while_turning_0__"
        "max_braking_speed_while_turning_2__max_lane_3__max_segment_300__safety_distance_5/"
        "simulation_00001/executed_scenario.xml"
    )

    remap_commonroad_ids_inplace(scenario_file_src)
    remap_commonroad_ids_inplace(executed_scenario_file_src)

    _, planning_problem_set = XMLFileReader(scenario_file_src).open()
    executed_scenario, _ = XMLFileReader(executed_scenario_file_src).open()

    output_file = os.path.join("paper/figures/Fig_7a.pdf")

    target_time_step = 80
    plot_at_times = [10, 20, 30, 40, 50, 70]

    visualize_the_scenario(
        executed_scenario,
        planning_problem_set,
        output_file,
        target_time_step,
        plot_at_times
    )



    ### PLOT 3b
    # scenario_file_src = os.path.join(
    #     "paper/02_trajectory_vis/03_similarity/out/cr_simulations/"
    #     "scenario_change_dur_3__init_distance_11__max_acceleration_while_turning_2__"
    #     "max_braking_speed_while_turning_4__max_lane_3__max_segment_300__safety_distance_5/"
    #     "simulation_00001/scenario.xml"
    # )
    # executed_scenario_file_src = os.path.join(
    #     "paper/02_trajectory_vis/03_similarity/out/cr_simulations/"
    #     "scenario_change_dur_3__init_distance_11__max_acceleration_while_turning_2__"
    #     "max_braking_speed_while_turning_4__max_lane_3__max_segment_300__safety_distance_5/"
    #     "simulation_00001/executed_scenario.xml"
    # )

    # remap_commonroad_ids_inplace(scenario_file_src)
    # remap_commonroad_ids_inplace(executed_scenario_file_src)

    # _, planning_problem_set = XMLFileReader(scenario_file_src).open()
    # executed_scenario, _ = XMLFileReader(executed_scenario_file_src).open()

    # output_file = os.path.join("paper/figures/Fig_7b.pdf")

    # target_time_step = 23
    # plot_at_times = [5, 14]

    # visualize_the_scenario(
    #     executed_scenario,
    #     planning_problem_set,
    #     output_file,
    #     target_time_step,
    #     plot_at_times
    # )



    ### PLOT 3c
    scenario_file_src = os.path.join(
        "paper/02_trajectory_vis/03_similarity/out/cr_simulations/"
        "scenario_change_dur_3__init_distance_16__max_acceleration_while_turning_0__"
        "max_braking_speed_while_turning_3__max_lane_3__max_segment_300__safety_distance_5/"
        "simulation_00001/scenario.xml"
    )
    executed_scenario_file_src = os.path.join(
        "paper/02_trajectory_vis/03_similarity/out/cr_simulations/"
        "scenario_change_dur_3__init_distance_16__max_acceleration_while_turning_0__"
        "max_braking_speed_while_turning_3__max_lane_3__max_segment_300__safety_distance_5/"
        "simulation_00001/executed_scenario.xml"
    )

    remap_commonroad_ids_inplace(scenario_file_src)
    remap_commonroad_ids_inplace(executed_scenario_file_src)

    _, planning_problem_set = XMLFileReader(scenario_file_src).open()
    executed_scenario, _ = XMLFileReader(executed_scenario_file_src).open()

    output_file = os.path.join("paper/figures/Fig_7c.pdf")

    target_time_step = 75
    plot_at_times = [10, 20, 30, 40, 50, 60, 70]

    visualize_the_scenario(
        executed_scenario,
        planning_problem_set,
        output_file,
        target_time_step,
        plot_at_times
    )



    ### PLOT 3d
    scenario_file_src = (
        "paper/02_trajectory_vis/03_similarity/out/cr_simulations/"
        "scenario_change_dur_3__init_distance_12__max_acceleration_while_turning_0__"
        "max_braking_speed_while_turning_2__max_lane_3__max_segment_300__safety_distance_5/"
        "simulation_00001/scenario.xml"
    )
    executed_scenario_file_src = (
        "paper/02_trajectory_vis/03_similarity/out/cr_simulations/"
        "scenario_change_dur_3__init_distance_12__max_acceleration_while_turning_0__"
        "max_braking_speed_while_turning_2__max_lane_3__max_segment_300__safety_distance_5/"
        "simulation_00001/executed_scenario.xml"
    )

    remap_commonroad_ids_inplace(scenario_file_src)
    remap_commonroad_ids_inplace(executed_scenario_file_src)

    _, planning_problem_set = XMLFileReader(scenario_file_src).open()
    executed_scenario, _ = XMLFileReader(executed_scenario_file_src).open()

    output_file = os.path.join("paper/figures/Fig_7b.pdf")

    target_time_step = 75
    plot_at_times = [10, 20, 30, 40, 50, 60, 70]

    visualize_the_scenario(
        executed_scenario,
        planning_problem_set,
        output_file,
        target_time_step,
        plot_at_times
    )


    recreate_anims = False

    if recreate_anims:

        ### fetch the animations

        dst_root = os.path.join("paper", "animations")
        os.makedirs(dst_root, exist_ok=True)

        # Use exact source paths (no base_dir/scenario_dir splitting)
        PLOTS = {
            "Fig_1": "paper/02_trajectory_vis/01_overtake/out/cr_simulations/scenario_0002/simulation_00001/simulation.gif",
            "Fig_4": "paper/01_model_vis/model_vis_plots/anim_stitched.gif",

            "Fig_9":  "paper/02_trajectory_vis/02_fake_overtake/out/cr_simulations/scenario_0001/simulation_00001/simulation.gif",

            "Fig_7a": "paper/02_trajectory_vis/03_similarity/out/cr_simulations/"
                    "scenario_change_dur_3__init_distance_11__max_acceleration_while_turning_0__"
                    "max_braking_speed_while_turning_2__max_lane_3__max_segment_300__safety_distance_5/"
                    "simulation_00001/simulation.gif",

            # ignore 3b

            "Fig_7c": "paper/02_trajectory_vis/03_similarity/out/cr_simulations/"
                    "scenario_change_dur_3__init_distance_16__max_acceleration_while_turning_0__"
                    "max_braking_speed_while_turning_3__max_lane_3__max_segment_300__safety_distance_5/"
                    "simulation_00001/simulation.gif",

            "Fig_7b": "paper/02_trajectory_vis/03_similarity/out/cr_simulations/"
                    "scenario_change_dur_3__init_distance_12__max_acceleration_while_turning_0__"
                    "max_braking_speed_while_turning_2__max_lane_3__max_segment_300__safety_distance_5/"
                    "simulation_00001/simulation.gif",
        }

        copied = 0
        for fig_name, src in PLOTS.items():
            if not os.path.exists(src):
                print(f"[fetch_gifs] missing: {src}")
                continue

            dst = os.path.join(dst_root, f"{fig_name}.gif")
            shutil.copy2(src, dst)
            copied += 1

        print(f"[fetch_gifs] copied {copied}/{len(PLOTS)} animation files to {dst_root}")
