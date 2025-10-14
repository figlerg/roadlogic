import click
import os
import glob
import csv
import enlighten
import inspect
import sys

from enum import Enum

from commonroad.scenario.scenario import Scenario, DynamicObstacle
from commonroad.common.file_reader import XMLFileReader
from commonroad.prediction.prediction import Trajectory, TrajectoryPrediction

from commonroad_crime.data_structure.configuration import CriMeConfiguration
from commonroad_crime.data_structure.crime_interface import CriMeInterface
# This import creates an issue with Qt and open-cv python
# from commonroad_crime.measure import TTCStar
from commonroad_crime.measure import CriMeBase


# Dynamically lookup for all the measures  from the commonroad_crime
from commonroad_extensions.common.utils import patch_TTC, patch_Latj, patch_Longj, patch_ALongReq, patch_ALatReq
from commonroad_crime.measure import *

# Patch the metrics that use only find_lanelet_by_position, thus fail if there are narrow gaps
TTC._compute = TTC.compute
TTC.compute = patch_TTC()

LatJ._compute = LatJ.compute
LatJ.compute = patch_Latj()

LongJ._compute = LongJ.compute
LongJ.compute = patch_Longj()

ALongReq._compute = ALongReq.compute
ALongReq.compute = patch_ALongReq()

ALatReq._compute = ALatReq.compute
ALatReq.compute = patch_ALatReq()


ALL_CRITICALITY_METRICS = [ (measure_name, measure_cls) for measure_name, measure_cls in inspect.getmembers(sys.modules[__name__], inspect.isclass) if issubclass(measure_cls, CriMeBase)]

# Make sure we account for our measures as well
import commonroad_extensions.simulation_analysis.measure as custom_measure
# Some metrics are abstract classes so we need to filter them out
from abc import ABC
ALL_CRITICALITY_METRICS = ALL_CRITICALITY_METRICS + [ (measure_name, measure_cls) for measure_name, measure_cls in inspect.getmembers(custom_measure, inspect.isclass)  if issubclass(measure_cls, CriMeBase)]

# Filter them by name (Not a base class!)
ALL_CRITICALITY_METRICS = [tup for tup in ALL_CRITICALITY_METRICS if not tup[0].endswith("MeBase")]
# Sort them by name
ALL_CRITICALITY_METRICS = sorted(ALL_CRITICALITY_METRICS[:])

# CURRENTLY THOSE METRICS CANNOT BE COMPUTED FOR WHATEVER REASON:
# STN
# LatJ -> Failes, LongJ -> removed after LatJ ?? CRASH Scenario?
# BTN, CPI -> Index error
# ALatReq, ALongReq -> Errors in some scenario with 2 agents
# TTR -> Takes ages to compute - Skip it
# DFLRB DFLLB DFRLB DFRRB -> Are not computed but do not fail
# TTM -> Crash with error






class GroupingStrategy(str, Enum):
    ALL = "all"
    SINGLE = "single"


