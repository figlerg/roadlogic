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

mpld3.register_plugin("roadlogic_scenario_editor", RoadLogicScenarioEditor);

RoadLogicScenarioEditor.prototype = Object.create(mpld3.Plugin.prototype);

RoadLogicScenarioEditor.prototype.constructor = RoadLogicScenarioEditor;

RoadLogicScenarioEditor.prototype.requiredProps = ["figure_id", 
                                                        "container_id", 
                                                        "generate_button_id",
                                                        "add_vehicle_button_id",
                                                        "reset_button_id",
                                                        "show_dialog_button_id",
                                                        "add_waypoint_button_id",
                                                        "select_player_id",
                                                        "update_select_button_id",
                                                        "initial_state_ids",
                                                        "waypoint_ids",
                                                        "scenario_data",
                                                        "colors"];

RoadLogicScenarioEditor.prototype.defaultProps = {alpha_fill:0.6, alpha_stroke:0.6, hoffset:0, voffset:10};


function RoadLogicScenarioEditor(fig, props){
    mpld3.Plugin.call(this, fig, props);
    // Ensure during dragging the markers are clearly and always visible; otherwise, their opacity should be 0.6
    mpld3.insert_css("#" + props.figure_id + " path.dragging",
                        {"fill-opacity": "1.0 !important",
                        "stroke-opacity": "1.0 !important"});
};

