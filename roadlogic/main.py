import httpx
import os
import uuid
import shutil
import sys

from contextlib import contextmanager
from nicegui import ui, app

# SOME DEFAULT VALUES
folder_containing_this_script = os.path.dirname(os.path.realpath(__file__))
root_of_project = os.path.dirname(folder_containing_this_script)

global_output_folder = os.path.join(folder_containing_this_script, "output")
app.add_static_files('/rawfiles', local_directory=global_output_folder)

default_map_name = "threelanes"
default_map_file = os.path.join(folder_containing_this_script, "maps", f"{default_map_name}.xml")

# Basic setup
if not os.path.exists(global_output_folder):
    print(f"Create the output folder {global_output_folder}")
    os.makedirs(global_output_folder)

# Import the root of this project on the path to import all the modules. TODO Refactor into roadlogic package
sys.path.insert(0, root_of_project)
sys.path.append(os.path.join(root_of_project, "monitoring", "syma-arv"))
sys.path.append(os.path.join(root_of_project, "monitoring", "syma"))

default_osc_spec = """
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

from pages import create

# This will create all the pages
create(global_output_folder, default_map_file)


ui.run()