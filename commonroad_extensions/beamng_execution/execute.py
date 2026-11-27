"""Simulate one plan in BeamNG.tech and write the result as executed_scenario.xml, the file the CommonRoad
backend writes, so metrics, monitor and summary run on it unchanged.

    python -m commonroad_extensions.beamng.execute --plan <plan.pkl> --scenario <scenario_N.xml> --out <folder>

The road is the CommonRoad road (road.py) on a flat part of a BeamNG level (road.LEVELS), in the same x, y coordinates. Each
moving car follows its plan as a timed script with BeamNG's AI (map_plan_beamng), a static one is parked.
The simulation runs in fixed steps (deterministic, PHYSICS_HZ) and records every car every 0.1 s: the
centre of its bounding box, its heading and its speed. Output: <out>/simulation_00001/executed_scenario.xml
(cut where the first car leaves the CommonRoad lanes), beamng_trace.json (the whole recording, with the
scripts) and beamng_NNN.log, the simulator's log. Session runs many scenarios, one BeamNG process each.
"""
import argparse
import json
import math
import os
import pickle
import sys
import warnings

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL = "etk800"
PHYSICS_HZ = 60
SPAWN_Z = 0.3                 # above the level's ground
COLOURS = [(0.12, 0.47, 0.71, 1.0), (1.0, 0.5, 0.05, 1.0), (0.17, 0.63, 0.17, 1.0), (0.84, 0.15, 0.16, 1.0)]


def heading_quat(heading):
    """BeamNG rotation (x, y, z, w) pointing a car's nose at `heading` [rad, counter-clockwise from +x]. Cars
    face -y unrotated and BeamNG turns a yaw quaternion the other way (measured in the COMMAND pipeline)."""
    yaw = -(heading + math.pi / 2)
    return (0.0, 0.0, math.sin(yaw / 2), math.cos(yaw / 2))


# TODO Extend agents with model and color, so we can replicate them in CommonRoad when we generate the visualization?
def build_scenario(bng, layout, agents, name="roadlogic"):
    """A new scenario. Each scenario loaded into a running BeamNG needs its own name: with a name it has
    already loaded, BeamNG keeps the old objects and rejects the new ones."""
    # This build and make the scenario in BeamNG
    # TODO For complex scenarios, we need to ensure the map is rebuilt
    from beamngpy import Scenario, Vehicle
    from beamngpy.sensors import Damage, Timer
    from commonroad_extensions.beamng_execution.road import add_to_scenario
    scenario = Scenario(layout["level"], name)
    
    add_to_scenario(scenario, layout)

    vehicles: dict[str, Vehicle] = {}
    for k, (name, a) in enumerate(agents.items()):
        vehicles[name] = Vehicle(f"rl_{name}", model=MODEL, color=COLOURS[k % len(COLOURS)])
        vehicles[name].sensors.attach("damage", Damage())
        vehicles[name].sensors.attach("timer", Timer())
        s = a["spawn"]
        scenario.add_vehicle(vehicles[name], pos=(s["x"], s["y"], layout["z"] + SPAWN_Z), rot_quat=heading_quat(s["heading"]))
    scenario.make(bng)

    # TODO We need to setup the frame per second to ensure a step is 0.1
    #  CLAUDE REPLY: done. Deterministic mode at PHYSICS_HZ = 60, and run() steps 6 physics steps per 0.1 s
    bng.settings.set_deterministic(PHYSICS_HZ)
    bng.scenario.load(scenario)
    bng.scenario.start()
    # TODO Not necessary
    #  CLAUDE REPLY: only matters for videos (light), costs nothing
    bng.env.set_tod(0.0)                       # noon, for the video
    bng.control.pause()
    return vehicles


def _frame(st):
    """Forward and left unit vectors of a car in the ground plane, from its state."""
    fwd = np.array(st["dir"][:2], float)
    fwd = fwd / np.linalg.norm(fwd)
    return fwd, np.array([-fwd[1], fwd[0]])


def centre_offset(vehicle):
    """Where the centre of a car's bounding box is relative to its reference point, in the car's own frame
    (forward, left). Measured once at rest: get_bbox is a round trip that doubled the time per step."""
    vehicle.sensors.poll()
    st = vehicle.state
    centre = np.mean([np.asarray(v) for v in vehicle.get_bbox().values()], axis=0)[:2]
    fwd, left = _frame(st)
    d = centre - np.asarray(st["pos"][:2])
    return float(d @ fwd), float(d @ left)


