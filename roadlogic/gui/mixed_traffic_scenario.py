#
# this page should render a commonroad scenario (only a road) and let user drag and drop the 
#   pointers corresponding to the vehicles so they can drag and drop them onto the map.
#   TODO Make sure there are waypoints
#   TODO: Currently the markers are not visible, needs some debugging, some plugins might be missing 
#
#
#
#
import mpld3
import uuid
import os
import matplotlib
import matplotlib.pyplot as plt

from commonroad.common.file_reader import XMLFileReader
from commonroad.visualization.mp_renderer import MPRenderer
from commonroad.scenario.scenario import Scenario

# https://github.com/zauberzeug/nicegui/discussions/359
from nicegui import ui


# TODO Move this to an util module
def get_colors():
    from matplotlib.cm import get_cmap
    _name = "Accent"
    _cmap = get_cmap(_name)  # type: matplotlib.colors.ListedColormap
    # TODO Those must be HEX Strings?
    # THIS HAS ONLY 8 COLORS!
    return _cmap.colors  # type: list


def generate_scenario_designer(scenario: Scenario, generate_button_html_id, scenario_data={}, max_vehicles_in_scenario=3):
    """
    Generate the interactive visualization of the Scenario with preloaded (hidden) max_player markers.
    Use scenario_data to position the markers and configure the initial values of the form

    TODO Ideally, the markers should be placed in the middle of the actual figure. This could be probably done
    with a plugin

    TODO Max player is 8 because the cmap has 8 entries!

    TODO Use different icons for User/AV
    :return:
    """
    fig, ax = plt.subplots(figsize=(8, 3))

    try:
        # Render the scenario, i.e., the road layout, without showing it yet
        rnd = MPRenderer(ax=ax)
        scenario.draw(rnd)
        rnd.render(show=False)

        # Generate the placeholder/markers - independently as they cannot be easily modified later!
        initial_state_points = []
        goal_area_points = []
        colors = []
        # Note: Since we stack the one on top of the other, they steal the mouseover, not we put them one beside the other.
        # Can try to reverse their generation, but keep their order in the final array, or move them one aside the other

        # Keep the limits for the map
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        bottom_left_corner = [xlim[0], ylim[0]]

        initial_state_data = []
        goal_area_data = []

        # Avoid stupid mistakes
        if scenario_data is None:
            scenario_data = {}

        # Initialize the scenario data with the default values or the existing ones
        for driver_index in range(max_vehicles_in_scenario):
            color = get_colors()[ driver_index ]

            # Assume the driver is not visible
            scenario_data[f"{driver_index}_is_visible"] = False

            # Initial State for the driver
            if f"{driver_index}_x_is" not in scenario_data:
                scenario_data[f"{driver_index}_x_is"] = bottom_left_corner[0] + driver_index * 2.0
            else:
                scenario_data[f"{driver_index}_is_visible"] = True

            if f"{driver_index}_y_is" not in scenario_data:
                scenario_data[f"{driver_index}_y_is"] = bottom_left_corner[1]
            else:
                scenario_data[f"{driver_index}_is_visible"] = True

            if f"{driver_index}_v_is" not in scenario_data:
                scenario_data[f"{driver_index}_v_is"] = 45.0
            else:
                scenario_data[f"{driver_index}_is_visible"] = True

            if f"{driver_index}_typology" not in scenario_data:
                scenario_data[f"{driver_index}_typology"] = "human"
            else:
                scenario_data[f"{driver_index}_is_visible"] = True

            # Goal Area for the driver
            if f"{driver_index}_x_ga" not in scenario_data:
                scenario_data[f"{driver_index}_x_ga"] = bottom_left_corner[0] + driver_index * 2.0
            else:
                scenario_data[f"{driver_index}_is_visible"] = True

            if f"{driver_index}_y_ga" not in scenario_data:
                scenario_data[f"{driver_index}_y_ga"] = bottom_left_corner[1] -2.0
            else:
                scenario_data[f"{driver_index}_is_visible"] = True

            # At this point scenario data contains either the past values or the default ones
            # The scenario data also contains a flag to force the vehicle visibility

            # Plot the markers

            # Round marker - Initial State
            x_is = float(scenario_data[f"{driver_index}_x_is"])
            y_is = float(scenario_data[f"{driver_index}_y_is"])

            initial_state_points.append(ax.plot(x_is, y_is, 'o', color= color, mec='k', ms=15, mew=1, alpha=0.0, zorder=52)[0])

            # Squared marker
            x_ga = float(scenario_data[f"{driver_index}_x_ga"])
            y_ga = float(scenario_data[f"{driver_index}_y_ga"])

            goal_area_points.append(ax.plot(x_ga, y_ga, 's', color= color, mec='k', ms=15, mew=1, alpha=0.0, zorder=52)[0])

            # Remember the colors as well
            colors.append(color)

        # Isn't it better to pass the scenario data directly here?! So the plugin can setup whatever it likes?
        mpld3.plugins.connect(fig, RoadLogicScenarioEditor(
            initial_state_points, goal_area_points, scenario_data, colors))

        html_snippet = mpld3.fig_to_html(fig)

    finally:
        plt.close(fig)

    return html_snippet


