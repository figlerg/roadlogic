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

import matplotlib
import matplotlib.pyplot as plt

from commonroad.common.file_reader import XMLFileReader
from commonroad.visualization.mp_renderer import MPRenderer
from commonroad.scenario.scenario import Scenario

# https://github.com/zauberzeug/nicegui/discussions/359
from nicegui import ui


def generate_scenario_designer(scenario: Scenario, generate_button_html_id, scenario_data={}, max_players=8):
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
        for driver_index in range(0, max_players):
            color = vehicle_colors[ driver_index ]

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

class RoadLogicScenarioEditor(mpld3.plugins.PluginBase):
    """
    Based on NewScenarioDragAndDrop
    """

    JAVASCRIPT = r"""
        mpld3.register_plugin("roadlogic_scenario_editor", RoadLogicScenarioEditor);

        RoadLogicScenarioEditor.prototype = Object.create(mpld3.Plugin.prototype);

        RoadLogicScenarioEditor.prototype.constructor = RoadLogicScenarioEditor;

        RoadLogicScenarioEditor.prototype.requiredProps = ["figure_id",
                                                            "container_id",
                                                            "generate_button_id",
                                                            "add_vehicle_button_id",
                                                            "reset_button_id",
                                                            "initial_state_ids",
                                                            "goal_area_ids",
                                                            "scenario_data",
                                                            "colors"
                                                            ];

        RoadLogicScenarioEditor.prototype.defaultProps = {alpha_fill:0.6,
                                                        alpha_stroke:0.6,
                                                        hoffset:0,
                                                        voffset:10};
        
        // http://stackoverflow.com/questions/5525071/how-to-wait-until-an-element-exists
        function waitForElm(selector) {
            return new Promise(resolve => {
                if (document.getElementById(selector)) {
                    return resolve(document.getElementById(selector));
                }

                const observer = new MutationObserver(mutations => {
                    if (document.getElementById(selector)) {
                        observer.disconnect();
                        resolve(document.getElementById(selector));
                    }
                });

                // If you get "parameter 1 is not of type 'Node'" error, see https://stackoverflow.com/a/77855838/492336
                observer.observe(document.body, {
                    childList: true,
                    subtree: true
                });
            });
        }

        function RoadLogicScenarioEditor(fig, props){
            mpld3.Plugin.call(this, fig, props);
            // Ensure during dragging the markers are clearly and always visible; otherwise, their opacity should be 0.6
            mpld3.insert_css("#" + props.figure_id + " path.dragging",
                             {"fill-opacity": "1.0 !important",
                              "stroke-opacity": "1.0 !important"});
        };

        RoadLogicScenarioEditor.prototype.draw = async function(){

            // "global" variable to know which vehicle is selected
            var current_vehicle;

            // Look up and bind to the container and the generate button
            // The figure corresponding to this plugin
            const the_figure_id = this.props.figure_id
            var the_figure = document.getElementById(the_figure_id)

            // Those are the default data about the vehicles
            var initial_scenario_data = this.props.scenario_data;

            // Wait until the container that should contain this figure is ready
            var the_container = await waitForElm(this.props.container_id)
            // Move the figure inside the container
            the_container.insertBefore(the_figure, the_container.firstChild)
            
            // Find the buttons and link the functions
            var the_generate_button  = document.getElementById(this.props.generate_button_id)
            var the_add_vehicle_button  = document.getElementById(this.props.add_vehicle_button_id)
            var the_reset_button = document.getElementById(this.props.reset_button_id)

            // Create an global object storing data about the scenario.
            the_figure.scenario_data = {}
            
            // Create an object to store the visibility of the vehicles
            var player_visibility_flags= []

            // Get a reference of each of the marker objects. We store data directly inside them
            // The objects are initialized with the provided initial values
            var initial_state_objs = [];
            var goal_area_objs = []; 

            
            // Values data must be initialized here
            for( let i = 0; i < this.props.initial_state_ids.length; i++){
                var initial_state_obj = mpld3.get_element(this.props.initial_state_ids[i])
                initial_state_obj.data = [ initial_scenario_data[i + "_x_is"], initial_scenario_data[i + "_y_is"] ];
                initial_state_objs.push(initial_state_obj);
                
                var goal_area_obj = mpld3.get_element(this.props.goal_area_ids[i])
                goal_area_obj.data = [ initial_scenario_data[i + "_x_ga"], initial_scenario_data[i + "_y_ga"] ];
                goal_area_objs.push(goal_area_obj);
                
                player_visibility_flags[i] = initial_scenario_data[i + "_is_visible"];
            }

            // Not sure this is needed
            var colors = this.props.colors;
            
            var make_player_visible = function(index){
                // Change visibility of the markers for the vehicle index
                player_visibility_flags[index] = true;
                
                initial_state_objs[index].data = [ initial_scenario_data[index + "_x_is"], initial_scenario_data[index + "_y_is"] ];
                // TODO Link 0.6 to this.props
                initial_state_objs[index].pathsobj
                        .style("visibility", "visible")
                        .style("stroke-opacity", 0.6)
                        .style("fill-opacity", 0.6);
                goal_area_objs[index].data = [ initial_scenario_data[index + "_x_ga"], initial_scenario_data[index + "_y_ga"] ];
                // TODO Link 0.6 to this.props
                goal_area_objs[index].pathsobj
                        .style("visibility", "visible")
                        .style("stroke-opacity", 0.6)
                        .style("fill-opacity", 0.6);

                // Add the data
                the_figure.scenario_data[index] = {
                    "initial_state": {
                        "x" : initial_scenario_data[index + "_x_is"],
                        "y" : initial_scenario_data[index + "_y_is"],
                        "v" : initial_scenario_data[index + "_v_is"]
                    }, 
                    "goal_area" : {
                        "x" : initial_scenario_data[index + "_x_ga"],
                        "y" : initial_scenario_data[index + "_y_ga"]
                    }
                }

                add_controls(index);
            };
            
            the_add_vehicle_button.onclick = function(){
                // Take the first nonvisible vehicle and make it visible.
                for( let player_index = 0; player_index < player_visibility_flags.length; player_index++){
                    if (player_visibility_flags[player_index] == false){
                        make_player_visible(player_index);
                        break;
                    }
                }
                // Ensure button is enabled/disabled correctly
                the_add_vehicle_button.classList.add("disabled");
                for( let player_index = 0; player_index < player_visibility_flags.length; player_index++){
                    if (player_visibility_flags[player_index] == false){
                        the_add_vehicle_button.classList.remove("disabled");
                    }
                }
            }

            var hide_player = function(index){
                // Change visibility of the markers
                player_visibility_flags[index] = false;

                // Hide and move back to the initial position the markers                
                var is_obj = initial_state_objs[index];


                is_obj.pathsobj.style("visibility", "hidden");
                is_obj.pathsobj.attr("transform", "translate("+is_obj.offsetcoords.x(is_obj.data[0])+","+is_obj.offsetcoords.y(is_obj.data[1])+")");
               
                var ga_obj = goal_area_objs[index];
                // ga_obj.data = [ initial_scenario_data[index + "_x_ga"], initial_scenario_data[index + "_y_ga"] ]
                ga_obj.pathsobj.style("visibility", "hidden");
                ga_obj.pathsobj.attr("transform", "translate("+ga_obj.offsetcoords.x(ga_obj.data[0])+","+ga_obj.offsetcoords.y(ga_obj.data[1])+")");
                
                // After removing a vehicle, then the add vehicle button is definitively active
                the_add_vehicle_button.classList.remove("disabled")
                                
                // Remove the data
                delete the_figure.scenario_data[index]

                // Remove any control associated to this player?
            };

            // Build the modal/panel with the buttons used to configure the scenario variables

            // A reusable tooltip control pane
            const tooltip_id = "control-tooltip_for_" + the_figure_id
            // Define the container
            var tooltip = d3.select("body").append("div")
                    .attr("id", tooltip_id)
                    .attr("class", "mpld3-tooltip")
                    .style("position", "absolute")
                    .style("z-index", "400")
                    .style("visibility", "hidden")
                    .style("color", "black")
                    .style("background-color", "white")
                    .style("border-style", "solid")
                    .style("box-shadow", "5px 5px 5px black");
            
            // Access the tooltip as actual DOM element and not via the d3 library
            var the_tooltip = document.getElementById(tooltip_id)
            console.log("the_tooltip: " + the_tooltip)

            // Manually set the content of the tooltip
            the_tooltip.innerHTML = ` 
            <table>
                <thead>
                    <tr><th colspan="2" class="text-center">Vehicle's Parameters</th></tr>
                </thead>
                <tbody>
                    <tr>
                        <th>Speed</th>
                        <td>
                            <label id="speed-selector-label" for="speed-selector">?? Km/h</label>
                            <input type="range" id="speed-selector" name="speed-selector" min="0" max="90"/>
                        </td>
                    </tr>
                    <tr>
                        <th>Color</th>
                        <td id="vehicle-color"></td>
                    </tr>
                    <tr>
                        <td>
                            <a id="remove-btn" class="btn btn-info" role="button">Remove this vehicle</a>
                        </td>
                        <td>
                            <a id="close-vehicle-parameter-dialog" class="btn btn-info" role="button" onclick="tooltip.style('visibility', 'hidden');">Close Dialog</a>
                        </td>
                    </tr>
                </tbody>
            </table>`;
            
            
            // Drag and Drop common functionalities            
            var drag_started = function(d) {
                d3.event.sourceEvent.stopPropagation();
                d3.select(this).classed("dragging", true);
            }

            var drag_ended = function(d) {
                d3.select(this).classed("dragging", false);
            }

            var add_controls = function(index) {
                // Configure the vehicle-related functionalities
                console.log("Add control to vehicle " + index)

                //update the global variable - Necessary?
                current_vehicle = index;
                
                // We attach the tooltip to the initial state
                var initial_state_obj = initial_state_objs[index];
                var goal_area_obj = goal_area_objs[index];
                    
                console.log("initial_state_obj " + initial_state_obj)
                console.log("goal_area_obj " + goal_area_obj)

                // We attach the dragging and dropping functionalities to both the initial_state and goal_area
                            
                var initial_state_drag = d3.drag()
                    .subject(function(d) {
                                // Ensure we always refer to the stored stat of the object
                                return {
                                        x: initial_state_obj.ax.x(the_figure.scenario_data[index]["initial_state"]["x"]),
                                        y: initial_state_obj.ax.y(the_figure.scenario_data[index]["initial_state"]["y"])
                                }; 
                            }
                        )
                    .on("start", drag_started)
                    .on("drag", function(d) {
                                    // As long as we are dragging d ... 
                                    d.x = initial_state_obj.ax.x.invert(d3.event.x);
                                    d.y = initial_state_obj.ax.y.invert(d3.event.y);
                                    // Apply the translation to the element we are dragging to move it around
                                    d3.select(this).attr("transform", "translate(" + [d3.event.x, d3.event.y] + ")");
                                    // Update the scenario data
                                    the_figure.scenario_data[index]["initial_state"]["x"] = d.x
                                    the_figure.scenario_data[index]["initial_state"]["y"] = d.y
                                }
                        )
                    .on("end", drag_ended);
                
                var goal_area_drag = d3.drag()
                    .subject(function(d) {
                                // Ensure we always refer to the stored stat of the object
                                return {
                                        x: initial_state_obj.ax.x(the_figure.scenario_data[index]["goal_area"]["x"]),
                                        y: initial_state_obj.ax.y(the_figure.scenario_data[index]["goal_area"]["y"])
                                };
                            } 
                        )
                    .on("start", drag_started)
                    .on("drag", function(d) {
                            // As long as we are dragging d ... 
                            // TODO Update the inputs elements corresponding to d (d.id might be stored somewhere)
                            d.x = goal_area_obj.ax.x.invert(d3.event.x);
                            d.y = goal_area_obj.ax.y.invert(d3.event.y);
                            // Apply the translation to the element we are dragging to move it around
                            d3.select(this).attr("transform", "translate(" + [d3.event.x, d3.event.y] + ")");
                            //console.log("GA Dragged to " + d.x + ", " + d.y)
                            // Refresh the form - Assume this elements are there!
                            the_figure.scenario_data[index]["goal_area"]["x"] = d.x
                            the_figure.scenario_data[index]["goal_area"]["y"] = d.y
                        }
                    )
                    .on("end", drag_ended);
                
                initial_state_obj.elements()
                    .style("cursor", "default")
                    .call(initial_state_drag);
                
                goal_area_obj.elements()
                    .style("cursor", "default")
                    .call(goal_area_drag);
            }

            var reset_scenario = function(){
                for( let player_index = 0; player_index < player_visibility_flags.length; player_index++){
                    // TODO Should hide_player remove the controls for dragging and tooltip?
                    hide_player(player_index)
                    if ( initial_scenario_data[player_index + "_is_visible"] ){
                        make_player_visible(player_index)
                    }
                }
            }

            the_reset_button.onclick = reset_scenario
            
            // Invoke the scenario initialization
            reset_scenario()
        };
    """

    def __init__(self, figure_id: str, container_id: str, generate_button_id: str, add_vehicle_button_id: str, reset_button_id: str,
                 initial_state_points: list, goal_area_points: list, scenario_data: dict, colors: list):
        
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
                      "initial_state_ids": get_collections_of_ids(initial_state_points),
                      "goal_area_ids": get_collections_of_ids(goal_area_points),
                      "scenario_data": scenario_data,
                      "colors": colors
                      }

