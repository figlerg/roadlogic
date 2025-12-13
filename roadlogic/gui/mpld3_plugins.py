import mpld3
import matplotlib as mpl
import json


class TrajectoryView(mpld3.plugins.PluginBase):
    """
    Make it possible to visualize the currently selected trajectory using two lines:
    - trajectory_line works in the background to visualize the entire trajectory
    - selected_line works in the foreground to visualize the selected part of the trajectory in bold

    This plugin creates a bridge element and assumes the figure contains the two lines to be modified,
    since I cannot find a way to dynamically add more lines in an existing figure without re-rending on the server
    everything
    """

    JAVASCRIPT = """
    mpld3.register_plugin("trajectoryview", TrajectoryViewPlugin);
    TrajectoryViewPlugin.prototype = Object.create(mpld3.Plugin.prototype);
    TrajectoryViewPlugin.prototype.constructor = TrajectoryViewPlugin;
    TrajectoryViewPlugin.prototype.requiredProps = ["trajectory_line", "selected_line", "reference_path_line"];
    TrajectoryViewPlugin.prototype.defaultProps = {}

    function TrajectoryViewPlugin(fig, props){
        mpld3.Plugin.call(this, fig, props);
    };
    
    // This is called at the beginning, and upon refresh?
    TrajectoryViewPlugin.prototype.draw = function(){
        // We need a bridge to capture value change events
        var div = d3.select("#" + this.fig.figid);

        var trajectory_line = mpld3.get_element(this.props.trajectory_line);
        var selected_line = mpld3.get_element(this.props.selected_line);
        var reference_path_line = mpld3.get_element(this.props.reference_path_line);
        
        // Create an hidden input that acts as bridge
        div.append("input")
            .attr("id","the_trajectory")
            .attr("type", "hidden");
            
        div.append("input")
            .attr("id","the_reference_path")
            .attr("type", "hidden");
        
        var trajectory_placeholder = document.getElementById("the_trajectory");
        var reference_path_placeholder = document.getElementById("the_reference_path");
        
        trajectory_placeholder.addEventListener("UpdateTrajectoryEvent", function(evt) {
                trajectory_line.data = evt.detail.trajectory
                
                if( evt.detail.horizon > 0 ){
					selected_line.data = trajectory_line.data.slice(0, evt.detail.horizon);
				} else {
					selected_line.data = trajectory_line.data;
				}
                
                // Show the underlying line
                trajectory_line.elements()
                    .attr("d", trajectory_line.datafunc(trajectory_line.data));
                // Show the bolded line
                selected_line.elements()
                    .attr("d", selected_line.datafunc(selected_line.data));
          });
        
        reference_path_placeholder.addEventListener("UpdateReferencePathEvent", function(evt) {
                reference_path_line.data = evt.detail.reference_path
                // Refresh the reference_path line
                reference_path_line.elements()
                    .attr("d", reference_path_line.datafunc(reference_path_line.data));
          });      
    };
    """

    def __init__(self, trajectory_line, selected_line, reference_path_line):
        self.dict_ = {
            "type": "trajectoryview",
            "trajectory_line": mpld3.utils.get_id(trajectory_line),
            "selected_line": mpld3.utils.get_id(selected_line),
            "reference_path_line": mpld3.utils.get_id(reference_path_line),
        }