# Basic plugin to bind to the generate button

def read_plugin_js(local_file_name):
    directory_containing_this_script = os.path.dirname(os.path.realpath(__file__))
    file_name = os.path.join(directory_containing_this_script, local_file_name)

    with open(file_name, "r") as js_file:
        return "\n".join(js_file.readlines())


class RoadLogicScenarioEditor(mpld3.plugins.PluginBase):
    """
    Based on NewScenarioDragAndDrop
    """

    JAVASCRIPT = read_plugin_js("roadlogic_scenario_editor.js")

    def __init__(self, figure_id: str, container_id: str,
                 generate_button_id: str, add_vehicle_button_id: str, reset_button_id: str, show_dialog_button_id: str,
                 add_waypoint_button_id: str, select_player_id: str, update_select_button_id: str,
                 initial_state_points: list, waypoints: list, scenario_data: dict, colors: list):
        
        def get_collections_of_ids(collections_of_points):
            collections_of_ids = []
            for points in collections_of_points:
                if isinstance(points, matplotlib.lines.Line2D):
                    suffix = "pts"
                else:
                    suffix = None
                collections_of_ids.append(mpld3.utils.get_id(points, suffix))
            return collections_of_ids
        
        # We need to pre-render the markers to enable drag and drop, they are generated in the figure associated to this plugin
        #   but we need to retrieve their ids to pass them to the plugin
        
        self.dict_ = {"type": "roadlogic_scenario_editor",
                      "figure_id": figure_id,
                      "container_id": container_id,
                      "generate_button_id": generate_button_id,
                      "add_vehicle_button_id": add_vehicle_button_id,
                      "reset_button_id": reset_button_id,
                      "show_dialog_button_id": show_dialog_button_id,
                      "add_waypoint_button_id": add_waypoint_button_id,
                      "select_player_id": select_player_id,
                      "update_select_button_id": update_select_button_id,
                      "initial_state_ids": get_collections_of_ids(initial_state_points),
                      "waypoint_ids": get_collections_of_ids(waypoints),
                      "scenario_data": scenario_data,
                      "colors": colors
                      }

from commonroad.planning.planning_problem import PlanningProblem, PlanningProblemSet, GoalRegion
from commonroad.scenario.state import InitialState, ExtendedPMState, Interval
from copy import deepcopy
import numpy as np
from commonroad.scenario.lanelet import Lanelet
from commonroad.geometry.shape import Rectangle
from commonroad.common.file_writer import XMLFileWriter

