import os
import uuid
import shutil

from contextlib import contextmanager
from nicegui import ui

def generate_scenarios(button: ui.button, n_scenarios: int, output_folder: str, osc_file: str, rule_injection_file: str, the_map_file: str) -> None:
    """
    Invoke the logic to generate the scenarios, and disable the generate button while doing so.
    This method creates a folders and files using the same click.Commands we invoke from the Makefile
    """
    # Call backs and the like
    @contextmanager
    def disable(button: ui.button):
        button.disable()
        try:
            yield
        finally:
            button.enable()

    # Avoid multiple submissions
    with disable(button):
        # Start the generation process

        # Note this is a Click command object, not a regular python function
        # See: https://stackoverflow.com/questions/48619517/call-a-click-command-from-code
        from create_scenarios.create_plan_scenarios import main as generate_osc_scenarios

        try:
            arguments = list()

            arguments.extend(["--osc-file", f"{osc_file}"])
            arguments.extend(["--n", f"{n_scenarios}"])
            arguments.extend(["--cr-scenario", f"{the_map_file}"])
            arguments.extend(["--output-folder", f"{output_folder}"])
            arguments.extend(["--rule-injection", f"{rule_injection_file}"])

            generate_osc_scenarios( arguments, standalone_mode=False)

            ui.notify(f"Done Generating ASP Plans!")
            # with output_grid:
            #     ui.label(f"Output is available in this folder {output_folder}")

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