class AllTrajectoriesView(mpld3.plugins.PluginBase):
    """
    Make it possible to visualize a bundle of trajectories identified by trajectory_ids
    This plugin assumes that the figure ALREADY contains a number of line-placeholders used to visualize the actual trajectories
    This value is controlled by model.mixed_traffic_scenario.VISIBLE_TRAJECTORIES
    """

    JAVASCRIPT = """
    mpld3.register_plugin("alltrajectoryview", AllTrajectoriesViewPlugin);
    AllTrajectoriesViewPlugin.prototype = Object.create(mpld3.Plugin.prototype);
    AllTrajectoriesViewPlugin.prototype.constructor = AllTrajectoriesViewPlugin;
    AllTrajectoriesViewPlugin.prototype.requiredProps = ["trajectory_ids"];
    AllTrajectoriesViewPlugin.prototype.defaultProps = {alpha_show: 0.2}

    function AllTrajectoriesViewPlugin(fig, props){
        mpld3.Plugin.call(this, fig, props);
    };

    // This is called at the beginning and must setup all the functions
    AllTrajectoriesViewPlugin.prototype.draw = function(){
        // We need a bridge to capture refresh events to refresh the visualization
        var div = d3.select("#" + this.fig.figid);
        div.append("input")
            .attr("id","visible_trajectories_bridge")
            .attr("type", "hidden");

        // Get an handle on the visible trajectories lines and extend them by adding methods
        var reset_me = function() {
			this.elements().attr("d", this.datafunc({}));
        };
            
        var update_me = function(trajectory_data){
			this.elements().attr("d", this.datafunc(trajectory_data));
        };
        
        // Prepare a variable to hold the ref of all the line/trajectories
        var the_visible_trajectories = []
        for(var i=0; i<this.props.trajectory_ids.length; i++){
            
            var obj = mpld3.get_element(this.props.trajectory_ids[i], this.fig);

            // Register the new functions            
            obj.reset_me = reset_me;
            // obj.show_me = show_me
            obj.update_me = update_me;
            
            // Store the object in the list
            the_visible_trajectories.push(obj);
        };
        
        // Register an Event Listener to trigger the refresh of all trajectories
        var visible_trajectories_bridge_placeholder = document.getElementById("visible_trajectories_bridge");
        
        visible_trajectories_bridge_placeholder.addEventListener("Refresh", function(evt) {
                // We assume that the trajectories to visualize are defined inside new_visible_trajectories as LIST
                // The order does not matter 
				var new_visible_trajectories = evt.detail.new_visible_trajectories

                // First we make ALL possible visible trajectories not visible anymore
                the_visible_trajectories.forEach(function(e){ e.reset_me(); });

                // Next we make SOME of the visible trajectories visible. Skip the ones that are empty!
                var visualized = 0
                for(var i=0; i <  new_visible_trajectories.length; i++){
                    // Visualize ONLY the one that exist and only if we have enough placeholders
                    if (JSON.stringify(new_visible_trajectories[i]).length - 2 > 0 &&  visualized < the_visible_trajectories.length){
                        the_visible_trajectories[visualized].update_me(new_visible_trajectories[i])
                        visualized = visualized + 1
                    }              
                }
          });         
    };
    """

    def __init__(self, trajectory_ids):
        self.dict_ = {
            "type": "alltrajectoryview",
            "trajectory_ids": [mpld3.utils.get_id(trajectory_id) for trajectory_id in trajectory_ids]
        }


