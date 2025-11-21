import click
import pickle
# from monitoring.overtake_monitor import manual_monitor as mon  # fixed automaton without self-loops
from monitoring.overtake_monitor import gen_monitor as default_mon       # generated monitoring with full setup
from monitoring.Monitor import Monitor
from planning.parse.TranslationGraphVisitor import TranslationGraphVisitor
from planning.parse.TranslationGraphVisitor import TranslationGraphVisitor
from planning.parse.generated.openscenario2Lexer import openscenario2Lexer
from planning.parse.generated.openscenario2Parser import openscenario2Parser
from antlr4 import FileStream, CommonTokenStream
from planning.intermediate_structure.TranslationGraph import TranslationGraph
from planning.intermediate_structure.Constraint import Constraint as MyConstraint # Dejan and I used the same name for our classes so I renamed mine in here
from planning.intermediate_structure.TranslationGraph import TranslationGraph
from planning.misc.errors import HardSyntaxErrorStrategy

from syma.automaton.automaton import Location, SymbolicAutomaton
from syma.constraint.constraint import Constraint
from syma.constraint.node.node import *
from syma_arv.monitor.boolean import BooleanMonitor
from syma_arv.monitor.minmax import MinMaxMonitor
from syma_arv.monitor.tropical import TropicalMonitor



@click.command()
@click.option("--output-folder", type=click.Path(file_okay=False, dir_okay=True, writable=True, resolve_path=True), required=True, help="Output directory for monitoring results.")
@click.option("--osc-file", type=click.Path(exists=True, file_okay=True, dir_okay=False, resolve_path=True), required=True, help="Input OpenSCENARIO file.")
@click.option("--check-plan", type=click.Path(exists=True, file_okay=True, dir_okay=False, resolve_path=True), required=False, help="Input OpenSCENARIO file.")
def gen_monitoring_results(output_folder, osc_file=None, check_plan=None):
    """
    Runs the monitor on a simulation result folder (GEN_PATH).
    Prints the resulting state from the monitor.
    """

    if not osc_file:
        mon = default_mon # the overtake
    else:
        mon = Monitor.from_osc2_file(osc_file,ring=MinMaxMonitor)

    mon_result = mon.eval_trace(output_folder)


    

    # TODO TODO the correct plans unpickled here. Probably I should move the files to the gen_path via makefile
    
    if check_plan:
        with open(check_plan, "rb") as f:
            check_plan = pickle.load(f)
        inv_mon = Monitor.invariant_from_plan(plan=check_plan)   

        inv_mon.eval_trace(output_folder, log_name_override='invariant_monitoring_results')

        # mon_result_2 = mon.eval_trace(gen_path, log_name_override='invariant_monitoring_results')
    # print(mon_result)


if __name__ == "__main__":
    gen_monitoring_results()
