from beamng_integration.data_structures import BeamNGConfigs
from beamng_integration.utils import ensure_materials, connect_or_start_beamng

from commonroad.scenario.scenario import Scenario
from commonroad.planning.planning_problem import PlanningProblem, PlanningProblemSet

from typing import Optional, Tuple, List
from copy import deepcopy


def write_executed_scenario(scenario: Scenario, agents, trace):
    """The CommonRoad road with each car's recorded trajectory as a dynamic obstacle (id as in the plan)."""
    from commonroad.common.file_reader import CommonRoadFileReader
    from commonroad.geometry.shape import Rectangle
    from commonroad.prediction.prediction import Trajectory, TrajectoryPrediction
    from commonroad.scenario.obstacle import DynamicObstacle, ObstacleType
    from commonroad.scenario.state import CustomState, InitialState
    from commonroad_extensions.common.utils import store_executed_scenario_to_output_folder
    from commonroad_extensions.beamng_execution.execute import on_road_steps
    import numpy as np
    # Clone the input scenarios
    executed_scenario = deepcopy(scenario)

    # Add the observed behaviors
    # TODO: Use the actual size of the vehicles from BeamNG!
    shape = Rectangle(4.508, 1.61)            # as the CommonRoad backend writes its cars
    end = on_road_steps(executed_scenario, trace)
    for name, rows in trace.items():
        rows = rows[:end]
        states = [dict(position=np.array([x, y]), orientation=h, velocity=v, acceleration=0.0, yaw_rate=0.0,
                       slip_angle=0.0, time_step=k) for k, x, y, h, v in rows]
        initial = InitialState(**states[0])
        traj = Trajectory(1, [CustomState(**s) for s in states[1:]])
        # TODO Map planning problems to agents id?
        executed_scenario.add_objects(DynamicObstacle(agents[name]["id"], ObstacleType.CAR, shape, initial,
                                             TrajectoryPrediction(traj, shape)))
    
    return executed_scenario

def run_the_simulation(bng, layout, agents, max_duration_s: float, dt=0.1):
    """
    TODO Update the description...
    Drive the plan and return {agent: [(time step, x, y, heading, speed), ...]}. A video.Recorder
    takes a frame per step."""
    from commonroad_extensions.beamng_execution.execute import build_scenario, observe, PHYSICS_HZ
    # Make the scenario in BeamNG and return the vehicles in it
    vehicles = build_scenario(bng, layout, agents)
    
    # Initialization of the AIs.
    bng.control.step(PHYSICS_HZ // 2)         # let the cars settle on their wheels
    for name, agent in agents.items():
        # Car that does not move are parked
        if agent["static"]:
            # TODO Is this necessary?
            vehicles[name].set_shift_mode("arcade")
            # TODO Is this necessary?            
            vehicles[name].control(parkingbrake=1)
        else:
            # The vehicles move by following the script, and the script is defined by the plan.
            #   By doing so we ensure that the vehicle is at the expected position at the target time (if possible)
            #   TODO: Check whether teleportation or something else it at play
            #   TODO: Add a debug flag to show the spheres where the vehicle should go, and change color when they are not "active" anymore
            vehicles[name].ai.set_script([{"x": p["x"], "y": p["y"], "z": layout["z"], "t": p["t"]} for p in agent["script"]])

    # Prepare to sample at constant rate (dt)
    # TODO... Not sure about this! why not simply max_duration?
    end = max([p["t"] for a in agents.values() for p in a["script"]] + [max_duration_s])

    # dt is the sampling rate. TODO We need to use the timer sensor to ensure samples are indeed collected at reasonable times
    steps = int(round(end / dt))
    trace = {name: [] for name in agents}
    for k in range(steps + 1):
        for name, veh in vehicles.items():
            
            # TODO observe misses the damage sensor/collision
            # TODO NEEDS SOME OFFSET VALUE No idea from where this come from!
            offset = [0.0, 0.0]
            ground_z = layout["z"]
            trace[name].append((k,) + observe(veh, offset, ground_z))

        # TODO: Upon collisions agents should stop
        
        # Step forward the simulation
        bng.control.step(int(round(PHYSICS_HZ * dt)))
    
    return trace

class BeamNGScenarioExecution():
    """
    A class to execute BeamNG scenario modelled after the FrenetixScenarioExecution in attempt to enable better refactoring
    """

    def __init__(self, output_folder:str, beamng_configs: BeamNGConfigs) -> None:   
        # Mandatory values    
        self.output_folder = output_folder
        self.beamng_configs = beamng_configs
        
    # TODO Candidate to be moved in abstract class
    # def visualize_the_scenario(self, scenario, planning_problem_set, output_folder):
    
    def execute(self, scenario: Scenario, plan_dict: dict, 
                simulation_id: int,
                max_duration_s: Optional[float] = None) -> None: # Apparently the original return value is never used in our scritps...

        import os
        from beamngpy import BeamNGpy
        from commonroad.common.file_reader import CommonRoadFileReader
        from commonroad_extensions.common.utils import store_executed_scenario_to_output_folder
        # OUR CODE:
        from commonroad_extensions.beamng_execution.road import road_layout
        from commonroad_extensions.beamng_execution.server import BeamNGServer
        from commonroad_extensions.beamng_execution.video import Recorder
        from commonroad_extensions.plan_execution.map_plan import map_plan_beamng
       
        # Hardcoded name as in CommonRoad. This is here for retro-compatibility but shall be removed later
        simulation_folder = os.path.join(self.output_folder, f"simulation_{str(simulation_id).rjust(5, '0')}")
        os.makedirs(simulation_folder, exist_ok=True)

        ##################################################################################################
        # Execute the simulation
        ##################################################################################################

        # Extract the Road Metadata from CommonRoad.
        # TODO This requires some love! SET THE LEVEL name to the one provided!!
        layout = road_layout(scenario)
        # Ensure that all the materials are in place
        ensure_materials(self.beamng_configs.beamng_user_path, self.beamng_configs.beamng_level_name)
        # 
        bng = connect_or_start_beamng(self.beamng_configs)

        # This follows the Claude implementation that configure the agents to run from the ASP plan

        # Run the simulation and return the trace
        # TODO Still I am not sure about the plan
        agents = plan_dict["agents"]
        # TODO This must be checked, what if this is more than max_duration?!
        max_duration_s = plan_dict["plan_end"]
        
        trace = run_the_simulation(bng, layout, agents, max_duration_s)

        # Store the trace into the executed_scenario CommonRoad Object
        executed_scenario = write_executed_scenario(scenario, agents, trace)
        store_executed_scenario_to_output_folder(executed_scenario, simulation_folder)
        


   