RoadLogicScenarioEditor.prototype.draw = async function(){
    // To ensure consistent look and fill, we created all the necessary buttons and pass their id to this plugin, so 
    // it can bind them and move them in the right positions

    // The figure corresponding to this plugin
    const the_figure_id = this.props.figure_id
    // The initial data to setup the scenario (ensure we can rollback to a consistent state when the reset button is pressed)
    const initial_scenario_data = this.props.scenario_data;

    // Move the figure which contain the scenario inside the element which will contain it
    // Waiting for the container to be rendered
    var the_figure = document.getElementById(the_figure_id)
    var the_container = await waitForElm(this.props.container_id)
    the_container.insertBefore(the_figure, the_container.firstChild)
    
    // Find the pre-generated buttons and link the functions

    // Logic to generate the scenario is triggered by this button. Currently, the logic runs on the server side
    var the_generate_button  = document.getElementById(this.props.generate_button_id)

    // Generate the XML and let the user download it.
    // var the_download_button  = document.getElementById(this.props.download_button_id)

    // Introduce a new vehicle in the scenario (up to max_vehicles, currently 8)
    var the_add_vehicle_button  = document.getElementById(this.props.add_vehicle_button_id)
    
    // Add a waypoint for the selected player if any
    var the_add_waypoint_button = document.getElementById(this.props.add_waypoint_button_id)
    the_add_waypoint_button.classList.add("disabled");

    var select_player  = document.getElementById(this.props.select_player_id)
    // https://stackoverflow.com/questions/5416767/get-selected-value-text-from-select-on-change
    // select_player.onchange = function(event){
        // var selectElement = event.target;
        // var value = selectElement.value;
        // console.log(value);
    // }

    var the_update_select_button  = document.getElementById(this.props.update_select_button_id)
    the_update_select_button.visibility = 'hidden'

    // Reset the scenario to its initial state, as recorded by initial_scenario_data
    var the_reset_button = document.getElementById(this.props.reset_button_id)
    // Show the modal dialog that allows to change parameters of the selected element (initial state or waypoint)
    var the_show_dialog_button = document.getElementById(this.props.show_dialog_button_id)
    // Ensure that initially the modala dialog is not visible
    the_show_dialog_button.style.visibility = 'hidden';

    // Communication with the server side is done by invoking JS functions and capturing their results, as per nicegui model
    // We achieve them by storing into known objects the data about the scenario.
    the_figure.scenario_data = {} // Scenario data
    the_figure.modal_data = {} // Data used to render the modal dialog
    
    // Create an object to store the visibility of the vehicles
    // This might not be needed if we store visibility flag on the initial_state_objects
    var player_visibility_flags= []

    // Get a reference of each of the marker objects. We store data directly inside them
    // The objects are initialized with the provided initial values
    var initial_state_objs = [];
    // This is a squared matrix of size vehicles X waypoints
    var waypoint_objs = []; 

    const n_vehicles = this.props.initial_state_ids.length
    const n_waypoints_per_vehicle = this.props.waypoint_ids.length / n_vehicles

    console.log("N VEHICLES " + n_vehicles)
    console.log("N WAYPOINT PER VEHICLE " +  n_waypoints_per_vehicle)

    for( let i = 0; i < n_vehicles; i++){
        // Associate to the marker representing the initial state additional data
        var initial_state_obj = mpld3.get_element(this.props.initial_state_ids[i])
        // TODO Include speed, make this generic with attributes
        initial_state_obj.data = [ initial_scenario_data[i + "_x_is"], initial_scenario_data[i + "_y_is"] ]
        initial_state_obj.visible = initial_scenario_data[i + "_is_visible"]
        initial_state_objs.push(initial_state_obj)

        var waypoints_of_vehicle = []
        for(let j = 0; j < n_waypoints_per_vehicle; j++){
            // Associate to the marker representing the j_th waypoint of the i_th vehicle additional data
            var waypoint_obj = mpld3.get_element(this.props.waypoint_ids[i + j])
            // TODO Include time, make this generic with attributes
            waypoint_obj.data = [ initial_scenario_data[i + "_" + j + "_wp_x"], initial_scenario_data[i + "_" + j + "_wp_y"] ]
            waypoint_obj.visible = initial_scenario_data[i + "_" + j + "_wp_is_visible"]
            waypoints_of_vehicle.push(waypoint_obj)
        }
        
        waypoint_objs.push(waypoints_of_vehicle)

        // This can be replaced by initial_state_obj.visible
        player_visibility_flags[i] = initial_scenario_data[i + "_is_visible"];
    }
    // Refresh the select
    the_update_select_button.click()

    // Not sure this is needed
    var colors = this.props.colors;
    
    var make_waypoint_visible_for_player = function(player_index, waypoint_index){
        // Visualize the waypoint in the default position
        // TODO How to handle initial position of the waypoints from other scenarios?!
        waypoint_objs[player_index][waypoint_index].data = [ initial_scenario_data[player_index + "_" + waypoint_index + "_wp_x"], initial_scenario_data[player_index + "_" + waypoint_index + "_wp_y"] ]
        // Set visibility flag
        waypoint_objs[player_index][waypoint_index].visible = true
        // Change the visibility so we can actually see it
        waypoint_objs[player_index][waypoint_index].pathsobj
                .style("visibility", "visible")
                .style("stroke-opacity", 0.6)
                .style("fill-opacity", 0.6)
        // Initialize the value for this
        the_figure.scenario_data[index].waypoints[waypoint_index] = {
                "x" : waypoint_objs[player_index][waypoint_index].data[0],
                "y" : waypoint_objs[player_index][waypoint_index].data[1],
                "t" : 0 // TODO Set the time as the max(time for time in waypoints) + 1 
        }
    }

    var make_player_visible = function(player_index){
        // Visualize the initial state of a player, thereby activating it
        player_visibility_flags[player_index] = true
        // Set the visibility flag
        initial_state_objs[player_index].visible = true
        // Why not storing all the data including v
        initial_state_objs[player_index].data = [ initial_scenario_data[player_index + "_x_is"], initial_scenario_data[player_index + "_y_is"] ];
        // Make it visible
        initial_state_objs[player_index].pathsobj
                .style("visibility", "visible")
                .style("stroke-opacity", 0.6)
                .style("fill-opacity", 0.6);
        // Add the data about the newly visible vehicle
        the_figure.scenario_data[player_index] = {
            "vehicle_model" : initial_scenario_data[player_index + "_vehicle_model"],
            "initial_state": {
                "x" : initial_scenario_data[player_index + "_x_is"],
                "y" : initial_scenario_data[player_index + "_y_is"],
                "v" : initial_scenario_data[player_index + "_v_is"]
            }, 
            "waypoints": []
        }
        // Attach the control logic to the vehicle initial state and waypoints
        add_controls(player_index)
        // Refresh the select
        the_update_select_button.click()
    }
    
    the_add_vehicle_button.onclick = function(){
        // Take the first nonvisible vehicle and make it visible.
        var selected_player_index;
        for( let player_index = 0; player_index < player_visibility_flags.length; player_index++){
            if (player_visibility_flags[player_index] == false){
                make_player_visible(player_index);
                selected_player_index = player_index;
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
        is_obj.visible = false
        
        for(let j = 0; j < n_waypoints_per_vehicle; j++){
            var wp_obj = waypoint_objs[index][j];
            // ga_obj.data = [ initial_scenario_data[index + "_x_ga"], initial_scenario_data[index + "_y_ga"] ]
            wp_obj.pathsobj.style("visibility", "hidden");
            wp_obj.pathsobj.attr("transform", "translate("+wp_obj.offsetcoords.x(wp_obj.data[0])+","+wp_obj.offsetcoords.y(wp_obj.data[1])+")");
            wp_obj.visible = false
        }
        
        // After removing a vehicle, then the add vehicle button is definitively active
        the_add_vehicle_button.classList.remove("disabled")

        // Remove the data
        delete the_figure.scenario_data[index]

        // Update the select
        the_update_select_button.click()
    }
    
    // Drag and Drop common functionalities            
    var drag_started = function(d) {
        d3.event.sourceEvent.stopPropagation();
        d3.select(this).classed("dragging", true);
    }

    var drag_ended = function(d) {
        d3.select(this).classed("dragging", false);
    }

    var add_controls = function(index) {
        var initial_state_obj = initial_state_objs[index];
        var waypoints = waypoint_objs[index];
            
        initial_state_obj.elements()
            .on("click", function(d, i){
                // Trigger a click event on this button
        
                // Data for the modal dialog box
                the_figure.modal_data = {}
                the_figure.modal_data["vehicle"] = index
                the_figure.modal_data["vehicle_model"] = the_figure.scenario_data[index]["vehicle_model"]
                the_figure.modal_data["color"] = {
                    "r" : (colors[index][0] * 255.0).toFixed(1),
                    "g" : (colors[index][1] * 255.0).toFixed(1),
                    "b" : (colors[index][2] * 255.0).toFixed(1)
                }
                the_figure.modal_data["initial_state"] = {}
                the_figure.modal_data["initial_state"]["v"] = the_figure.scenario_data[index]["initial_state"]["v"]

                // Show the modal dialog
                the_show_dialog_button.click()
            });

        for(let j = 0; j < n_waypoints_per_vehicle; j++){
            var wp_obj = waypoint_objs[index][j];
            wp_obj.elements()
                .on("click", function(d, i){
                    // Trigger a click event on this button
            
                    // Data for the modal dialog box
                    the_figure.modal_data = {}
                    the_figure.modal_data["vehicle"] = index
                    the_figure.modal_data["color"] = {
                        "r" : (colors[index][0] * 255.0).toFixed(1),
                        "g" : (colors[index][1] * 255.0).toFixed(1),
                        "b" : (colors[index][2] * 255.0).toFixed(1)
                    }
                    the_figure.modal_data["waypoint_id"] = j
                    the_figure.modal_data["waypoint"] = {}

                    // Show the modal dialog
                    the_show_dialog_button.click()
                });
            }
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
        
        // var goal_area_drag = d3.drag()
        //     .subject(function(d) {
        //                 // Ensure we always refer to the stored stat of the object
        //                 return {
        //                         x: initial_state_obj.ax.x(the_figure.scenario_data[index]["goal_area"]["x"]),
        //                         y: initial_state_obj.ax.y(the_figure.scenario_data[index]["goal_area"]["y"])
        //                 };
        //             } 
        //         )
        //     .on("start", drag_started)
        //     .on("drag", function(d) {
        //             // As long as we are dragging d ... 
        //             // TODO Update the inputs elements corresponding to d (d.id might be stored somewhere)
        //             d.x = goal_area_obj.ax.x.invert(d3.event.x);
        //             d.y = goal_area_obj.ax.y.invert(d3.event.y);
        //             // Apply the translation to the element we are dragging to move it around
        //             d3.select(this).attr("transform", "translate(" + [d3.event.x, d3.event.y] + ")");
        //             //console.log("GA Dragged to " + d.x + ", " + d.y)
        //             // Refresh the form - Assume this elements are there!
        //             the_figure.scenario_data[index]["goal_area"]["x"] = d.x
        //             the_figure.scenario_data[index]["goal_area"]["y"] = d.y
        //         }
        //     )
        //     .on("end", drag_ended);
        
        initial_state_obj.elements()
            .style("cursor", "default")
            .call(initial_state_drag);
        
        // goal_area_obj.elements()
        //     .style("cursor", "default")
        //     .call(goal_area_drag);
    }

    var reset_scenario = function(){
        for( let player_index = 0; player_index < player_visibility_flags.length; player_index++){
            // TODO Should hide_player remove the controls for dragging and tooltip?
            hide_player(player_index)
            if ( initial_scenario_data[player_index + "_is_visible"] ){
                make_player_visible(player_index)
            }
        }
        // Refresh the select
        the_update_select_button.click()
    }

    the_reset_button.onclick = reset_scenario
    
    // Invoke the scenario initialization
    reset_scenario()
};