async def generate_the_scenario(scenario_editor_unique_id):
    # Read the scenario data
    scenario_data = await ui.run_javascript(f"document.getElementById('{scenario_editor_unique_id}').scenario_data")
    # Invoke the logic to generate the scenario using that data
    ui.notify(f'Generate scenario using {scenario_data}')

# TODO Move this to an util module
def get_colors():
    from matplotlib.cm import get_cmap
    _name = "Accent"
    _cmap = get_cmap(_name)  # type: matplotlib.colors.ListedColormap
    # TODO Those must be HEX Strings?
    # THIS HAS ONLY 8 COLORS!
    return _cmap.colors  # type: list


def scenario_editor(map_file: str, container: ui.element):
    """
    Generate the scenario editing plugin and link it to the external buttons
    """
    scenario_editor_unique_id = f"fig_{uuid.uuid4()}"
    max_players = 8

    with ui.button_group():
        generate_button = ui.button("Generate", on_click=lambda : generate_the_scenario(scenario_editor_unique_id))
        add_vehicle_button = ui.button("Add Vehicle")
        reset_button = ui.button("Reset")
    
    # Setting the size of the plot is tricky, it depends on the road shape
    fig, ax = plt.subplots(figsize=(10, 2))
    try:
        # Render the figure
        scenario, _ = XMLFileReader(map_file).open()
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
        goal_area_points = list()
        colors = list()
        scenario_data = dict()

        vehicle_colors = get_colors()

        # Initialize the scenario data with default values for initial state and goal state for all the vehicles
        for driver_index in range(0, max_players):
            color = vehicle_colors[ driver_index ]
            # TODO Do we really need scenario data? The original code used that to visualize existing scenarios, so it might be useful to keep it
            
            # Ensure the marker is not visible initially
            scenario_data[f"{driver_index}_is_visible"] = False
            # Show two lines of markers
            scenario_data[f"{driver_index}_x_is"] = bottom_left_corner[0] + driver_index * 2.0
            scenario_data[f"{driver_index}_y_is"] = bottom_left_corner[1]
            scenario_data[f"{driver_index}_v_is"] = 0.0
            scenario_data[f"{driver_index}_vehicle_model"] = "car"
            scenario_data[f"{driver_index}_x_ga"] = bottom_left_corner[0] + driver_index * 2.0
            scenario_data[f"{driver_index}_y_ga"] = bottom_left_corner[1] -2.0

            # We plot the markers to ensure they are included in the plugin as currently generate markers on the fly is not possible
            # Round marker - Initial State
            x_is = float(scenario_data[f"{driver_index}_x_is"])
            y_is = float(scenario_data[f"{driver_index}_y_is"])
            initial_state_points.append(ax.plot(x_is, y_is, 'o', color= color, mec='k', ms=15, mew=1, alpha=0.0, zorder=52)[0])
            # Squared marker - Goal State
            x_ga = float(scenario_data[f"{driver_index}_x_ga"])
            y_ga = float(scenario_data[f"{driver_index}_y_ga"])
            goal_area_points.append(ax.plot(x_ga, y_ga, 's', color= color, mec='k', ms=15, mew=1, alpha=0.0, zorder=52)[0])
            # Remember the color of the player as well
            colors.append(color)
        
        #
        #
        # Status I can show and hide vehicles' initial and final states but cannot drag and drop them across the map
        #       Also the tooltip is not visible/does not show
        #   TODO: First make sure that drag works, then make sure that tool tip can be seen, finally add inputs via tool tips
        #
        #

        mpld3.plugins.connect(fig, RoadLogicScenarioEditor(figure_id=scenario_editor_unique_id, 
                                                           container_id=container.html_id,
                                                           generate_button_id=generate_button.html_id,
                                                           add_vehicle_button_id=add_vehicle_button.html_id,
                                                           reset_button_id=reset_button.html_id,
                                                           initial_state_points=initial_state_points,
                                                           goal_area_points=goal_area_points,
                                                           scenario_data=scenario_data,
                                                           colors=colors))
        
        # Add the HTML figure at the page level (so the plugin must take care of moving around)
        # The figid MUST start with fig_
        ui.add_body_html(mpld3.fig_to_html(fig, figid=scenario_editor_unique_id))
        
    finally:
        plt.close(fig)

    