import theme
import os
import uuid
import shutil
import shutil
import time
import json

from json.decoder import JSONDecodeError

from pathlib import Path
from nicegui import app, ui


from roadlogic.backend import generate_scenarios

async def store_to_file_and_invoke_generate_scenarios(button: ui.button,
                                                      output_grid: ui.refreshable,
                                                        output_folder: str,
                                                        input_n: int,
                                                        osc_file: str, osc_editor,
                                                        rule_injection_file: str, rule_injection_editor,
                                                        additional_parameters_file: str,
                                                        the_map_file: str):
        # Store to file the inputs so they stay there
        # TODO: This inject \n everywhere...
        with open(osc_file, 'w') as fw:
            fw.writelines(osc_editor.value)

        with open(rule_injection_file, "w") as fw:
            fw.writelines(rule_injection_editor.value)

        input_n.sanitize()
        n_scenarios = int(input_n.value)

        # print(f"Clean up {output_folder}")
        shutil.rmtree(output_folder)
        os.makedirs(output_folder, exist_ok=False)

        # print(f"Generating {n_scenarios} \n\n ")
        additional_parameters_as_dict = {}
        additional_parameters_as_dict["n_scenarios"] = n_scenarios
        # additional_parameters_as_dict["map_name"] = map_name

        with open(additional_parameters_file, "w") as fw:
            json.dump(additional_parameters_as_dict, fw)

        # Invoke 
        generate_scenarios(button, n_scenarios, output_folder, osc_file, rule_injection_file, the_map_file)

        # Eventually refresh. This could be probably done on the fly
        output_grid.refresh()
        
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
            return [ os.path.basename(s).split(".")[0].split("_")[1] for s in os.listdir(cr_scenarios_folder) if os.path.isfile(os.path.join(cr_scenarios_folder, s))]
    
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


    @ui.refreshable
    def output_grid(session_id: str) -> None:
        # Look up the scenarios generated if any
        scenario_ids = list_scenarios(session_id)
        if len(scenario_ids) > 0:
            with ui.grid(columns=4).classes('w-full').style('padding: 20px'):
                ui.label('Generated Scenarios').classes('text-h5')
                # Link the files PER scenario building a view over the various folders
                for scenario_id in scenario_ids:
                    # Todo we assume n_scenarios were all created
                    # '/rawfiles' -> output
                    # animations -> ASP Animation
                    # asp
                    # cr_scenarios
                    # cr_simulations
                    # instance.lp
                    # plans
                    # serialized_models

                    with ui.card().classes('col-span-full'):
                        ui.label(f'Scenario {scenario_id}').classes('text-h6')
                        ui.link('ASP Animation', f'/rawfiles/{session_id}/out/animations/anim_{scenario_id}.gif', new_tab=True)
                        ui.link('CR Scenario', f'/rawfiles/{session_id}/out/cr_simulations/scenario_{scenario_id}/simulation_00001/scenario.jpg', new_tab=True)
                        ui.link('CR Animation', f'/rawfiles/{session_id}/out/cr_simulations/scenario_{scenario_id}/simulation_00001/scenario.jpg', new_tab=True)



    @ui.page('/sessions/{session_id}')
    def show_session(session_id: str):
        with theme.frame(f'Scenario Generation (Session {session_id})'):
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
            
            # At this point the session must exist, we visualize it with the components by reading the 
            # content of the various files.
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

            # The input section shows the spec and extra atoms - they cannot change asynchronously
            with ui.grid(columns=2).classes('w-full').style('padding: 20px'):
                # Row 1
                with ui.card():
                    ui.label('OpenScenario DSL Editor')
                    osc_editor = ui.codemirror(osc_spec, language='Python').classes('h-100')
                    # TODO Add a save button
                with ui.card():
                    ui.label('Extra ASP Rules Editor')
                    rule_injection_editor = ui.codemirror(extra_rules, language='Python').classes('h-100')
                    # TODO Add a save button

                # Row 2
                with ui.card().classes('col-span-full'):
                    input_n = ui.number("N", value=n_scenarios, min=1, max=10)
                    ui.label(f"Using Map: 3 Lanes (Hardcoded)")
                    # Clicking this will trigger the generation process, which delete the previous out folder, and then regenerate the stuff
                    ui.button('Generate!', on_click=lambda e: store_to_file_and_invoke_generate_scenarios(e.sender,
                                                                                                          output_grid,
                                                        output_folder,
                                                        input_n,
                                                        osc_file, osc_editor,
                                                        rule_injection_file, rule_injection_editor,
                                                        additional_parameters_file,
                                                        the_map_file))

            # Create the part showing the outputs, this is refreshed every time without reloading the page
            output_grid(session_id)


    @ui.page('/')
    def landing_page():
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


# def root():
#     ui.label(f'This ID {str(uuid4())[:6]} changes only on reload.')
#     ui.separator()
#     ui.sub_pages({'/': main, '/other': other})

# def main():
#     ui.label('Main page content')
#     ui.link('Go to other page', '/other')

# def other():
#     ui.label('Another page content')
#     ui.link('Go to main page', '/')