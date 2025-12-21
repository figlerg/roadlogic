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
                                                        "selected_vehicle_id",
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

    // Introduce a new vehicle in the scenario (up to max_vehicles, currently 8)
    var the_add_vehicle_button  = document.getElementById(this.props.add_vehicle_button_id)
    
    // Add a waypoint for the selected player if any
    var the_add_waypoint_button = document.getElementById(this.props.add_waypoint_button_id)
    // Disabled this by default
    the_add_waypoint_button.classList.add("disabled");

    // var the_update_select_button  = document.getElementById(this.props.update_select_button_id)
    // the_update_select_button.visibility = 'hidden'

    // Reset the scenario to its initial state, as recorded by initial_scenario_data
    var the_reset_button = document.getElementById(this.props.reset_button_id)
    // Show the modal dialog that allows to change parameters of the selected element (initial state or waypoint)
    var the_show_dialog_button = document.getElementById(this.props.show_dialog_button_id)
    // Ensure that initially the modala dialog is not visible
    the_show_dialog_button.style.visibility = 'hidden';

    // Communication with the server side is done by invoking JS functions and capturing their results, as per nicegui model
    // We achieve them by storing into known objects the data about the scenario.
    the_figure.scenario_data = {} // Scenario data. Note: this is a plain js object, not a dictionary
    the_figure.modal_data = {} // Data used to render the modal dialog. Note: this is a plain js object, not a dictionary
    the_figure.selected_vehicle_id = null

    const n_vehicles = this.props.initial_state_ids.length
    const n_waypoints_per_vehicle = this.props.waypoint_ids.length / n_vehicles

    var update_generate_button = function(){
        // This button is disabled if there are no players or if any player is invalid
        // An invalid player is a player with no waypoints
        the_generate_button.classList.add("disabled");
        active_vehicles = Object.keys(the_figure.scenario_data).length
        if (active_vehicles > 0 ){
            for (var vehicle_key in the_figure.scenario_data) {
                if (Object.keys(the_figure.scenario_data[vehicle_key]["waypoints"]).length == 0){
                    return
                }
            }
            // If all the players have at least a waypoint, we can generate the scenario
            the_generate_button.classList.remove("disabled");
        }
    }

    // Create an object to store the visibility of the vehicles
    // This might not be needed if we store visibility flag on the initial_state_objects
    var player_visibility_flags= []

    // Get a reference of each of the marker objects. We store data directly inside them
    // The objects are initialized with the provided initial values
    var initial_state_objs = [];
    // This is a squared matrix of size vehicles X waypoints
    var waypoint_objs = {}; 

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
            var waypoint_obj = mpld3.get_element(this.props.waypoint_ids[i * n_vehicles + j])

            // TODO Include time, make this generic with attributes
            waypoint_obj.data = [ initial_scenario_data[i + "_" + j + "_wp_x"], initial_scenario_data[i + "_" + j + "_wp_y"] ]
            waypoint_obj.visible = initial_scenario_data[i + "_" + j + "_wp_is_visible"]

            waypoints_of_vehicle.push(waypoint_obj)
        }
        
        waypoint_objs[i] = waypoints_of_vehicle

        // This can be replaced by initial_state_obj.visible
        player_visibility_flags[i] = initial_scenario_data[i + "_is_visible"];
    }

    // Not sure this is needed
    var colors = this.props.colors
    var label_showing_selected_vehicle_id = document.getElementById(this.props.selected_vehicle_id)
    var default_label_showing_selected_vehicle = label_showing_selected_vehicle_id.innerHTML


    var select_vehicle_id = function(player_index){
        // Clicking on the initial state of the vehicle selects the vehicle for further operations
        the_figure.selected_vehicle_id = player_index
        // Update the label - TODO Update the Colors
        label_showing_selected_vehicle_id.innerHTML = "Vehicle " + player_index + " Selected"
        const r = (colors[player_index][0] * 255.0).toFixed(1)
        const g = (colors[player_index][1] * 255.0).toFixed(1)
        const b = (colors[player_index][2] * 255.0).toFixed(1)
        label_showing_selected_vehicle_id.style.background = "rgb(" + r + "," + g + "," + b +" )"
        //
        update_add_waypoint_button()
    }
    

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
        the_figure.scenario_data[player_index]["waypoints"][waypoint_index] = {
                "x" : waypoint_objs[player_index][waypoint_index].data[0],
                "y" : waypoint_objs[player_index][waypoint_index].data[1],
                "t" : 0 // TODO Set the time as the max(time for time in waypoints) + 1 
        }
        // Ensure we can 
        update_generate_button()
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
        // Force a refresh the vehicle select control
        // the_update_select_button.click()
        // Check whether generation is enabled
        update_generate_button()
    }
    
    the_add_vehicle_button.onclick = function(){
        // Take the first nonvisible vehicle and make it visible.
        // Also atta
        for( let player_index = 0; player_index < player_visibility_flags.length; player_index++){
            if (player_visibility_flags[player_index] == false){
                make_player_visible(player_index)
                add_controls(player_index)
                break;
            }
        }
        // Ensure add vehicle button is enabled/disabled correctly
        the_add_vehicle_button.classList.add("disabled");
        for( let player_index = 0; player_index < player_visibility_flags.length; player_index++){
            if (player_visibility_flags[player_index] == false){
                the_add_vehicle_button.classList.remove("disabled");
            }
        }
    }

    the_add_waypoint_button.onclick = function(){
        // Get the index of the selected vehicle
        var vehicle_index = the_figure.selected_vehicle_id
        // Take the first nonvisible waypoint of this vehicle and make it visible.
        for( let wp_index = 0; wp_index < n_waypoints_per_vehicle; wp_index++){
            if (waypoint_objs[vehicle_index][wp_index].visible == false){
                make_waypoint_visible_for_player(vehicle_index, wp_index)
                break
            }
        }
    }

    the_figure.hide_waypoint = function(vehicle_index, waypoint_index){
        var wp_obj = waypoint_objs[vehicle_index][waypoint_index];
        wp_obj.pathsobj.style("visibility", "hidden");
        wp_obj.pathsobj.attr("transform", "translate("+wp_obj.offsetcoords.x(wp_obj.data[0])+","+wp_obj.offsetcoords.y(wp_obj.data[1])+")");
        wp_obj.visible = false
        // Remove the data of the waypoint
        if (vehicle_index in this.scenario_data && this.scenario_data[vehicle_index] && waypoint_index in this.scenario_data[vehicle_index]["waypoints"]){
            delete this.scenario_data[vehicle_index]["waypoints"][waypoint_index]
        } 
        update_generate_button()
    }

    // Expose this function
    the_figure.hide_player = function(index){
        // Change visibility of the markers
        player_visibility_flags[index] = false;

        // Hide and move back to the initial position and all the waypoints                
        var is_obj = initial_state_objs[index];
        is_obj.pathsobj.style("visibility", "hidden");
        is_obj.pathsobj.attr("transform", "translate("+is_obj.offsetcoords.x(is_obj.data[0])+","+is_obj.offsetcoords.y(is_obj.data[1])+")");
        is_obj.visible = false
        
        for(let wp_index = 0; wp_index < n_waypoints_per_vehicle; wp_index++){
            this.hide_waypoint(index, wp_index)
        }
        
        // After removing a vehicle, then the add vehicle button is definitively active
        the_add_vehicle_button.classList.remove("disabled")

        // Remove the data
        delete the_figure.scenario_data[index]

        // If we hide the currently selected player, we need to reset the state and the button
        if (the_figure.selected_vehicle_id == index){
            the_figure.selected_vehicle_id = null
            // Update the label - TODO Update the Colors
            label_showing_selected_vehicle_id.innerHTML = default_label_showing_selected_vehicle
        }
        // Ensure consistency of GUI
        update_generate_button()
        update_add_waypoint_button()
    }
    
    // Drag and Drop common functionalities            
    var drag_started = function(d) {
        d3.event.sourceEvent.stopPropagation();
        d3.select(this).classed("dragging", true);
    }

    var drag_ended = function(d) {
        d3.select(this).classed("dragging", false);
    }

    var update_add_waypoint_button = function(){
        // Enable or disable the add waypoint button
        if( the_figure.selected_vehicle_id == null){
            // No player is currently selected, the button must be disabled
            the_add_waypoint_button.classList.add("disabled")
            label_showing_selected_vehicle_id.style.background = "white"
        } else {
            // A player is currently selected, the button must be enabled
            the_add_waypoint_button.classList.remove("disabled")
        }        
    }

    // Function to attach mouse events to the markers
    var add_controls = function(player_index) {
        var initial_state_obj = initial_state_objs[player_index]
        var vehicle_waypoints_objs = waypoint_objs[player_index]
    
        // Double Clicking on the Initial State should open the modal dialog
        initial_state_obj.elements()
            .on("click", function(d, i ){
                select_vehicle_id(player_index)
            })
            .on("dblclick", function(d, i){
                // The modal dialog shows the vehicle initial speed and model based on the state of the scenario
                the_figure.modal_data = {}
                //
                the_figure.modal_data["vehicle_index"] = player_index
                //
                the_figure.modal_data["vehicle_model"] = the_figure.scenario_data[player_index]["vehicle_model"]
                //
                the_figure.modal_data["color"] = {
                    "r" : (colors[player_index][0] * 255.0).toFixed(1),
                    "g" : (colors[player_index][1] * 255.0).toFixed(1),
                    "b" : (colors[player_index][2] * 255.0).toFixed(1)
                }
                // TODO Simplify with Type = Initial State and then only attributes
                the_figure.modal_data["initial_state"] = {}
                // Initial position. Will not be editable.
                the_figure.modal_data["initial_state"]["x"] = the_figure.scenario_data[player_index]["initial_state"]["x"]
                the_figure.modal_data["initial_state"]["y"] = the_figure.scenario_data[player_index]["initial_state"]["y"]
                // the_figure.modal_data["initial_state"]["orientation"] = the_figure.scenario_data[player_index]["initial_state"]["orientation"]
                // the_figure.modal_data["initial_state"]["timestep"] = the_figure.scenario_data[player_index]["initial_state"]["timestep"]
                // Initial speed
                the_figure.modal_data["initial_state"]["v"] = the_figure.scenario_data[player_index]["initial_state"]["v"]
                // the_figure.modal_data["initial_state"]["acceleration"] = the_figure.scenario_data[player_index]["initial_state"]["acceleration"]

                // Show the modal dialog
                the_show_dialog_button.click()
            });

        for( let wp_index = 0; wp_index < vehicle_waypoints_objs.length; wp_index++){
            var wp_obj = vehicle_waypoints_objs[wp_index];

            wp_obj.elements()
                .on("click", function(d, i ){
                    select_vehicle_id(player_index)
                })
                .on("dblclick", function(d, i){
                    // Data for the modal dialog box
                    the_figure.modal_data = {}
                    //
                    the_figure.modal_data["vehicle_index"] = player_index
                    the_figure.modal_data["waypoint_index"] = wp_index
                    //
                    the_figure.modal_data["color"] = {
                        "r" : (colors[player_index][0] * 255.0).toFixed(1),
                        "g" : (colors[player_index][1] * 255.0).toFixed(1),
                        "b" : (colors[player_index][2] * 255.0).toFixed(1)
                    }
                    //
                    the_figure.modal_data["waypoint"] = {}
                    the_figure.modal_data["waypoint"]["x"] = the_figure.scenario_data[player_index]["waypoints"][wp_index]["x"]
                    the_figure.modal_data["waypoint"]["y"] = the_figure.scenario_data[player_index]["waypoints"][wp_index]["y"]
                    the_figure.modal_data["waypoint"]["t"] = the_figure.scenario_data[player_index]["waypoints"][wp_index]["t"]
                    // the_figure.modal_data["waypoint"]["v"] = the_figure.scenario_data[player_index]["waypoints"][waypoint_index]["v"]

                    // Show the modal dialog
                    the_show_dialog_button.click()
                });
            }

        // We attach the dragging and dropping functionalities to both the initial_state and waypoints
                    
        var initial_state_drag = d3.drag()
            .subject(function(d) {
                        select_vehicle_id(player_index)
                        // Ensure we always refer to the stored stat of the object
                        return {
                                x: initial_state_obj.ax.x(the_figure.scenario_data[player_index]["initial_state"]["x"]),
                                y: initial_state_obj.ax.y(the_figure.scenario_data[player_index]["initial_state"]["y"])
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
                            the_figure.scenario_data[player_index]["initial_state"]["x"] = d.x
                            the_figure.scenario_data[player_index]["initial_state"]["y"] = d.y
                        }
                )
            .on("end", drag_ended);
        initial_state_obj.elements()
            .style("cursor", "default")
            .call(initial_state_drag);

        for( let wp_index = 0; wp_index < vehicle_waypoints_objs.length; wp_index++){
            var wp_obj = vehicle_waypoints_objs[wp_index];
            var waypoint_drag = d3.drag()
                .subject(function(d) {
                            select_vehicle_id(player_index)
                            // Ensure we always refer to the stored stat of the object
                            return {
                                    x: wp_obj.ax.x(the_figure.scenario_data[player_index]["waypoints"][wp_index]["x"]),
                                    y: wp_obj.ax.y(the_figure.scenario_data[player_index]["waypoints"][wp_index]["y"])
                            };
                        } 
                    )
                .on("start", drag_started)
                .on("drag", function(d) {
                        // As long as we are dragging d ... 
                        // TODO Update the inputs elements corresponding to d (d.id might be stored somewhere)
                        d.x = wp_obj.ax.x.invert(d3.event.x);
                        d.y = wp_obj.ax.y.invert(d3.event.y);
                        // Apply the translation to the element we are dragging to move it around
                        d3.select(this).attr("transform", "translate(" + [d3.event.x, d3.event.y] + ")");
                        //console.log("GA Dragged to " + d.x + ", " + d.y)
                        // Refresh the form - Assume this elements are there!
                        the_figure.scenario_data[player_index]["waypoints"][wp_index]["x"] = d.x
                        the_figure.scenario_data[player_index]["waypoints"][wp_index]["y"] = d.y
                    }
                )
                .on("end", drag_ended);
            wp_obj.elements()
                .style("cursor", "default")
                .call(waypoint_drag);
        }
    }

    var reset_scenario = function(){
        for( let player_index = 0; player_index < player_visibility_flags.length; player_index++){
            // TODO Should hide_player remove the controls for dragging and tooltip?
            the_figure.hide_player(player_index)
            if ( initial_scenario_data[player_index + "_is_visible"] ){
                make_player_visible(player_index)
            }
        }
        // Refresh the select
        // the_update_select_button.click()
    }

    the_reset_button.onclick = reset_scenario
    
    // Invoke the scenario initialization
    reset_scenario()
    // Check whether generation is enabled
    update_generate_button()
}