async def generate_the_scenario(scenario_editor_unique_id, base_commonroad_scenario: Scenario):
    # Read the scenario data as dictionary
    # try:
        scenario_data: dict = await ui.run_javascript(f"document.getElementById('{scenario_editor_unique_id}').scenario_data")
        # Extract the planning problems of the vehicles
        scenario = deepcopy(base_commonroad_scenario)
        planning_problem_list = []
        for vehicle_index, vehicle_data in scenario_data.items():
            planning_problem_id = scenario.generate_object_id()
            initial_position_x = scenario_data[vehicle_index]["initial_state"]["x"]
            initial_position_y = scenario_data[vehicle_index]["initial_state"]["y"]
            initial_velocity = scenario_data[vehicle_index]["initial_state"]["v"]
            initial_lanelet: Lanelet = scenario.lanelet_network.find_lanelet_by_id(scenario.lanelet_network.find_lanelet_by_position([np.array([initial_position_x, initial_position_y])])[0][0])
            initial_orientation = initial_lanelet.orientation_by_position(np.array([initial_position_x, initial_position_y]))
            initial_acceleration = 0.0
            initial_yaw_rate = 0.0
            initial_slip_angle = 0.0
            initial_time_step = 0
            initial_state = InitialState(time_step=initial_time_step, 
                        position=np.array([initial_position_x, initial_position_y]),
                        orientation=initial_orientation, 
                        velocity=initial_velocity, 
                        acceleration=initial_acceleration,
                        yaw_rate=initial_yaw_rate,
                        slip_angle=initial_slip_angle)
            goal_states = []
            for waypoint in vehicle_data["waypoints"]:
                waypoint_time_step = int(waypoint["t"] / scenario.dt)
                waypoint_x = waypoint["x"]
                waypoint_y = waypoint["y"]
                waypoint_lanelet: Lanelet = scenario.lanelet_network.find_lanelet_by_id(scenario.lanelet_network.find_lanelet_by_position([np.array([waypoint_x, waypoint_y])])[0][0])
                waypoint_orientation = waypoint_lanelet.orientation_by_position(np.array([waypoint_x, waypoint_y]))
                waypoint_rect = Rectangle(1., 2., np.array([waypoint_x, waypoint_y]), waypoint_orientation)  # work, but may mess with timing because too long
                # Allow a +/- 2 sec slack
                goal_state = ExtendedPMState(time_step=Interval(max(0, waypoint_time_step-20), waypoint_time_step+20), position=waypoint_rect, velocity=None)
                goal_states.append(goal_state)
            
            goal_states = sorted(goal_states, key=lambda gs : gs.time_step.start)

            goal_region = GoalRegion(goal_states)
            planning_problem_list.append(PlanningProblem(planning_problem_id, initial_state, goal_region))
        # Generate the scenario XML file or report an error
        planning_problem_set = PlanningProblemSet(planning_problem_list)
        # TODO Fix this one
        random_file_name = os.path.join(os.path.abspath('.'), "roadlogic", "output", f"{uuid.uuid4()}.xml")
        print(f"Scenario stored at: {random_file_name}")
        XMLFileWriter(scenario=scenario, planning_problem_set=planning_problem_set).write_to_file(random_file_name, check_validity=True)
        # Let use download
        ui.download.file(random_file_name, filename="scenario.xml")
    # except Exception as exc:
        # ui.notify(f'Cannot generate the scenario. Exception {exc}')

async def update_input_state_and_close_dialog(scenario_editor_unique_id: str, vehicle_index: int, dialog: ui.dialog, velocity_slider: ui.slider, vehicle_model_select: ui.select):
    velocity = float(velocity_slider.value)
    await ui.run_javascript(f"document.getElementById('{scenario_editor_unique_id}').scenario_data[{vehicle_index}]['initial_state']['v'] = {velocity}")
    vehicle_model = vehicle_model_select.value
    await ui.run_javascript(f"document.getElementById('{scenario_editor_unique_id}').scenario_data[{vehicle_index}]['vehicle_model'] = '{vehicle_model}'")
    dialog.close()

async def update_waypoint_and_close_dialog(scenario_editor_unique_id: str, vehicle_index: int, waypoint_index: int, dialog: ui.dialog, time_slider: ui.slider):
    # Close and update the value of the shared data
    time = float(time_slider.value)
    await ui.run_javascript(f"document.getElementById('{scenario_editor_unique_id}').scenario_data[{vehicle_index}]['waypoints']['{waypoint_index}']['t'] = {time}")
    dialog.close()

async def remove_vehicle(scenario_editor_unique_id: str, vehicle_index: int, dialog: ui.dialog):
    # Invoke the javascript function associated to this element for hiding a player
    await ui.run_javascript(f"document.getElementById('{scenario_editor_unique_id}').hide_player({vehicle_index})")
    # Close the modal dialog
    dialog.close()

async def remove_waypoint(scenario_editor_unique_id: str, vehicle_index: int, waypoint_index: int, dialog: ui.dialog):
    # Invoke the javascript function associated to this element for hiding a player
    await ui.run_javascript(f"document.getElementById('{scenario_editor_unique_id}').hide_waypoint({vehicle_index},{waypoint_index})")
    # Close the modal dialog
    dialog.close()

async def update_the_select(scenario_editor_unique_id: str, select_player: ui.select):
    # Get the data about scenario, it contains only the visible players
    scenario_data = await ui.run_javascript(f"document.getElementById('{scenario_editor_unique_id}').scenario_data")
    visible_vehicles = [vehicle_index for vehicle_index in scenario_data.keys()]
    # Update the select option
    selected_value = select_player.value if select_player.value in visible_vehicles else "None"
    select_player.set_options(["None"] + visible_vehicles, value=selected_value)
    select_player.update()

async def toggle_add_waypoint_button(select_player: ui.select, add_waypoint_button: ui.button):
    if select_player.value != "None":
        add_waypoint_button.enable()
    else:
        add_waypoint_button.disable()

