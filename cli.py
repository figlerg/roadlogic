from typing import Optional, List, Tuple

import sys 

def debugger_is_active() -> bool:
    """Return if the debugger is currently active"""
    return hasattr(sys, 'gettrace') and sys.gettrace() is not None

# Note: non-Agg (aka GUI) backends break the code on Ubuntu
# This is needed because the QT platform has issues while running in debug inside visual code
import matplotlib
matplotlib.use('Agg')
# matplotlib.use('TkAgg')
import matplotlib.pyplot as plt

import click
import os
import tempfile


from commonroad_extensions.scenario_execution.commands import execute_scenario
from commonroad_extensions.scenario_generation.commands import generate_scenario, generate_baseline_scenarios, generate_from_simulation
from commonroad_extensions.simulation_analysis.commands import compute_metrics
from commonroad_extensions.simulation_visualization.commands import plot_simulation, animate_simulation

FRENETIX_ROOT = os.path.join(os.path.dirname(os.path.realpath(__file__)), "Frenetix-Motion-Planner")

def _configure_random(random_seed: int):
    """ 
    Configure default random module with predefined seed. 
    """
    # TODO Maybe we should create an instance of Random instead?
    # See https://stackoverflow.com/questions/11526975/set-random-seed-programwide-in-python
    import random
    random.seed(random_seed)

@click.group()
@click.pass_context
@click.option('--output-folder', required=False, type=click.Path(dir_okay=True), help='Folder where test results will be produced')
@click.option('--verbose/--no-verbose', default=False, help='Activate verbose debugging on console')
@click.option('--frenetix-root', required=False, type=click.Path(exists=True, dir_okay=True),  default=FRENETIX_ROOT, help='Folder containing the Frenetix Motion Planner')
@click.option('--random-seed', required=False, type=int, help='Seed for random generator')
@click.option('--co', 'configuration_overrides', required=False, default=[], multiple=True, type=click.Tuple([str,str]), help='configuration overrides')
def cli(ctx, output_folder: str, verbose: bool, frenetix_root: str, random_seed: Optional[int], configuration_overrides: List[Tuple[str, str]]):
    the_output_folder = output_folder if output_folder is not None else tempfile.mkdtemp()
    # Ensure the output folder exists
    os.makedirs(the_output_folder, exist_ok=True)
    #
    ctx.obj = dict()
    ctx.obj["output_folder"] = the_output_folder
    ctx.obj["verbose"] = verbose
    ctx.obj["frenetix_root"] = frenetix_root

    if random_seed is None:
        from datetime import datetime
        dt = datetime.today()
        random_seed = dt.timestamp()
        
    _configure_random(random_seed)

    ctx.obj["random_seed"] = random_seed
    ctx.obj["configuration_overrides"] = configuration_overrides
    
    if verbose:
        click.echo(f"Verbose mode on")
        click.echo(f"Output results to {the_output_folder}")
        click.echo(f"Frenetix Motion Planner available at {frenetix_root}")
        click.echo(f"Random seed set to {random_seed}")

# Import and setup the various commands
cli.add_command(generate_scenario)

cli.add_command(generate_baseline_scenarios)

cli.add_command(generate_from_simulation)

cli.add_command(execute_scenario)

cli.add_command(compute_metrics)

cli.add_command(plot_simulation)

cli.add_command(animate_simulation)

if __name__ == "__main__":
    cli()