class ZoomEgoCarPlugin(mpld3.plugins.PluginBase):
    """
    Large maps might show the ego car as a very small rectangle. This plugin automatically center the diagram
    on the ego-car and ensure to focus on it by zooming 10, 20, 30 meters around the Ego Car.
    """
    JAVASCRIPT = """
    // little car icon
    var my_icon = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAAACXBIWXMAAAsTAAALEwEAmpwYAAACoklEQVRoge2Yu2sVQRTGJ1hEi0RExYBBRNDCRiSV8cEWCRrEBwm3TqFYGKONj3/AGAtfjZALQawSgqJFwEejhVqEJESx0ULQJgSEaOIjRTT6HfYszI4z+7gzy11hPvhBWM75zndy9959COHl5eX1v6kBdIHLoOoI8jrE3oVqP3gD/hTEaxAUFZ7+6z8LDB+xDI67Dt8KFpVBr8CwsD99htlL9l4Am10ucF0yp0+hy6U567CIf8LXXBmvAnOS8YArY40GpDlzPNtaByXTFbDVhalBW3hGNK/TheldyfCFC8MUvZTm3bE1Ww2+SoanbQ0zqE/Ev8xrbMx6RPznbZNtugzayLOiud02Zvclo0fW0bLrsTT3Xq0mzWBJMrphqFsLdoA20A46wDFQASeYCh/r4Bqq3c69Ot2S5i5xltzqlUyIRV7iNhgHb0V4jtpeeRfYa5y9b4JvSk1vLQs8dRDOFU/yhj8DfpUgeARl6csa/lQJAps4mRa+BfwoQVAT30XKT/mlEoRM40LSAg81De9E+NPXJMIL2xdNDR3bI7I9UTVwrXyFl326edZe8F5T8yDJfELT0K7UnNXUjGQIrmpU49Ov1OzT1EwkmU5pGpqUmkBT8xGszxF+A/ik8QmUumZNzVTeBXqUmquaGoIudNPskcS0+PfpLuKKMqviYgE6L+m0CcCgiN9ouWaZl6BZ54T+e5J7gbLhF6g3foF6U9MCn8EM+ABmwbyIvz2wZYU9Z3nGDM90tkA1oacRrGPoZnAbs1OET15t/Hd0vEWqb0zwrdaywKShaSipqSANGbJMJjWNGZrOF5nUoIuGLKNJTQH4rTTQuen0RWtG0Qtl9c6Xsh1Iazwqwi8R3a88A7uKy5iq3eA5Z6FMR+qYxcvLy8urhPoLf+IiiROBpr0AAAAASUVORK5CYII=";

    // create the plugin
    mpld3.register_plugin("zoomEgoCar", ZoomEgoCarPlugin);
    ZoomEgoCarPlugin.prototype = Object.create(mpld3.Plugin.prototype);
    ZoomEgoCarPlugin.prototype.constructor = ZoomEgoCarPlugin;
    // The actual center of the ego vehicle
    ZoomEgoCarPlugin.prototype.requiredProps = ["vehiclePositionX", "vehiclePositionY"];
    // Zoom Levels. It will reset to the initial one before restarting.
    ZoomEgoCarPlugin.prototype.defaultProps = { zoomLevels: [20, 30, 50] };
    // Store the current zoom level
    ZoomEgoCarPlugin.prototype.currentLevel = 0;
    
    // Extend the figure axes to include this additional method, because I have no idea how to create a selection object 
    // TODO Move this code inside our plugin and just call doZoom on the axes instead
    mpld3_Axes.prototype.doEgoZoom = function(x_min, y_min, x_max, y_max) {
        // Transfom coordinates into pixel position
        sel_x_min = this.x(x_min)
        sel_y_min = this.y(y_min)
        sel_x_max = this.x(x_max)
        sel_y_max = this.y(y_max)
        // Code copied from the BoxZoomPlugin d -> new width and height of the figure to define a scaling factor
        var dx = sel_x_max - sel_x_min;
        var dy = sel_y_max - sel_y_min;
        // Position of the "new" center -> we need this to translate the content in the right position
        var cx = (sel_x_min + sel_x_max) / 2;
        var cy = (sel_y_min + sel_y_max) / 2;
        //
        var scale = dx > dy ? this.width / dx : this.height / dy;
        var transX = this.width / 2 - scale * cx;
        var transY = this.height / 2 - scale * cy;
        // This is how we can create the functional composition of transformation        
        var transform = d3.zoomIdentity.translate(transX, transY).scale(scale);
        // Apply the transformation
        this.doZoom(true, transform, 750);
    };

    ZoomEgoCarPlugin.prototype.cycleZoom = function(fig){       
        // Make sure we call this at leat once
        fig.axes[0].reset()
        if(this.currentLevel >= this.defaultProps.zoomLevels.length){
            fig.axes[0].reset()
            this.currentLevel = 0
        } else {
            let minX = parseFloat(this.props.vehiclePositionX) - parseFloat(this.defaultProps.zoomLevels[this.currentLevel])
            let maxX = parseFloat(this.props.vehiclePositionX) + parseFloat(this.defaultProps.zoomLevels[this.currentLevel])
    		let minY = parseFloat(this.props.vehiclePositionY) - parseFloat(this.defaultProps.zoomLevels[this.currentLevel])
	    	let maxY = parseFloat(this.props.vehiclePositionY) + parseFloat(this.defaultProps.zoomLevels[this.currentLevel])
			fig.axes[0].doEgoZoom(minX, minY, maxX, maxY)
			this.currentLevel = this.currentLevel + 1
		}		
    }
    
    function ZoomEgoCarPlugin(fig, props){
        mpld3.Plugin.call(this, fig, props);
        // Pass this to the ButtonFactory, we need a reference to "this-as-the-plugin"
        var thePlugin = this              
        // create EgoCar button
        var EgoCarButton = mpld3.ButtonFactory({
            buttonID: "egoCar",
            sticky: false,
            onActivate: function(){thePlugin.cycleZoom(fig);}.bind(this),
            icon: function(){return my_icon;},
        });
        this.fig.buttons.push(EgoCarButton);
    };
    """

    def __init__(self, ego_vehicle_position_x, ego_vehicle_position_y):
        self.dict_ = {
            "type": "zoomEgoCar",
            "vehiclePositionX": ego_vehicle_position_x,
            "vehiclePositionY": ego_vehicle_position_y}