@click.command()
@click.pass_context
# We need the simulation folder because some data are extracted from simulation.db, other are collected from agent_<ID>/logs.csv, and so on
@click.option("--simulation-folder", required=True, type=click.Path(exists=True, dir_okay=True), help="The folder containing the simulated scenario")
@click.option("--metric", "selected_metrics", required=True, multiple=True, type=click.Choice([n for n, cls in ALL_CRITICALITY_METRICS]), help="The criticality metrics to compute on the simulated scenario")
@click.option("--group-by", "list_of_grouping", required=True, default=[str(GroupingStrategy.ALL.name)], multiple=True, type=click.Choice([str(v.name) for v in list(GroupingStrategy)]), help="Criticality metrics grouping strategy.")
def compute_metrics(ctx, simulation_folder: str, selected_metrics: List[str], list_of_grouping:List[str]):
    # Extract the options from ctx
    output_folder = ctx.obj["output_folder"]
    verbose = ctx.obj["verbose"]

    criticality_metrics = [ cls for n, cls in ALL_CRITICALITY_METRICS if n in selected_metrics]
    
    # Executed scenario should only have obstacles that correspond to the monitored behavior of vehicles during the simulation
    executed_scenario_file = os.path.join(simulation_folder, "executed_scenario.xml")
    executed_scenario, _ = XMLFileReader(executed_scenario_file).open(lanelet_assignment=True)

    all_vehicles = [o.obstacle_id for o in executed_scenario.obstacles]
    manager = enlighten.Manager()
    vehicles_pbar = manager.counter(desc='Vehicles', total=len(all_vehicles))

    criticality_data = list()   
    
    # For each agent, compute the metrics
    for ego_id in vehicles_pbar(all_vehicles):

        ego_vehicle = executed_scenario.obstacle_by_id(ego_id)
        
        # Compute the metrics across the entire life of the vehicle
        ts_start = ego_vehicle.initial_state.time_step
        ts_end = ego_vehicle.prediction.trajectory.final_state.time_step
        
        # Configure the tool
        # TODO. There are plenty of configurations, not sure which one we'd like to tweak...
        config = CriMeConfiguration()
        config.general.simulation_folder = simulation_folder
        
        crime_interface = CriMeInterface(config)
        # Set the current vehicle as the ego vehicle in the given (executed) scenario
        config.update(ego_id=ego_id, sce=executed_scenario)
        # config.print_configuration_summary()
        
        # Evaluate the criticality metrics
        metrics_pbar = manager.counter(desc='Metrics', total=len(criticality_metrics), leave=False)
        for criticality_metric in metrics_pbar(criticality_metrics): 
            time_step_par = manager.counter(desc="Simulation Time", total=(ts_end - ts_start), leave=False)
            for time_step in time_step_par(range(ts_start, ts_end+1)):
                crime_interface.evaluate_scene([criticality_metric], time_step, verbose=verbose)
            time_step_par.close(clear=True)
        metrics_pbar.close(clear=True)
        
        # Accumulate the data such that for each row (time) and agent there's
        # Create the list of dictionaries needed to produce the CSV file. Each dictionary is a row
        def ensure_none_becomes_nan(data_dict):
            for k, v in data_dict.items():
                if v is None:
                    data_dict[k] = float('nan')
                    
        for time_step in sorted(crime_interface.criticality_dict.keys(), key=lambda x : int(x)):
             data = crime_interface.criticality_dict[time_step]
             ensure_none_becomes_nan(data)

             # Add context
             data["time_step"] = time_step
             data["agent_id"] = ego_id
             data["time"] = round(time_step * executed_scenario.dt, ndigits=3)
             criticality_data.append(data)

    # Groups the criticality data for this agent and output the csv file(s)
    if GroupingStrategy.ALL.name in list_of_grouping:
        # Put everything insto a big CSV file with predefined name 
        csv_file = os.path.join(output_folder, f"criticality_metrics.csv")
        # define the header of the csv: time, time_step, criticality metrics sorted
        sorted_fieldnames = ["time_step"] + ["agent_id"] + ["time"] + sorted(cm for cm in criticality_data[0].keys() if cm not in ["time", "time_step", "agent_id"])
        
        with open(csv_file, mode='w', newline='') as file: 
            # Create a DictWriter object 
            writer = csv.DictWriter(file, fieldnames=sorted_fieldnames) 
            # Write the header 
            writer.writeheader() 
            # Write the rows 
            writer.writerows(criticality_data)

    if GroupingStrategy.SINGLE.name in list_of_grouping:
        # Each metric is store in its own file
        for measure_id, measure_name in [(m.measure_name.name, m.measure_name.value) for m in crime_interface.measures]:
            # CSV file named after measure and agent
            csv_file = os.path.join(output_folder, f"{measure_id}.csv")
            # Filter data by measure name
            filtered_data = list()
            wanted_keys = set(['time_step', 'time', 'agent_id', str(measure_name)])
            for data_record in criticality_data:
                filtered_dict = {k: data_record[k] for k in data_record.keys() & wanted_keys}
                filtered_data.append(filtered_dict)
            # define the header of the csv: time, time_step, criticality metrics sorted
            sorted_fieldnames = ["time_step"] + ["agent_id"] + ["time"] + sorted(cm for cm in filtered_data[0].keys() if cm not in ["time", "time_step", "agent_id"])
        
            with open(csv_file, mode='w', newline='') as file: 
                # Create a DictWriter object 
                writer = csv.DictWriter(file, fieldnames=sorted_fieldnames) 
                # Write the header 
                writer.writeheader() 
                # Write the rows 
                writer.writerows(filtered_data) 
    
            
    
    

        
   
        