def setup_modal_for_initial_state(dialog: ui.dialog, scenario_editor_unique_id:str, modal_data: dict):
    # Title
    ui.label("Edit the Initial State").classes('text-h6')
    # Content.    
    with ui.grid(columns=2) as grid:
        # Extract Vehicle and Color
        ui.label(f"Vehicle")
        ui.label(f"{modal_data['vehicle_index']}").style(f"background-color: rgb({modal_data['color']['r']}, {modal_data['color']['g']}, {modal_data['color']['b']})")
        ui.label(f"Model")
        vehicle_model_select = ui.select(options=["car", "truck"], value=modal_data['vehicle_model'])
        # Leave some blank space
        ui.label('')
        ui.label('')
        #
        ui.label(f"Initial Position (m,m)")
        ui.label(f"({round(float(modal_data['initial_state']['x']),2)},{round(float(modal_data['initial_state']['y']),2)})")
        # Extract Speed
        ui.label(f"Initial Velocity (Km/h)")
        # ui.label(f"{modal_data['initial_state']['v']} Km/h")
        velocity_slider = ui.slider(min=0, max=200, value=float(modal_data['initial_state']['v'])).props('label-always')
    
    ui.button("Save", on_click=lambda : update_input_state_and_close_dialog(scenario_editor_unique_id, modal_data["vehicle_index"], dialog, velocity_slider, vehicle_model_select))
    ui.button("Remove Vehicle", on_click=lambda : remove_vehicle(scenario_editor_unique_id, modal_data["vehicle_index"], dialog))

def setup_modal_for_waypoint(dialog: ui.dialog, scenario_editor_unique_id:str, modal_data: dict):
    # Title
    ui.label("Edit the Waypoint").classes('text-h6')
    with ui.grid(columns=2) as grid:
        # Extract Vehicle and Color
        ui.label(f"Vehicle")
        ui.label(f"{modal_data['vehicle_index']}").style(f"background-color: rgb({modal_data['color']['r']}, {modal_data['color']['g']}, {modal_data['color']['b']})")
        # Leave some blank space
        ui.label('')
        ui.label('')
        # Position (not editable)
        ui.label("Position (m, m)")
        ui.label(f"({round(float(modal_data['waypoint']['x']),2)},{round(float(modal_data['waypoint']['y']),2)})")
        # Extract Time
        ui.label(f"Time (sec)")
        # ui.label(f"{modal_data['initial_state']['v']} Km/h")
        time_slider = ui.slider(min=0.0, max=60.0, step=0.1, value=modal_data['waypoint']['t']).props('label-always')
    
    ui.button("Save", on_click=lambda : update_waypoint_and_close_dialog(scenario_editor_unique_id, modal_data["vehicle_index"], modal_data["waypoint_index"], dialog, time_slider))
    ui.button("Remove Waypoint", on_click=lambda : remove_waypoint(scenario_editor_unique_id, modal_data["vehicle_index"], modal_data["waypoint_index"], dialog))

async def create_the_modal_dialog(scenario_editor_unique_id):
    modal_data = await ui.run_javascript(f"document.getElementById('{scenario_editor_unique_id}').modal_data")
    
    # Do not show anything if there's nothing to show
    if "initial_state" not in modal_data and "waypoint" not in modal_data:
        return

    with ui.dialog() as dialog, ui.card():
        if "initial_state" in modal_data:
            setup_modal_for_initial_state(dialog, scenario_editor_unique_id, modal_data)
                        
        elif "waypoint" in modal_data:
            setup_modal_for_waypoint(dialog, scenario_editor_unique_id, modal_data)

    
    dialog.open()

    # // Data for the modal dialog box
    #                     the_figure.modal_data = {}
    #                     the_figure.modal_data["vehicle"] = index
    #                     the_figure.modal_data["color"] = {
    #                         "r" : (colors[index][0] * 255.0).toFixed(1);
    #                         "g" : (colors[index][1] * 255.0).toFixed(1);
    #                         "b" : (colors[index][2] * 255.0).toFixed(1);
    #                     }
    #                     the_figure.modal_data["initial_state"] = {}
    #                     the_figure.modal_data["initial_state"]["v"] = the_figure.scenario_data[index]["initial_state"]["v"]

