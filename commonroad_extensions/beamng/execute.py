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


def build_scenario(bng, layout, agents, name="roadlogic"):
    """A new scenario. Each scenario loaded into a running BeamNG needs its own name: with a name it has
    already loaded, BeamNG keeps the old objects and rejects the new ones."""
    from beamngpy import Scenario, Vehicle
    from commonroad_extensions.beamng.road import add_to_scenario
    scenario = Scenario(layout["level"], name)
    add_to_scenario(scenario, layout)
    vehicles = {}
    for k, (name, a) in enumerate(agents.items()):          # colours as in the plots: C0, C1, ...
        vehicles[name] = Vehicle(f"rl_{name}", model=MODEL, color=COLOURS[k % len(COLOURS)])   # the level may have an object called "obstacle"
        s = a["spawn"]
        scenario.add_vehicle(vehicles[name], pos=(s["x"], s["y"], layout["z"] + SPAWN_Z), rot_quat=heading_quat(s["heading"]))
    scenario.make(bng)
    bng.settings.set_deterministic(PHYSICS_HZ)
    bng.scenario.load(scenario)
    bng.scenario.start()
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


def observe(vehicle, offset, ground_z):
    """(centre x, centre y, heading, speed) of a car: the bounding box centre, as CommonRoad's position.
    Fails if the car is below the ground (no ground where the level is assumed to have it)."""
    vehicle.sensors.poll()
    st = vehicle.state
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
    vehicles = build_scenario(bng, layout, agents, name)
    bng.control.step(PHYSICS_HZ // 2)         # let the cars settle on their wheels
    offsets = {name: centre_offset(veh) for name, veh in vehicles.items()}
    for name, a in agents.items():
        if a["static"]:
            vehicles[name].set_shift_mode("arcade")
            vehicles[name].control(parkingbrake=1)
        else:
            vehicles[name].ai.set_script([{"x": p["x"], "y": p["y"], "z": layout["z"], "t": p["t"]} for p in a["script"]])
    end = max([p["t"] for a in agents.values() for p in a["script"]] + [plan["plan_end"]])
    steps = int(round(end / dt))
    trace = {name: [] for name in agents}
    for k in range(steps + 1):
        for name, veh in vehicles.items():
            trace[name].append((k,) + observe(veh, offsets[name], layout["z"]))
        if recorder:
            recorder.frame(k, [rows[-1][1:3] for rows in trace.values()], layout["z"])
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
    shape = Rectangle(4.508, 1.61)            # as the CommonRoad backend writes its cars
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
        from commonroad_extensions.beamng.road import road_layout
        self.road, _ = CommonRoadFileReader(os.path.join(ROOT, "cr_scenarios", "threelanes.xml")).open()
        self.layout = road_layout(self.road)
        self.log_dir, self.server, self.bng, self.count, self.starts = log_dir, None, None, 0, 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()

    def start(self):
        from beamngpy import BeamNGpy
        from commonroad_extensions.beamng.server import BeamNGServer
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
        from commonroad_extensions.beamng.video import Recorder
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
        with open(os.path.join(sim, "beamng_trace.json"), "w") as f:
            json.dump({"agents": plan["agents"], "trace": trace}, f)
        write_executed(cr_scenario, plan["agents"], trace, os.path.join(sim, "executed_scenario.xml"))
        return os.path.join(sim, "executed_scenario.xml")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True, help="a stored plan (serialized_models/NNNN.pkl)")
    ap.add_argument("--scenario", required=True, help="its CommonRoad scenario (cr_scenarios/scenario_NNNN.xml)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--video", help="also record an mp4 here")
    args = ap.parse_args()
    warnings.simplefilter("ignore")
    sys.path.insert(0, ROOT)
    with Session(args.out) as session:
        print("wrote", session.simulate(args.plan, args.scenario, args.out, args.video))


if __name__ == "__main__":
    main()
