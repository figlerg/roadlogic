import click
# from monitoring.overtake_monitor import manual_monitor as mon  # fixed automaton without self-loops
from monitoring.overtake_monitor import gen_monitor as mon       # generated monitoring with full setup
from monitoring.Monitor import Monitor

@click.command()
@click.argument("gen_path", type=click.Path(exists=True, file_okay=False))
def gen_monitoring_results(gen_path):
    """
    Runs the monitor on a simulation result folder (GEN_PATH).
    Prints the resulting state from the monitor.
    """

    mon_result = mon.eval_trace(gen_path)


    # TODO TODO the correct plans unpickled here. Probably I should move the files to the gen_path via makefile
    # inv_mon = Monitor.invariant_from_plan(planning=planning)
    # mon_result_2 = mon.eval_trace(gen_path, log_name_override='invariant_monitoring_results')
    # print(mon_result)


if __name__ == "__main__":
    gen_monitoring_results()
