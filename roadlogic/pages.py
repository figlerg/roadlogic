import theme
import os
import uuid
import shutil
import json

import asyncio

from contextlib import contextmanager

from json.decoder import JSONDecodeError

from pathlib import Path
from nicegui import app, ui, background_tasks

# Note this is a Click command object, not a regular python function
# See: https://stackoverflow.com/questions/48619517/call-a-click-command-from-code

from gui.mixed_traffic_scenario import scenario_editor
from create_scenarios.create_plan_scenarios import main as generate_osc_scenario
from cli import cli as roadloagic_cli


def create(global_output_folder: str, default_map_file: str) -> None:
    
    def generate_new_session_id():
        return uuid.uuid4()
    
    def list_sessions():
        """
        By design the sessions are stored in the global_output_folder as directories. Only directories identify sessions.
        """
        return [d for d in os.listdir(global_output_folder) if os.path.isdir(os.path.join(global_output_folder, d))]
    
    def list_scenarios(session_id: str):
        # Uses an heuristic, generally bad
        output_folder_in_session = os.path.join(global_output_folder, str(session_id), "out")
        cr_scenarios_folder = os.path.join(output_folder_in_session, "cr_scenarios")
        if not os.path.exists(output_folder_in_session) or not os.path.exists(cr_scenarios_folder):
            return []
        else:
            # Look inside the generated scenario folder
            return sorted([ os.path.basename(s).split(".")[0].split("_")[1] for s in os.listdir(cr_scenarios_folder) if os.path.isfile(os.path.join(cr_scenarios_folder, s))])
    
    def delete_session(session_id: str):
        execution_folder = os.path.join(global_output_folder, session_id)
        # resolve to absolute and delete only if inside
        child_path = Path(execution_folder)
        if child_path.resolve().is_relative_to(global_output_folder):
            print(f"Remove {child_path}")
            shutil.rmtree(execution_folder)
            # This will not be shown because we reload the entire page. Replace the list of sessions with a @refreshable component
            ui.notify('Session Deleted')
            ui.navigate.reload()

    ######
    async def generation_pipeline(session_id: str, button: ui.button, progressbar: ui.linear_progress, output_grid: ui.refreshable, osc_editor: ui.codemirror, rule_injection_editor: ui.codemirror, input_n: ui.number):
        # TODO Wrap this into a ScenarioEditingSession object
        execution_folder = os.path.join(global_output_folder, session_id)
        input_folder = os.path.join(execution_folder, "in")
        output_folder = os.path.join(execution_folder, "out")
        scenarios_folder = os.path.join(output_folder, "cr_scenarios")
        simulations_folder = os.path.join(output_folder, "cr_simulations")
        osc_file = os.path.join(input_folder, "spec.osc")
        rule_injection_file = os.path.join(input_folder, "rule_injection.lp")
        the_map_file = os.path.join(input_folder, "the_map.xml")
        additional_parameters_file = os.path.join(input_folder, "additional_parameters.json")

        # parse the input
        input_n.sanitize()
        n_scenarios = int(input_n.value)

        # TODO: Ideally we should encapsulate each step into a function
        # 1 = Setup folders 
        # 1 = Create ASP Scenarios and Animation
        # 4 * n = Execute, Compute Metrics, Plot, and Animate each scenario
        how_many_tasks = 1 + 1 + 4 * n_scenarios
        progress_tick = 1.0 / how_many_tasks
        
        progressbar.set_value(0.0)

        ##################################################
        # Store to file the inputs so they stay there
        with open(osc_file, 'w') as fw:
            fw.writelines(osc_editor.value)

        with open(rule_injection_file, "w") as fw:
            fw.writelines(rule_injection_editor.value)

        additional_parameters_as_dict = {}
        additional_parameters_as_dict["n_scenarios"] = n_scenarios

        with open(additional_parameters_file, "w") as fw:
            json.dump(additional_parameters_as_dict, fw)
        
        # Clean up the output folder
        shutil.rmtree(output_folder)
        os.makedirs(output_folder, exist_ok=False)
        
        ##################################################
        progressbar.set_value(progressbar.value + progress_tick)
        # Enable the update of the page by blocking this coroutine
        await asyncio.sleep(1)
        ##################################################
        arguments = list()

        arguments.extend(["--osc-file", f"{osc_file}"])
        arguments.extend(["--n", f"{n_scenarios}"])
        arguments.extend(["--cr-scenario", f"{the_map_file}"])
        arguments.extend(["--output-folder", f"{output_folder}"])
        arguments.extend(["--rule-injection", f"{rule_injection_file}"])

        generate_osc_scenario(arguments, standalone_mode=False)
        
        ##################################################
        progressbar.set_value(progressbar.value + progress_tick)
        # Enable the update of the page by blocking this coroutine
        await asyncio.sleep(1)
        ##################################################

        # Execute, Compute metrics, Plot, and Animate
        await asyncio.sleep(1)
        for index, scenario_id in enumerate(list_scenarios(session_id), start=1):
            scenario_name = f"scenario_{scenario_id}"
            arguments = list()
            scenario_output_folder = os.path.join(f"{simulations_folder}", f"{scenario_name}")
            arguments.extend(["--output-folder", f"{scenario_output_folder}"])
            # Command to execute
            arguments.extend(["execute-scenario"])
            # scenarios_folder
            scenario_file = os.path.join(scenarios_folder, f"{scenario_name}.xml")
            arguments.extend(["--scenario-file", f"{scenario_file}"])
            arguments.extend(["--simulation-id", "00001"])
            # Invoke the CLI
            roadloagic_cli(arguments, standalone_mode=False)
        
            ##################################################
            progressbar.set_value(progressbar.value + progress_tick)
            # Enable the update of the page by blocking this coroutine
            await asyncio.sleep(1)
            ##################################################
        
        for index, scenario_id in enumerate(list_scenarios(session_id), start=1):
            scenario_name = f"scenario_{scenario_id}"
            arguments = list()
            scenario_output_folder = os.path.join(f"{simulations_folder}", f"{scenario_name}")
            arguments.extend(["--output-folder", f"{scenario_output_folder}"])
            # Command to execute
            arguments.extend(["compute-metrics"])
            # scenarios_folder
            scenario_file = os.path.join(scenarios_folder, f"{scenario_name}.xml")
            # selected_metrics
            arguments.extend(["--metric", "LANE"])
            arguments.extend(["--metric", "LONGPOS"])
            # Folder containing the simulated scenario data
            arguments.extend(["--simulation-folder", os.path.join(f"{scenario_output_folder}", "simulation_00001")])
            arguments.extend(["--group-by", "SINGLE"])
            # Invoke the CLI
            roadloagic_cli(arguments, standalone_mode=False)

            ##################################################
            progressbar.set_value(progressbar.value + progress_tick)
            # Enable the update of the page by blocking this coroutine
            await asyncio.sleep(1)
            ##################################################
        

        # TODO: This might be broken
        # generate_summary(arguments, standalone_mode=False)
        # progressbar.set_value(0.6)
        # await asyncio.sleep(1)

        # TODO: Trigger this with a different command
        # compute_similarity(arguments, standalone_mode=False)
        # progressbar.set_value(0.7)
        # await asyncio.sleep(1)

        for index, scenario_id in enumerate(list_scenarios(session_id), start=1):
            # Plot the scenarios
            scenario_name = f"scenario_{scenario_id}"
            scenario_output_folder = os.path.join(f"{simulations_folder}", f"{scenario_name}")
            simulation_00001_folder = os.path.join(f"{scenario_output_folder}", "simulation_00001")
            plots_folder = os.path.join(f"{simulation_00001_folder}", "plots")
            # Collect the arguments for plotting
            arguments = list()
            # Output the plots here
            arguments.extend(["--output-folder", f"{plots_folder}"])
            # Execute the command to plot the simulation
            arguments.extend(["plot-simulation"])
            # Take simulated scenario data from here
            arguments.extend(["--simulation-folder", f"{simulation_00001_folder}"])
            # Invoke the CLI
            roadloagic_cli(arguments, standalone_mode=False)

            ##################################################
            progressbar.set_value(progressbar.value + progress_tick)
            # Enable the update of the page by blocking this coroutine
            await asyncio.sleep(1)
            ##################################################

            # Collect the arguments for animating 
            arguments = list()
            # Output the plots here
            arguments.extend(["--output-folder", f"{simulation_00001_folder}"])
            # Execute the command to plot the simulation
            arguments.extend(["animate-simulation"])
            # Take simulated scenario data from here
            arguments.extend(["--plots-folder", f"{plots_folder}"])
            # Invoke the CLI
            roadloagic_cli(arguments, standalone_mode=False)

            ##################################################
            progressbar.set_value(progressbar.value + progress_tick)
            # Enable the update of the page by blocking this coroutine
            await asyncio.sleep(1)
            ##################################################
            
        button.enable()
        progressbar.visible = False
        output_grid.refresh()       

    async def start_generation(session_id: str, button: ui.button, input_grid:ui.refreshable, progressbar: ui.linear_progress, output_grid: ui.refreshable,
                               osc_editor: ui.codemirror, rule_injection_editor: ui.codemirror, input_n: ui.number):
        """
        Trigger the scenario generation ensuring that the button is disabled while the process runs, and the progress bar is shown.
        By the end of the process, the output_grid is reloaded
        """
        button.disable()
        progressbar.visible = True
        background_tasks.create(generation_pipeline(session_id, button, progressbar, output_grid, osc_editor, rule_injection_editor, input_n))

    async def compute_diversity(session_id: str, content: ui.grid, output_grid: ui.refreshable):
        content.clear()
        # background_tasks.create(generation_pipeline(session_id, output_grid))
        raise NotImplementedError("THIS NOT READY YET!")

    @ui.refreshable
    def output_grid(session_id: str) -> None:
        """
        Build the input panel, titled Scenario Editor. Content is read from the storage (i.e., files) based on the session_id
        """
        execution_folder = os.path.join(global_output_folder, session_id)
        input_folder = os.path.join(execution_folder, "in")
        output_folder = os.path.join(execution_folder, "out")
        diversity_plot = os.path.join(output_folder, "diversity.png")

        # Look up the scenarios generated if any
        scenario_ids = list_scenarios(session_id)
        with ui.expansion().classes('w-full') as expansion:
            with expansion.add_slot('header'):
                ui.label(f'Generated Scenarios ({len(scenario_ids)})').classes('text-h4')
            with ui.grid(columns=2).classes('w-full').style('padding: 20px'):
                # Left Column shows scenarios
                with ui.grid(columns=2).classes('w-full'):
                    # Link the files for each scenario, thus building a view over the various folders/files
                    for scenario_id in scenario_ids:
                        with ui.card(): # .classes('col-span-full'):
                            # TODO Add monitoring results, validity checks
                            # TODO Optionally Add logs, APS outputs, 
                            ui.label(f'Scenario {scenario_id}').classes('text-h6')
                            ui.link('ASP Animation', f'/rawfiles/{session_id}/out/animations/anim_{scenario_id}.gif', new_tab=True)
                            ui.link('CR Scenario', f'/rawfiles/{session_id}/out/cr_simulations/scenario_{scenario_id}/simulation_00001/scenario.jpg', new_tab=True)
                            ui.link('CR Animation', f'/rawfiles/{session_id}/out/cr_simulations/scenario_{scenario_id}/simulation_00001/simulation.gif', new_tab=True)
                # Right Column shows diversity or the button to compute it
                with ui.grid().classes('w-full') as content:
                    # If diversity if NOT there show the button
                    # Otherwise show the picture
                    if os.path.exists(diversity_plot):
                        ui.label("Here's the diversity plot")
                    else:
                        with ui.card():
                            ui.button("COMPUTE DIVERSITY!", on_click=lambda: compute_diversity(session_id, content))
                
    
    @ui.refreshable
    def input_grid(session_id: str, output_grid: ui.refreshable) -> None:
        """
        Build the input panel, titled Scenario Editor. Content is read from the storage (i.e., files) based on the session_id
        """
        execution_folder = os.path.join(global_output_folder, session_id)
        input_folder = os.path.join(execution_folder, "in")
        output_folder = os.path.join(execution_folder, "out")
        osc_file = os.path.join(input_folder, "spec.osc")
        rule_injection_file = os.path.join(input_folder, "rule_injection.lp")
        the_map_file = os.path.join(input_folder, "the_map.xml")
        additional_parameters_file = os.path.join(input_folder, "additional_parameters.json")
        
        # Load the content from the storage/files
        osc_spec = ""
        with open(osc_file, 'r') as rf:
            osc_spec = "".join(rf.readlines())
            
        extra_rules = ""
        with open(rule_injection_file, 'r') as rf:
            extra_rules =  "".join(rf.readlines())

        additional_parameters_as_dict = {}
        try:
            with open(additional_parameters_file, "r") as rf:
                additional_parameters_as_dict = json.load(rf)
        except JSONDecodeError as json_error:
            # This happens if the file is empty
            pass

        n_scenarios = 1 if "n_scenarios" not in additional_parameters_as_dict else additional_parameters_as_dict["n_scenarios"]

        with ui.expansion(value=True).classes('w-full') as expansion:
            # Show a nice title for the expansion
            with expansion.add_slot('header'):
                ui.label(f'Scenario Editor').classes('text-h4')

            # Build the content of the expansion
            with ui.grid(columns=2).classes('w-full').style('padding: 20px'):
                # Row 1
                with ui.card():
                    ui.label('OpenScenario DSL Editor').classes('text-h6')
                    osc_editor = ui.codemirror(osc_spec, language='Python').classes('h-100')
                    # TODO Add a save button
                with ui.card():
                    ui.label('Extra ASP Rules Editor').classes('text-h6')
                    rule_injection_editor = ui.codemirror(extra_rules, language='Python').classes('h-100')
                    # TODO Add a save button

                # Row 2
                with ui.card().classes('col-span-full'):
                    input_n = ui.number("N", value=n_scenarios, min=1, max=10).classes('text-h6')
                    ui.label(f"Using Map: 3 Lanes (Hardcoded)").classes('text-h6')
                
                # Row 3
                # TODO Button is not disabled, the progress bar is not visible, the spinner starts late

                with ui.card().classes('col-span-full'):
                    # Define the global progressbar
                    progressbar = ui.linear_progress(value=0, size="50px", show_value=False).props('instant-feedback')
                    # TODO: Make it invisible by default
                    progressbar.visible = False
                    ui.button('Generate!', on_click=lambda e: start_generation(session_id, e.sender, input_grid, progressbar, output_grid, osc_editor, rule_injection_editor, input_n))


    def _ensure_folders_exists(session_id: str):
        
        # TODO This should be wrapped in an object most likely
        execution_folder = os.path.join(global_output_folder, session_id)
        input_folder = os.path.join(execution_folder, "in")
        output_folder = os.path.join(execution_folder, "out")
        osc_file = os.path.join(input_folder, "spec.osc")
        rule_injection_file = os.path.join(input_folder, "rule_injection.lp")
        the_map_file = os.path.join(input_folder, "the_map.xml")
        additional_parameters_file = os.path.join(input_folder, "additional_parameters.json")

        # Create if not existing
        if session_id not in list_sessions():
            # Debug
            print(f"Generate new session {session_id}")
            
            # Create the folder hosting the session
            os.makedirs(execution_folder, exist_ok=False)
            # Setup the expected structure for generating the scenario (according to our current setup)        
            os.makedirs(input_folder)
            os.makedirs(output_folder)

            # Create an empty spec.osc file into the input folder
            with open(osc_file, 'w'):
                os.utime(osc_file, None)
            
            # Create an empty rule_injection.lp file into the input folder
            with open(rule_injection_file, "w"):
                os.utime(rule_injection_file, None)
            
            with open(additional_parameters_file, "w"):
                os.utime(additional_parameters_file, None)

            # Copy over the default map
            shutil.copy(default_map_file, the_map_file)

    @ui.page('/sessions/{session_id}')
    def show_session(session_id: str):
        """
        Generate the page associated to a session for scenario editing.
        Each session is backed up by a folder with various input and output files.
        
        :param session_id: Description
        :type session_id: str
        """

        _ensure_folders_exists(session_id)

        with theme.frame(f'Scenario Generation (Session {session_id})'):
            # Visualize the input form and link it to the refreshable output part of the page and the progressbar
            input_grid(session_id, output_grid)
            
            # Visualize the output grid based on the content of the file
            output_grid(session_id)

    @ui.page('/test')
    def show_scenario_editor():
        """
        Generate the page that allows to manually generate scenarios (currently, using an hardcoded map)
        The setup follow this logic:
        - Create buttons using nicegui and give them know and predefined ids
        - Pass the ids of the buttons to the logic that renders the plugin
        
        """
        @ui.refreshable
        def output_view() -> None:
            """
            Build the input panel, titled Scenario Editor. Content is read from the storage (i.e., files) based on the session_id
            """
            # Look up in the global_output_folder the sessions that contain manual_scenario.xml files
            manually_generated_session_ids = []
            for session_id_folder in [s for s in os.listdir(global_output_folder) if os.path.isdir(os.path.join(global_output_folder, s))]:
                target_file = os.path.join(global_output_folder, session_id_folder, "out", "cr_scenarios", "manual-scenario.xml")
                if os.path.exists(target_file ):
                    manually_generated_session_ids.append(session_id_folder)

            with ui.expansion().classes('w-full') as expansion:
                with expansion.add_slot('header'):
                    ui.label(f'Generated Scenarios ({len(manually_generated_session_ids)})').classes('text-h4')
                with ui.grid(columns=2).classes('w-full').style('padding: 20px'):
                    # Left Column shows scenarios
                    with ui.grid(columns=2).classes('w-full'):
                        # Link the files for each scenario, thus building a view over the various folders/files
                        for session_id in manually_generated_session_ids:
                            with ui.card(): # .classes('col-span-full'):
                                # TODO Add monitoring results, validity checks
                                # TODO Optionally Add logs, APS outputs, 
                                ui.label(f'Scenario').classes('text-h6')
                                ui.button('Scenario XML', on_click=lambda: ui.download.from_url(f'/rawfiles/{session_id}/out/cr_simulations/scenario/simulation_00001/scenario.xml'))
                                ui.link('Scenario Animation', f'/rawfiles/{session_id}/out/cr_simulations/scenario/simulation_00001/simulation.gif', new_tab=True)

        # Input section shows the visual/interactive editor
        with ui.expansion(value=True).classes('w-full') as expansion:
            # Show a nice title for the expansion
            with expansion.add_slot('header'):
                ui.label(f'Scenario Editor').classes('text-h4')

            # Build the content of the expansion
            with ui.card().classes('w-full').style('padding: 20px') as container:
                # Pass the output view, so we can call refresh once generation if completed
                scenario_editor(global_output_folder, default_map_file, container, output_view)
        
        # Render the output view
        output_view()

    @ui.page('/')
    def landing_page():
        """
        Generate the landing page
        """
        with theme.frame('Home Page'):
            with ui.card().classes('w-full'):
                ui.label('Start A New Session').classes('text-h5') #.classes('w-200')
                ui.button('Create A New Session', on_click=lambda: ui.navigate.to(f'/sessions/{generate_new_session_id()}'))
                ui.label('Resume Past Sessions').classes('text-h5')
                if len(list_sessions()) > 0:
                    with ui.grid(columns=3):
                        ui.label("Session").classes('font-bold')
                        ui.label("")
                        ui.label("")
                        # Look up the past folders inside output_folder
                        for session_id in list_sessions():
                            ui.label(f"{session_id}")
                            ui.button(f'Resume', on_click=lambda: ui.navigate.to(f'/sessions/{session_id}'))
                            ui.button(f'Delete', on_click=lambda: delete_session(session_id))
                else:
                    ui.label("Empty").classes('text-h5')