def centre_x(vehicle, offset):
    """x of the centre of a car's bounding box, for the video camera (one round trip)."""
    vehicle.sensors.poll()
    fwd, left = _frame(vehicle.state)
    return float(vehicle.state["pos"][0] + offset[0] * fwd[0] + offset[1] * left[0])


def off_road(layout, trace):
    """Per car the first time [s] its centre is off the asphalt (BeamNG road), None if never."""
    asphalt = [r for r in layout["roads"] if r["name"] == "asphalt"][0]
    line = np.array([n[:2] for n in asphalt["nodes"]])
    half = asphalt["nodes"][0][3] / 2
    out = {}
    for name, rows in trace.items():
        first = None
        for k, x, y, *_ in rows:
            p = np.array([x, y])
            seg = [np.linalg.norm(p - (a + np.clip((p - a) @ (b - a) / ((b - a) @ (b - a)), 0, 1) * (b - a)))
                   for a, b in zip(line[:-1], line[1:]) if (b - a) @ (b - a) > 0]
            if min(seg) > half:
                first = round(k / 10, 1)
                break
        out[name] = first
    return out


CAR_LENGTH, CAR_WIDTH = 4.9, 1.9             # the simulated cars (BeamNG etk800, CARLA lincoln mkz) are about
                                              # this big. The CommonRoad shape 4.508 x 1.61 missed a car pushing another


def _corners(x, y, h):
    c, s = math.cos(h), math.sin(h)
    return np.array([[x + c * dx - s * dy, y + s * dx + c * dy]
                     for dx, dy in ((CAR_LENGTH / 2, CAR_WIDTH / 2), (CAR_LENGTH / 2, -CAR_WIDTH / 2),
                                    (-CAR_LENGTH / 2, -CAR_WIDTH / 2), (-CAR_LENGTH / 2, CAR_WIDTH / 2))])


def _overlap(a, b):
    """Two convex polygons intersect (separating axis test)."""
    for poly in (a, b):
        for i in range(len(poly)):
            edge = poly[(i + 1) % len(poly)] - poly[i]
            axis = np.array([-edge[1], edge[0]])
            pa, pb = a @ axis, b @ axis
            if pa.max() < pb.min() or pb.max() < pa.min():
                return False
    return True


