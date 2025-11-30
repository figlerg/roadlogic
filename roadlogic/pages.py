import theme
import os
import uuid
import shutil
import shutil
import time
import json

from pathlib import Path
from nicegui import app, ui


from roadlogic.backend import generate_scenarios

async def store_to_file_and_invoke_generate_scenarios(button: ui.button,
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

        print(f"\n\n Generating {n_scenarios} \n\n ")
        
        additional_parameters_as_dict = {}
        additional_parameters_as_dict["n_scenarios"] = n_scenarios
        # additional_parameters_as_dict["map_name"] = map_name

        with open(additional_parameters_file, "w") as fw:
            json.dump(additional_parameters_as_dict, fw)

        # Invoke 
        generate_scenarios(button, n_scenarios, output_folder, osc_file, rule_injection_file, the_map_file)
        
def create(global_output_folder: str, default_map_file: str) -> None:
    
    def generate_new_session_id():
        return uuid.uuid4()
    
    def list_sessions():
        return list(os.listdir(global_output_folder))
    
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


    @ui.page('/sessions/{session_id}')
    def show_session(session_id: str):
        with theme.frame(f'- Scenario Generation (Session {session_id})-'):
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
            with open(additional_parameters_file, "r") as rf:
                additional_parameters_as_dict = json.load(rf)

            n_scenarios = 1 if "n_scenarios" not in additional_parameters_as_dict else additional_parameters_as_dict["n_scenarios"]


            # The input section shows the spec and extra atoms
            input_grid = ui.grid(columns=2).classes('w-full gap-0')

            # The output section lists the files but group them by scenario if possible
            output_grid = ui.grid(columns=4).classes('w-full gap-0')

            with input_grid:
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
                    # Clicking this will trigger the generation process

                    ui.button('Generate!', on_click=lambda e: store_to_file_and_invoke_generate_scenarios(e.sender,
                                                        output_folder,
                                                        input_n,
                                                        osc_file, osc_editor,
                                                        rule_injection_file, rule_injection_editor,
                                                        additional_parameters_file,
                                                        the_map_file))

            # Build the output grid from the files generated so far inside the output_folder
            with output_grid:
                ui.label('Generated Scenarios').classes('text-h5')
                # Link the files PER scenario building a view over the various folders
                for scenario_id in [str(s).rjust(4, "0") for s in range(1, n_scenarios+1)]:
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
                pass


    @ui.page('/')
    def page_a():
        with theme.frame('- Home Page-'):
            ui.link('Create New Session', f'/sessions/{generate_new_session_id()}')
            ui.label('Resume Past Sessions')
            # Look up the past folders inside output_folder
            for dir_name in list_sessions():
                ui.link(f'Resume session {dir_name}', f'/sessions/{dir_name}')
            for dir_name in list_sessions():
                ui.button(f'Delete Session {dir_name}', on_click=lambda: delete_session(dir_name))


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