class ScenarioDragPlugin(mpld3.plugins.PluginBase):
    """ Old Version of the Plugin. Deprecated!"""
    JAVASCRIPT = r"""
        mpld3.register_plugin("scenario_drag", ScenarioDragPlugin);
    
        ScenarioDragPlugin.prototype = Object.create(mpld3.Plugin.prototype);
        
        ScenarioDragPlugin.prototype.constructor = ScenarioDragPlugin;
        
        ScenarioDragPlugin.prototype.requiredProps = ["initial_state_id", "goal_area_id", "id_array", "x_array", "y_array"];
        
        ScenarioDragPlugin.prototype.defaultProps = {}
        
        function ScenarioDragPlugin(fig, props){
            mpld3.Plugin.call(this, fig, props);
            mpld3.insert_css("#" + fig.figid + " path.dragging",
                             {"fill-opacity": "1.0 !important",
                              "stroke-opacity": "1.0 !important"});
        };

        ScenarioDragPlugin.prototype.draw = function(){
            //
            var initial_state_obj = mpld3.get_element(this.props.initial_state_id);
            var goal_area_obj = mpld3.get_element(this.props.goal_area_id);
            
            var id_array = JSON.parse(this.props.id_array);
            var x_array = JSON.parse(this.props.x_array);
            var y_array = JSON.parse(this.props.y_array);
            
            document.getElementById("id_array").value = JSON.stringify(id_array);

            var pointsData = [];
            for (var i = 0; i < id_array.length; i++) {
            var point = {
                id: id_array[i],
                x: x_array[i],
                y: y_array[i]
            };
            pointsData.push(point);
            }
        
        // TODO Not sure what's this...
        var initial_state_combinedData = [];
        for (var i = 0; i < id_array.length; i++) {
            initial_state_combinedData.push({
                id: id_array[i],
                offsets: initial_state_obj.offsets[i]
            });
        }
        var goal_area_combinedData = [];
        for (var i = 0; i < id_array.length; i++) {
            goal_area_combinedData.push({
                id: id_array[i],
                offsets: goal_area_obj.offsets[i]
            });
        }

        var initial_state_drag = d3.drag()
            .subject(function(d) { return {x: initial_state_obj.ax.x(d.x), y: initial_state_obj.ax.y(d.y)}; })
            .on("start", dragstarted)
            .on("drag", initial_state_dragged)
            .on("end", dragended);
            
        var goal_area_drag = d3.drag()
            .subject(function(d) { return {x: goal_area_obj.ax.x(d.x), y: goal_area_obj.ax.y(d.y)}; })
            .on("start", dragstarted)
            .on("drag", goal_area_dragged)
            .on("end", dragended);

        initial_state_obj.elements()
            .data(initial_state_combinedData)
            .style("cursor", "default")
            .call(initial_state_drag);
            
        goal_area_obj.elements()
            .data(goal_area_combinedData)
            .style("cursor", "default")
            .call(goal_area_drag);

        function dragstarted(d) {
            d3.event.sourceEvent.stopPropagation();
            d3.select(this).classed("dragging", true);
        }

        // TODO Refactor this... why can't we pass obj as input?
        function initial_state_dragged(d) {
            // This is to map the position in pixels of the mouse/element to the element coordinate
            d.x = initial_state_obj.ax.x.invert(d3.event.x);
            d.y = initial_state_obj.ax.y.invert(d3.event.y);
            var index = id_array.indexOf(d.id);
            var formX = d.id+"_x"
            var formY = d.id+"_y" 
            if (index !== -1) {
                x_array[index] = d.x;
                y_array[index] = d.y;
                document.getElementById(formX).value = d.x;
                document.getElementById(formY).value = d.y;
            }            
            document.getElementById("x_array").value = JSON.stringify(x_array);
            document.getElementById("y_array").value = JSON.stringify(y_array);
            d3.select(this)
              .attr("transform", "translate(" + [d3.event.x, d3.event.y] + ")");
        }
        
        function goal_area_dragged(d) {
            d.x = goal_area_obj.ax.x.invert(d3.event.x);
            d.y = goal_area_obj.ax.y.invert(d3.event.y);
            var index = id_array.indexOf(d.id);
            var formX = d.id+"_goal_x"
            var formY = d.id+"_goal_y" 
            if (index !== -1) {
                x_array[index] = d.x;
                y_array[index] = d.y;
                document.getElementById(formX).value = d.x;
                document.getElementById(formY).value = d.y;
            }
            
            document.getElementById("x_array").value = JSON.stringify(x_array);
            document.getElementById("y_array").value = JSON.stringify(y_array);
            
            d3.select(this)
              .attr("transform", "translate(" + [d3.event.x, d3.event.y] + ")");
        }

        function dragended(d) {
            d3.select(this).classed("dragging", false);
        }
    };
    """

    def __init__(self, initial_state_points, goal_area_points, id_array, x_array, y_array):

        if isinstance(initial_state_points, mpl.lines.Line2D):
            initial_state_suffix = "pts"
        else:
            initial_state_suffix = None

        if isinstance(goal_area_points, mpl.lines.Line2D):
            goal_area_suffix = "pts"
        else:
            goal_area_suffix = None

        self.dict_ = {"type": "scenario_drag",
                      # TODO Not sure this is the same as getting
                      "initial_state_id": mpld3.utils.get_id(initial_state_points, initial_state_suffix),
                      "goal_area_id": mpld3.utils.get_id(goal_area_points, goal_area_suffix),
                      "id_array": json.dumps(id_array),
                      "x_array": json.dumps(x_array),
                      "y_array": json.dumps(y_array)}