def scenario_editor(map_file: str, container: ui.element, max_vehicles = 3):
    """
    Generate the scenario editing plugin and link it to the external buttons
    """
    try:
        # Render the figure
        scenario, _ = XMLFileReader(map_file).open()
    
        scenario_editor_unique_id = f"fig_{uuid.uuid4()}"


        with ui.button_group():
            generate_button = ui.button("Generate", on_click=lambda : generate_the_scenario(scenario_editor_unique_id, scenario))
            add_vehicle_button = ui.button("Add Vehicle")
            with ui.button_group():
                add_waypoint_button = ui.button("Add Waypoint")
                select_player = ui.select([], on_change= lambda e : toggle_add_waypoint_button(e.sender, add_waypoint_button))

            reset_button = ui.button("Reset")

        # This dialog allows to visualize and update the parameters of the selected vehicle
        show_dialog_button = ui.button("Show Editor", on_click=lambda : create_the_modal_dialog(scenario_editor_unique_id))
        # Pretend this is invisible
        show_dialog_button.style("opacity: 0")
        # We cannot use the following, as it completely disable the button
        # show_dialog_button.visible = False
        update_select_button = ui.button("Update Select", on_click=lambda: update_the_select(scenario_editor_unique_id, select_player))
        update_select_button.style("opacity: 0")

        # Setting the size of the plot is tricky, it depends on the road shape
        fig, ax = plt.subplots(figsize=(10, 2))
        rnd = MPRenderer(ax=ax)
        scenario.draw(rnd)
        rnd.render(show=False)
        fig.tight_layout()

        # Keep the limits for the map
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        bottom_left_corner = [xlim[0], ylim[0]]
        
        # Generate the placeholder/markers - independently as they cannot be easily modified later!
        initial_state_points = list()
        waypoints = list()
        colors = list()
        scenario_data = dict()

        vehicle_colors = get_colors()

        # Initialize the scenario data with default values for initial state and goal state for all the vehicles
        for driver_index in range(0, max_vehicles):
            color = vehicle_colors[ driver_index ]
            # TODO Do we really need scenario data? The original code used that to visualize existing scenarios, so it might be useful to keep it
            
            # Ensure the marker is not visible initially
            scenario_data[f"{driver_index}_is_visible"] = False
            # Show two lines of markers
            scenario_data[f"{driver_index}_x_is"] = bottom_left_corner[0] + driver_index * 2.0
            scenario_data[f"{driver_index}_y_is"] = bottom_left_corner[1]
            scenario_data[f"{driver_index}_v_is"] = 0.0

            scenario_data[f"{driver_index}_vehicle_model"] = "car"

            # We plot the markers to ensure they are included in the plugin as currently generate markers on the fly is not possible
            # Round marker - Initial State
            x_is = float(scenario_data[f"{driver_index}_x_is"])
            y_is = float(scenario_data[f"{driver_index}_y_is"])

            initial_state_points.append(ax.plot(x_is, y_is, 'o', color= color, mec='k', ms=15, mew=1, alpha=0.0, zorder=52)[0])
            
            # Squared marker - Waypoints
            # TODO Define variable instead of 3
            for waypoint_index in range(3):
                # TODO create all the waypoints here
                scenario_data[f"{driver_index}_{waypoint_index}_wp_x"] = bottom_left_corner[0] + driver_index * 2.0
                scenario_data[f"{driver_index}_{waypoint_index}_wp_y"] = bottom_left_corner[1] -2.0
                scenario_data[f"{driver_index}_{waypoint_index}_wp_t"] = 0.0
                scenario_data[f"{driver_index}_{waypoint_index}_wp_is_visible"] = False

                x_wp = float(scenario_data[f"{driver_index}_{waypoint_index}_wp_x"])
                y_wp = float(scenario_data[f"{driver_index}_{waypoint_index}_wp_y"])

                waypoints.append(ax.plot(x_wp, y_wp, 's', color= color, mec='k', ms=15, mew=1, alpha=0.0, zorder=52)[0])

            # Remember the color of the player as well
            colors.append(color)

        mpld3.plugins.connect(fig, RoadLogicScenarioEditor(figure_id=scenario_editor_unique_id, 
                                                           container_id=container.html_id,
                                                           generate_button_id=generate_button.html_id,
                                                           add_vehicle_button_id=add_vehicle_button.html_id,
                                                           reset_button_id=reset_button.html_id,
                                                           show_dialog_button_id = show_dialog_button.html_id,
                                                           add_waypoint_button_id=add_waypoint_button.html_id,
                                                           select_player_id=select_player.html_id,
                                                           update_select_button_id=update_select_button.html_id,
                                                           initial_state_points=initial_state_points,
                                                           waypoints=waypoints,
                                                           scenario_data=scenario_data,
                                                           colors=colors))
        
        # Add the HTML figure at the page level (so the plugin must take care of moving around)
        # The figid MUST start with fig_
        ui.add_body_html(mpld3.fig_to_html(fig, figid=scenario_editor_unique_id))
        
    finally:
        plt.close(fig)

    