def collisions(trace):
    """The first time [s] each pair of cars overlaps (car outlines of CAR_LENGTH x CAR_WIDTH), as
    {"car_a/car_b": t}. Only pairs that touch at some point."""
    names, out = list(trace), {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for ra, rb in zip(trace[a], trace[b]):
                if abs(ra[1] - rb[1]) < CAR_LENGTH + 1 and _overlap(_corners(*ra[1:4]), _corners(*rb[1:4])):
                    out[f"{a}/{b}"] = round(ra[0] / 10, 1)
                    break
    return out


def observe(vehicle, offset, ground_z):
    """(centre x, centre y, heading, speed) of a car: the bounding box centre, as CommonRoad's position.
    Fails if the car is below the ground (no ground where the level is assumed to have it)."""
    vehicle.sensors.poll()
    st = vehicle.state
    # Note this is important, we do not use st['pos']
    #  CLAUDE REPLY: st['pos'] is BeamNG's reference node, not the centre CommonRoad uses. We add the offset to the
    #  bounding box centre, measured once per car in centre_offset() (get_bbox every step doubled the time per step)
    # TODO Not necessary?
    #  REPLY FELIX: I had some issues with cars falling forever because they spawned below ground
    if st["pos"][2] < ground_z - 2.0:
        raise RuntimeError(f"{vehicle.vid} fell through the ground (z = {st['pos'][2]:.1f})")
    fwd, left = _frame(st)
    centre = np.asarray(st["pos"][:2]) + offset[0] * fwd + offset[1] * left
    v = st["vel"]
    return float(centre[0]), float(centre[1]), math.atan2(fwd[1], fwd[0]), float(math.hypot(v[0], v[1]))


def run(bng, layout, plan, dt=0.1, recorder=None, name="roadlogic", max_wall=900):
    """Drive the plan and return {agent: [(time step, x, y, heading, speed), ...]}. A video.Recorder
    takes a frame per step. Fails after max_wall seconds of wall time."""
    import time
    start = time.time()
    agents = plan["agents"]

    # Make the scenario in BeamNG and return the vehicles in it
    # TODO Add Timer and Damage sensors
    #  CLAUDE REPLY: agreed, the damage sensor is the next step (now collisions() checks car outlines in the trace,
    #  which also flags near misses). No timer needed: deterministic mode, we step the simulation ourselves
    vehicles = build_scenario(bng, layout, agents, name)

    # Initialization of the AIs.
    bng.control.step(PHYSICS_HZ // 2)         # let the cars settle on their wheels
    offsets = {name: centre_offset(veh) for name, veh in vehicles.items()}
    for name, a in agents.items():
        # Car that does not move are parked
        if a["static"]:
            # TODO Is this necessary?
            #  CLAUDE REPLY: arcade mode so the parking brake is applied without a gear change. Not tested without
            vehicles[name].set_shift_mode("arcade")
            # TODO Is this necessary?
            #  CLAUDE REPLY: my assumption, not tested: without a brake a parked car could roll when another one touches it
            vehicles[name].control(parkingbrake=1)
        else:
            # The vehicles move by following the script, and the script is defined by the plan.
            #   By doing so we ensure that the vehicle is at the expected position at the target time (if possible)
            #   TODO: Check whether teleportation or something else it at play
            #    CLAUDE REPLY: no teleport, BeamNG's AI drives the car (throttle, brake, steering) in physics
            #   TODO: Add a debug flag to show the spheres where the vehicle should go, and change color when they are not "active" anymore
            vehicles[name].ai.set_script([{"x": p["x"], "y": p["y"], "z": layout["z"], "t": p["t"]} for p in a["script"]])

    # Prepare to sample at constant rate (dt)
    end = max([p["t"] for a in agents.values() for p in a["script"]] + [plan["plan_end"]])
    # dt is the sampling rate. TODO We need to use the timer sensor to ensure samples are indeed collected at reasonable times
    #  CLAUDE REPLY: in deterministic mode simulated time only moves when we step, a sample is exactly every dt
    steps = int(round(end / dt))
    trace = {name: [] for name in agents}
    focus = "ego" if "ego" in agents else next(iter(agents))       # the car the video follows
    followed = vehicles[focus]
    road_y = [r for r in layout["roads"] if r["name"] == "asphalt"][0]["nodes"][0][1]
    for k in range(steps + 1):
        for name, veh in vehicles.items():
            # TODO observe misses the damage sensor/collision
            #  CLAUDE REPLY: see above, collisions come from the trace for now (collisions())
            trace[name].append((k,) + observe(veh, offsets[name], layout["z"]))
        if recorder:                          # extra frames between the recorded steps, for a smooth video
            for sub in range(recorder.substeps):
                x = trace[focus][-1][1] if not sub else centre_x(followed, offsets[focus])   # the same point as the trace
                recorder.frame(x, road_y, layout["z"])
                bng.control.step(int(round(PHYSICS_HZ * dt / recorder.substeps)))
        else:
            # Step forward the simulation
            bng.control.step(int(round(PHYSICS_HZ * dt)))
        if time.time() - start > max_wall:
            raise TimeoutError(f"{name}: over {max_wall} s of wall time at step {k} of {steps}")
    return trace


def on_road_steps(scenario, trace):
    """The number of recorded steps until the first car leaves the CommonRoad lanes. The BeamNG road is
    longer, but the metrics project positions onto the CommonRoad road and fail beyond its end."""
    net = scenario.lanelet_network
    steps = min(len(rows) for rows in trace.values())
    for k in range(steps):
        points = [np.array(rows[k][1:3]) for rows in trace.values()]
        if any(not ids for ids in net.find_lanelet_by_position(points)):
            return k
    return steps


def write_executed(cr_scenario_file, agents, trace, out_file):
    """The CommonRoad road with each car's recorded trajectory as a dynamic obstacle (id as in the plan)."""
    from commonroad.common.file_reader import CommonRoadFileReader
    from commonroad.geometry.shape import Rectangle
    from commonroad.prediction.prediction import Trajectory, TrajectoryPrediction
    from commonroad.scenario.obstacle import DynamicObstacle, ObstacleType
    from commonroad.scenario.state import CustomState, InitialState
    from commonroad_extensions.common.utils import store_executed_scenario_to_output_folder
    scenario, _ = CommonRoadFileReader(cr_scenario_file).open()
    # TODO This information shall be included in the agents structure and sampled directly from BeamNG.tech
    shape = Rectangle(CAR_LENGTH, CAR_WIDTH)
    end = on_road_steps(scenario, trace)
    for name, rows in trace.items():
        rows = rows[:end]
        states = [dict(position=np.array([x, y]), orientation=h, velocity=v, acceleration=0.0, yaw_rate=0.0,
                       slip_angle=0.0, time_step=k) for k, x, y, h, v in rows]
        initial = InitialState(**states[0])
        traj = Trajectory(1, [CustomState(**s) for s in states[1:]])
        scenario.add_objects(DynamicObstacle(agents[name]["id"], ObstacleType.CAR, shape, initial,
                                             TrajectoryPrediction(traj, shape)))
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    store_executed_scenario_to_output_folder(scenario, os.path.dirname(out_file), os.path.basename(out_file))


class Session:
    """Runs many scenarios, restarting BeamNG every RESTART_EVERY scenarios and after a failure. The default
    is a fresh BeamNG per scenario: a scenario run after others in the same process differs by up to 0.9 m
    (exp_004 0002 after two scenarios), while a fresh process reproduces it exactly. ROADLOGIC_BEAMNG_REUSE=N
    keeps a process for N scenarios, about 40 s faster per scenario but not reproducible."""
    RESTART_EVERY = int(os.environ.get("ROADLOGIC_BEAMNG_REUSE", "1"))

    def __init__(self, log_dir):
        from commonroad.common.file_reader import CommonRoadFileReader
        from commonroad_extensions.beamng_execution.road import road_layout
        self.road, _ = CommonRoadFileReader(os.path.join(ROOT, "cr_scenarios", "threelanes.xml")).open()
        self.layout = road_layout(self.road)
        self.log_dir, self.server, self.bng, self.count, self.starts = log_dir, None, None, 0, 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()

    def start(self):
        from beamngpy import BeamNGpy
        from commonroad_extensions.beamng_execution.server import BeamNGServer
        self.starts += 1
        os.makedirs(self.log_dir, exist_ok=True)
        self.server = BeamNGServer(log_path=os.path.join(self.log_dir, f"beamng_{self.starts:03d}.log")).start()
        self.bng = BeamNGpy(self.server.host, self.server.port)
        self.bng.open(launch=False)
        self.since_start = 0

    def stop(self):
        try:
            if self.bng is not None:
                self.bng.disconnect()
        except Exception:
            pass
        if self.server is not None:
            self.server.stop()
        self.server = self.bng = None

    def simulate(self, plan_pkl, cr_scenario, out, video=None):
        """Simulate one stored plan. Writes <out>/simulation_00001/{executed_scenario.xml, beamng_trace.json}."""
        from commonroad_extensions.beamng_execution.video import Recorder
        from commonroad_extensions.plan_execution.map_plan import map_plan_beamng
        if self.bng is None or self.since_start >= self.RESTART_EVERY:
            self.stop()
            self.start()
        with open(plan_pkl, "rb") as f:
            plan = map_plan_beamng(self.road, pickle.load(f), anchor_lane_idx=1)
        self.count += 1
        self.since_start += 1
        try:
            recorder = Recorder(self.bng, os.path.splitext(video)[0] + "_frames") if video else None
            trace = run(self.bng, self.layout, plan, recorder=recorder, name=f"roadlogic_{self.count:04d}")
            if recorder:
                recorder.finish(video)
        except Exception:
            self.stop()                        # a fresh BeamNG for the next scenario
            raise
        sim = os.path.join(out, "simulation_00001")
        os.makedirs(sim, exist_ok=True)
        # TODO We are not using this one. Collisions must be checked using our monitors afterwards
        with open(os.path.join(sim, "beamng_trace.json"), "w") as f:
            json.dump({"agents": plan["agents"], "trace": trace, "off_road": off_road(self.layout, trace),
                       "collisions": collisions(trace)}, f)
        write_executed(cr_scenario, plan["agents"], trace, os.path.join(sim, "executed_scenario.xml"))
        return os.path.join(sim, "executed_scenario.xml")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # TODO Why do we need a plan if we have a scenario?
    # TODO Why do we have a scenario if we have a plan to build the scenario from?
    #  CLAUDE REPLY: the plan gives the timed positions BeamNG's AI follows (map_plan_beamng). The scenario file is only
    #  the template for executed_scenario.xml (road, ids), so metrics and monitor read the same format as for
    #  the CommonRoad simulation. Could be generated from the plan, kept for the shared format
    ap.add_argument("--plan", required=True, help="a stored plan (serialized_models/NNNN.pkl)")
    ap.add_argument("--scenario", required=True, help="its CommonRoad scenario (cr_scenarios/scenario_NNNN.xml)")
    ap.add_argument("--out", required=True)
    # TODO Why do we have a video recording?
    #  CLAUDE REPLY: optional, for looking at single runs (found falling cars, cars leaving the road). Off in batch
    #  runs, the trace is the same with and without
    ap.add_argument("--video", help="also record an mp4 here")
    args = ap.parse_args()
    # TODO What's this?!
    #  CLAUDE REPLY: hides CommonRoad's and map_plan's warnings (padding distance, three lanes) on every run
    warnings.simplefilter("ignore")
    # TODO Why is this necessary?
    #  CLAUDE REPLY: lets the module run as a script from anywhere, not only with the repository installed (pip -e)
    sys.path.insert(0, ROOT)

    from beamngpy import BeamNGpy
    from commonroad.common.file_reader import CommonRoadFileReader
    # OUR CODE:
    from commonroad_extensions.beamng_execution.road import road_layout
    from commonroad_extensions.beamng_execution.server import BeamNGServer
    from commonroad_extensions.beamng_execution.video import Recorder
    from commonroad_extensions.plan_execution.map_plan import map_plan_beamng

    # Read the default ROAD. TODO This shall be changed
    # TODO: Why reading this road when we have an input scenario?
    road, _ = CommonRoadFileReader(os.path.join(ROOT, "cr_scenarios", "threelanes.xml")).open()

    # Read the ASP plan
    with open(args.plan, "rb") as f:
        plan = map_plan_beamng(road, pickle.load(f), anchor_lane_idx=1)

    # This is dictionary of roads, including dashed, lanes, etc.
    layout = road_layout(road)

    # Hardcoded name as in CommonRoad. This is here for retro-compatibility but shall be removed later
    sim = os.path.join(args.out, "simulation_00001")

    os.makedirs(sim, exist_ok=True)

    ##################################################################################################
    # Execute the simulation
    ##################################################################################################

    # TODO This shall be replaced by our BeamNGWrapper
    with BeamNGServer(log_path=os.path.join(args.out, "beamng.log")) as server:
        bng = BeamNGpy(server.host, server.port)
        bng.open(launch=False)
        try:
            # TODO: This is to record the frames during the execution. Can be probably deferred to another process
            recorder = Recorder(bng, os.path.splitext(args.video)[0] + "_frames") if args.video else None

            # Run the simulation and return the trace
            # TODO Still I am not sure about the plan
            trace = run(bng, layout, plan, recorder=recorder)

            if recorder:
                print("video:", recorder.finish(args.video), "frames ->", args.video)
        finally:
            bng.disconnect()

    ##################################################################################################
    # Store the data
    ##################################################################################################

    # TODO Why do we store data in json, if we are also storying the data in the executed_scenario.xml? 
    with open(os.path.join(sim, "beamng_trace.json"), "w") as f:
        json.dump({"agents": plan["agents"], "trace": trace}, f)
    
    # At this point we use the input scenario to copy over the trace data thus obtaining the executed_scenario.xml
    write_executed(args.scenario, plan["agents"], trace, os.path.join(sim, "executed_scenario.xml"))

    print("wrote", os.path.join(sim, "executed_scenario.xml"))
    # TODO NEW CODE, Not sure what it does!
    with Session(args.out) as session:
        print("wrote", session.simulate(args.plan, args.scenario, args.out, args.video))


if __name__ == "__main__":
    main()