class NewScenarioDragPlugin(mpld3.plugins.PluginBase):
    """
    This should take care of:
        - visualize/hide the points when add/remove player buttons are pressed
        - position the added markers in the center of the diagram
        - move the markers around and update the global state variables that the form uses during submission
        - store the original position inside the object so we can reset them!
    """
    JAVASCRIPT = r"""
        mpld3.register_plugin("new_scenario_drag", NewScenarioDragPlugin);

        NewScenarioDragPlugin.prototype = Object.create(mpld3.Plugin.prototype);

        NewScenarioDragPlugin.prototype.constructor = NewScenarioDragPlugin;

        NewScenarioDragPlugin.prototype.requiredProps = ["initial_state_ids", "goal_area_ids", "scenario_data", "colors"];

        NewScenarioDragPlugin.prototype.defaultProps = {alpha_fill:0.6,
                                                        alpha_stroke:0.6,
                                                        hoffset:0,
                                                        voffset:10};

        function NewScenarioDragPlugin(fig, props){
            mpld3.Plugin.call(this, fig, props);
            // Ensure during dragging the markers are clearly and always visible; otherwise, their opacity should be 0.6
            mpld3.insert_css("#" + fig.figid + " path.dragging",
                             {"fill-opacity": "1.0 !important",
                              "stroke-opacity": "1.0 !important"});
        };

        NewScenarioDragPlugin.prototype.draw = function(){
            // Register all the functions for dragging, dropping, visualize, and hide and initialize the inputs with the given 
            // scenario data
            
            // Make sure we defined variables that are accessible by enclosed functions
            var scenario_data = this.props.scenario_data;

            // global variable to know which vehicle is selected
            var current_vehicle;
        
            // Get the a reference of each object from their ids. Store the data directly inside them
            // Global for DEBUG
            initial_state_objs = [];
            for( let i = 0; i < this.props.initial_state_ids.length; i++){
                var initial_state_obj = mpld3.get_element(this.props.initial_state_ids[i]);
                initial_state_obj.data = [ scenario_data[i + "_x_is"], scenario_data[i + "_y_is"] ];
                initial_state_objs.push(initial_state_obj);
            }
            var goal_area_objs = []; 
            for( let i = 0; i < this.props.goal_area_ids.length; i++){
                var goal_area_obj = mpld3.get_element(this.props.goal_area_ids[i]);
                goal_area_obj.data = [ scenario_data[i + "_x_ga"], scenario_data[i + "_y_ga"] ];
                goal_area_objs.push(goal_area_obj);
            }
            
            // Not sure this is needed
            var colors = this.props.colors;
            
            // Define the behavioral functions to assign to each element
            // fill-opacity - stoke-opacity
                        
            // Add a button to the figure with a given ID or assume the button is there?
            var plot_buttons_div = document.getElementById("plot-buttons");
            var add_button = document.createElement("a");
            add_button.innerHTML = "Add Vehicle";
            add_button.setAttribute("class", "btn btn-info");
            add_button.setAttribute("role", "button");
            add_button.setAttribute("id", "add-vehicle-btn");
            
            
            var set_default_values = function(index){
                // This assumes the form and the inputs already exist!
                document.getElementById(index + "_x_is").value = scenario_data[index + "_x_is"];
                document.getElementById(index + "_y_is").value = scenario_data[index + "_y_is"];
                document.getElementById(index + "_v_is").value = scenario_data[index + "_v_is"];
                
                document.getElementById(index + "_x_ga").value = scenario_data[index + "_x_ga"];
                document.getElementById(index + "_y_ga").value = scenario_data[index + "_y_ga"];
                
                document.getElementById(index + "_typology").value = scenario_data[index + "_typology"];
            };
            
            var update_the_form = function(index){
                // Get the form
                var the_form = document.getElementById("new-scenario-form");
                
                // Define an utility function to create hidden inputs with given id (but no values... I guess those might be passed as input at this point!)
                var create_hidden_input = function(the_id){
                    hidden_input = document.createElement("input");
                    hidden_input.setAttribute("type", "hidden");
                    hidden_input.setAttribute("id", the_id);
                    hidden_input.setAttribute("name", the_id);

                    return hidden_input;
                }
                 
                the_form.appendChild(create_hidden_input(index + "_x_is"));
                the_form.appendChild(create_hidden_input(index + "_y_is"));
                the_form.appendChild(create_hidden_input(index + "_v_is"));
                
                the_form.appendChild(create_hidden_input(index + "_x_ga"));
                the_form.appendChild(create_hidden_input(index + "_y_ga"));
                
                the_form.appendChild(create_hidden_input(index + "_typology"));
                the_form.appendChild(create_hidden_input(index + "_user_id"));
            }
                    
            var make_player_visible = function(index){
                // Change visibility of the markers
                player_visibility_flags[index] = true;
                
                // TODO Link 0.6 to this.props
                initial_state_objs[index].pathsobj
                        .style("visibility", "visible")
                        .style("stroke-opacity", 0.6)
                        .style("fill-opacity", 0.6);
                // TODO Link 0.6 to this.props
                goal_area_objs[index].pathsobj
                        .style("visibility", "visible")
                        .style("stroke-opacity", 0.6)
                        .style("fill-opacity", 0.6);
            };
            
            var hide_player = function(index){
                // Change visibility of the markers
                player_visibility_flags[index] = false;
                
                var is_obj = initial_state_objs[index];
                // Hide it 
                is_obj.pathsobj.style("visibility", "hidden");
                // Move it back to the original position
                is_obj.pathsobj.attr("transform", "translate("+is_obj.offsetcoords.x(is_obj.data[0])+","+is_obj.offsetcoords.y(is_obj.data[1])+")");
                
                var ga_obj = goal_area_objs[index];
                // Hide it 
                ga_obj.pathsobj.style("visibility", "hidden");
                //
                ga_obj.pathsobj.attr("transform", "translate("+ga_obj.offsetcoords.x(ga_obj.data[0])+","+ga_obj.offsetcoords.y(ga_obj.data[1])+")");
                
                // If you remove a vehicle, then you can sure add another one
                document.getElementById("add-vehicle-btn").classList.remove("disabled");
                                
                // Remove inputs
                document.getElementById(index + "_x_is").remove();
                document.getElementById(index + "_y_is").remove();
                document.getElementById(index + "_v_is").remove();
                
                document.getElementById(index + "_x_ga").remove();
                document.getElementById(index + "_y_ga").remove();
                
                document.getElementById(index + "_typology").remove();
                document.getElementById(index + "_user_id").remove();
            };
            
            ////// Build the modal/panel with the buttons.
            // TODO Add here the flag AV/User
            //      Add here the slider for the speed (0.0 - 90.0 km/h, increment by 1.0 km/h)
            //      Add here the name of the user - Later
            var tooltip = d3.select("body").append("div")
                    .attr("id", "control-tooltip")
                    .attr("class", "mpld3-tooltip")
                    .style("position", "absolute")
                    .style("z-index", "100")
                    .style("visibility", "hidden")
                    .style("color", "black")
                    .style("background-color", "white")
                    .style("border-style", "solid")
                    .style("box-shadow", "5px 5px 5px black");
            
            var the_tooltip = document.getElementById("control-tooltip")
            the_tooltip.innerHTML = ` 
            <table>
                <thead>
                    <tr><th colspan="2" class="text-center">Vehicle's Parameters</th></tr>
                </thead>
                <tbody>
                    <tr><th>Speed</th><td>
                        <label id="speed-selector-label" for="speed-selector">?? Km/h</label>
                        <input type="range" id="speed-selector" name="speed-selector" min="0" max="90"/></td></tr>
                    <tr><th>Color</th><td id="vehicle-color"></td></tr>
                    <tr><th>Type</th>
                        <td>
                            <input type="radio" id="human" name="typology" value="human"><label for="human">Human Driver</label><br>
                            <input type="radio" id="av" name="typology" value="av"><label for="av">AV</label><br>
                        </td>
                    </tr>
                    <tr><th>User</th><td><input type="text" id="user-selector" name="user-id" disabled></td></tr>
                    <tr>
                        <td><a id="remove-btn" class="btn btn-info" role="button">Remove this vehicle</a></td>
                        <td><a id="close-vehicle-parameter-dialog" class="btn btn-info" role="button">Close Dialog</a></td>        
                </tbody>
            </table>`;

            document.getElementById("human").addEventListener('change', function() {
                if (this.checked) {
                    document.getElementById("user-selector").disabled = false;
                }
            });

            document.getElementById("av").addEventListener('change', function() {
                if (this.checked) {
                    document.getElementById("user-selector").disabled = true;
                    document.getElementById("user-selector").value = "";
                    document.getElementById(current_vehicle + "_user_id").value = "";
                }
            });

            document.getElementById("user-selector").addEventListener('input', function() {
                // console.log(current_vehicle);
                document.getElementById(current_vehicle + "_user_id").value = this.value;
            });
            
            document.getElementById("close-vehicle-parameter-dialog").onclick = function(){
                tooltip.style("visibility", "hidden");
            };
            
            // Drag and Drop common functionalities            
            var drag_started = function(d) {
                d3.event.sourceEvent.stopPropagation();
                d3.select(this).classed("dragging", true);
                //console.log("Start dragging " + d );
            }

            var drag_ended = function(d) {
                d3.select(this).classed("dragging", false);
                //console.log("Stop dragging " + d );
            }
  
            var add_controls = function(index) {
                // Configure the vehicle-related functionalities

                //update the global variable
                current_vehicle = index;
                
                // We attach the tooltip to the initial state
                var initial_state_obj = initial_state_objs[index];
                var goal_area_obj = goal_area_objs[index];
                
                // TODO When a vehicle is added, we need to automatically add all the input elements in the form
                //      When the vehicle is removed, we need to automatically remove all the inputs elements in the form
                initial_state_obj.elements()
                    .on("click", function(d, i){
                        // Make sure to configure the tooltip in a way to update the right elements in the form
                        // Show the tooltip
                        tooltip
                            .style("visibility", "visible")
                            .style("top", d3.event.pageY + 10 + "px")
                            .style("left",d3.event.pageX + 0 + "px");
                        // Get the current values for the vehicle from the form
                        var typology = document.getElementById(index + "_typology").value;
                        var user_id = document.getElementById(index + "_user_id").value;
                        var speed = document.getElementById(index + "_v_is").value;

                        // Update the radio buttons and the user-selector field based on the current values
                        document.getElementById("human").checked = typology === 'human';
                        document.getElementById("av").checked = typology === 'av';                       
                        document.getElementById("user-selector").value = user_id;
                        document.getElementById("user-selector").disabled = typology !== 'human';
                        document.getElementById("speed-selector").value = speed;
                        document.getElementById("speed-selector-label").innerText = speed + "Km/h";
                        
                        // Link this button to the player index
                        tooltip.select("a")
                            .on("click", function(d) {
                                    tooltip.style("visibility", "hidden");
                                    hide_player(index);}
                            );
                            
                        var speed_selector = document.getElementById("speed-selector").onclick = function(){
                            // Link the selector to the hidden input value
                            document.getElementById("speed-selector-label").innerText = document.getElementById("speed-selector").value + "Km/h";
                            document.getElementById( index + "_v_is").value = document.getElementById("speed-selector").value;
                        }
                        
                        var vehicle_color = document.getElementById("vehicle-color");
                        // convert to r,b,g
                        var r = (colors[index][0] * 255.0).toFixed(1);
                        var g = (colors[index][1] * 255.0).toFixed(1);
                        var b = (colors[index][2] * 255.0).toFixed(1);
                        //
                        vehicle_color.style.backgroundColor = 'rgb(' + [r,g,b].join(',') + ')';
                        //
                        var update_radio_value = function(){
                            // 'this' refers to the element clicked!
                            document.getElementById( index + "_typology").value = this.value;
                        }
                        document.getElementsByName("typology").forEach( function(elem){
                             elem.onclick = update_radio_value;
                        });
                        
                    });
                    
                // We attach the dragging and dropping functionalities to both the initial_state and goal_area
                
                // We create a specific drag (?) that refer to the initial_state_obj variable
                // TODO Refactor to generate initial_state and goal_area functions/drags programmatically
                // Use partial function application here!?
                            
                var initial_state_drag = d3.drag()
                    .subject(function(d) { return {x: initial_state_obj.ax.x(d.x), y: initial_state_obj.ax.y(d.y)}; })
                    .on("start", drag_started)
                    .on("drag", function(d) {
                            // As long as we are dragging d ... 
                            d.x = initial_state_obj.ax.x.invert(d3.event.x);
                            d.y = initial_state_obj.ax.y.invert(d3.event.y);
                            // Apply the translation to the element we are dragging to move it around
                            d3.select(this).attr("transform", "translate(" + [d3.event.x, d3.event.y] + ")");
                            // Refresh the form - Assume this elements are there!
                            document.getElementById( index + "_x_is").value = d.x;
                            document.getElementById( index + "_y_is").value = d.y;
                        })
                    .on("end", drag_ended);
                
                var goal_area_drag = d3.drag()
                    .subject(function(d) { return {x: goal_area_obj.ax.x(d.x), y: goal_area_obj.ax.y(d.y)}; })
                    .on("start", drag_started)
                    .on("drag", function(d) {
                            // As long as we are dragging d ... 
                            // TODO Update the inputs elements corresponding to d (d.id might be stored somewhere)
                            d.x = goal_area_obj.ax.x.invert(d3.event.x);
                            d.y = goal_area_obj.ax.y.invert(d3.event.y);
                            // Apply the translation to the element we are dragging to move it around
                            d3.select(this).attr("transform", "translate(" + [d3.event.x, d3.event.y] + ")");
                            // Refresh the form - Assume this elements are there!
                            document.getElementById( index + "_x_ga").value = d.x;
                            document.getElementById( index + "_y_ga").value = d.y;
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
            
            add_button.onclick = function(){
                // Take the first nonvisible player and make it visible
                // Initialize its parameters to the default values
                // Add the elements to host its state in the form
                for( let player_index = 0; player_index < player_visibility_flags.length; player_index++){
                    if (player_visibility_flags[player_index] == false){
                        update_the_form(player_index);
                        set_default_values(player_index);
                        make_player_visible(player_index);
                        add_controls(player_index);
                        break;
                    }
                }
                add_button.classList.add("disabled");
                for( let player_index = 0; player_index < player_visibility_flags.length; player_index++){
                    if (player_visibility_flags[player_index] == false){
                        add_button.classList.remove("disabled");
                    }
                }
            }
            
            plot_buttons_div.appendChild(add_button);

            // Ensure that if a vehicle is visible we can see it!            
            player_visibility_flags = [];
            for( let player_index = 0; player_index < this.props.goal_area_ids.length; player_index++){ 
                player_visibility_flags.push( scenario_data[player_index + "_is_visible"] );
                if (scenario_data[player_index + "_is_visible"]){
                    // Same behavior of clicking add button
                    update_the_form(player_index);
                    set_default_values(player_index);
                    make_player_visible(player_index);
                    add_controls(player_index);
                }
            }

        };
    """

    def __init__(self, initial_state_points, goal_area_points, scenario_data, colors):
        """
        :param initial_state_points: the matplot lib object
        :param goal_area_points:  same as before
        :param scenario_data:  the initial value for all the data of all the players and a visibility flag
        :param colors: make sure we use different colors
        """
        import matplotlib

        def get_collections_of_ids(collections_of_points):
            collections_of_ids = []
            for points in collections_of_points:
                if isinstance(points, matplotlib.lines.Line2D):
                    suffix = "pts"
                else:
                    suffix = None
                collections_of_ids.append(mpld3.utils.get_id(points, suffix))
            return collections_of_ids

        self.dict_ = {"type": "new_scenario_drag",
                      "initial_state_ids": get_collections_of_ids(initial_state_points),
                      "goal_area_ids": get_collections_of_ids(goal_area_points),
                      "scenario_data": scenario_data,
                      "colors": colors}

