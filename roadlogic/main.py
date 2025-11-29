import httpx
import os
import uuid
import shutil

from contextlib import contextmanager
from nicegui import ui

########################################################
#       FORCEFULLY IMPORT ALL THE PACKAGES  -> TODO REFACTOR!!!
########################################################
import sys

folder_containing_this_script = os.path.dirname(os.path.realpath(__file__))
root_of_project = os.path.dirname(folder_containing_this_script)

# Import the root of this project
sys.path.insert(0, root_of_project)

# Import the monitoring libs
# $(ROOT_DIR)/monitoring/syma-arv:$(ROOT_DIR):$(ROOT_DIR)/monitoring/syma
# for dep in ["commonroad_extensions", "create_scenarios", "Frenetix-Motion-Planner", "monitoring", "planning"]:
#     to_import = os.path.join(root_of_project, dep)
#     print(f"Importing {to_import}")
sys.path.append(os.path.join(root_of_project, "monitoring", "syma-arv"))
sys.path.append(os.path.join(root_of_project, "monitoring", "syma"))

# Input to scenario generation:
#   the spec in osc served from the Left CodeMirror Editor
#   the map pointing to CommonRoad scenario hard coded
#   the number of input to generate, served from the input form
#   additional constraints to inject server from the Right  CodeMirror Editor
# the_map_file = os.path.
# Sample SPEC

osc_spec = """
# 2 cars behind each other. one moves to other lane, then other moves to other lane

scenario follow:
    p: path
    car1: car
    ego: car

    do parallel(duration:  [3s..20s]):

        c0: car1.drive(p)

        c1: serial:
            c1_0: ego.drive(p) with:
                position([10m..20m], behind:car1, at:start)
                lane(same_as:car1, at:start)
                lane(left_of:car1, at:end)
            c1_1: ego.drive(p) with:
                lane(same_as:car1, at:end)
                position([1m..30m], behind:car1, at:end)
"""


# maps

the_map_name = "threelanes"
the_map_file = os.path.join(folder_containing_this_script, "maps", f"{the_map_name}.xml")

OUTPUT_FOLDER = os.path.join(folder_containing_this_script, "output")
if not os.path.exists(OUTPUT_FOLDER):
    print(f"Create the output folder {OUTPUT_FOLDER}")
    os.makedirs(OUTPUT_FOLDER)

# Global elements of the main page. Use them to update the visualization dynamically, e.g., 
#   by adding elements on the fly to output_grid
input_grid = ui.grid(columns=2).classes('w-full gap-0')
output_grid = ui.grid(columns=4).classes('w-full gap-0')


# Call backs and the like
@contextmanager
def disable(button: ui.button):
    button.disable()
    try:
        yield
    finally:
        button.enable()

async def generate_scenarios(button: ui.button, 
                             input_n: int, osc: str, extra_rules: str, the_map_file: str) -> None:
    """
    Generate the n scenarios. This will create a bunch of folder in the data directory, etc.
    
    :param button: Description
    :type button: ui.button
    :param n: Description
    :type n: int
    """
    # Avoid multiple submissions
    with disable(button):
        # Ensure each request is treated uniquely
        execution_id = f"execution-{uuid.uuid4()}"
        execution_folder = os.path.join(OUTPUT_FOLDER, execution_id)
        os.makedirs(execution_folder, exist_ok=False)

        # Setup the expected structure for generating the scenario (according to our current setup)        
        input_folder = os.path.join(execution_folder, "in")
        os.makedirs(input_folder)

        # Store the specs to the spec.osc file
        osc_file = os.path.join(input_folder, "spec.osc")
        with open(osc_file, "w+") as osc_file_writer:
            osc_file_writer.writelines(osc)

        # Store the additional rules to the rule_injection.lp file
        rule_injection_file = os.path.join(input_folder, "rule_injection.lp")
        with open(rule_injection_file, "w+") as rule_injection_file:
            rule_injection_file.writelines(extra_rules)

        # Copy over the map
        output_map_file = os.path.join(input_folder, "the_map.xml")
        shutil.copy(the_map_file, output_map_file)

        output_folder = os.path.join(execution_folder, "out")
        os.makedirs(output_folder)
        
        osc_output_folder = os.path.join(output_folder, "cr_simulations")
        # Start the generation process

        # Note this is a Click command object, not a regular python function
        # See: https://stackoverflow.com/questions/48619517/call-a-click-command-from-code
        from create_scenarios.create_plan_scenarios import main as generate_osc_scenarios

        try:
            arguments = list()
            arguments.extend(["--osc-file", f"{osc_file}"])
            arguments.extend(["--n", f"{input_n}"])
            arguments.extend(["--cr-scenario", f"{output_map_file}"])
            arguments.extend(["--output-folder", f"{output_folder}"])
            
            if len(extra_rules) > 0:
                arguments.extend(["--rule-injection", f"{rule_injection_file}"])

            generate_osc_scenarios( arguments, standalone_mode=False)

            ui.notify(f"Done !")
            with output_grid:
                ui.label(f"Output is available in this folder {output_folder}")

        except Exception as e:
            print(f"ERROR {e}!")
            ui.notify(f"ERROR {e}!")


#   time_step "execute-all-scenarios" \
#   make execute-all-scenarios \
#     SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
#     OUTPUT_FOLDER="$EXP/out/cr_simulations"

#   time_step "compute-metrics" \
#   make -j 8 \
#     SCENARIOS_FOLDER=$EXP/out/cr_scenarios \
#     OUTPUT_FOLDER=$EXP/out/cr_simulations \
#     compute-selected-metrics-for-all-scenarios

#   time_step "generate-summary" \
#   make generate-summary \
#     SCENARIOS_FOLDER="$EXP/out/cr_scenarios" \
#     OUTPUT_FOLDER="$EXP/out/cr_simulations" \
#     OSC_FILE="$EXP/in/spec.osc"
        #
        
        # async with httpx.AsyncClient() as client:
        #     response = await client.get('https://httpbin.org/delay/1', timeout=5)
        # ui.notify(f'Generating : {input_n}, {osc}, {extra_rules}')

#######################


with input_grid:
    # Row 1
    with ui.card():
        ui.label('OpenScenario DSL Editor')
        osc_editor = ui.codemirror(osc_spec, language='Python').classes('h-100')
    with ui.card():
        ui.label('Extra ASP Rules Editor')
        extra_rule_editor = ui.codemirror('', language='Python').classes('h-100')
    # Row 2
    with ui.card().classes('col-span-full'):
        input_n = ui.number("N", value=1, min=1, max=10)
        input_n.sanitize()
        # Show the map name
        ui.label(f"Using Map: {the_map_name}")
        # Clicking this will trigger the generation process
        ui.button('Generate!', on_click=lambda e: generate_scenarios(e.sender, input_n.value, osc_editor.value, extra_rule_editor.value, the_map_file))


with output_grid:
    pass

ui.run()