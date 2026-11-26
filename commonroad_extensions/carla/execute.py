"""Simulate one plan in CARLA and write executed_scenario.xml, as the CommonRoad and BeamNG backends do, so
metrics, monitor and summary run on it unchanged.

    python -m commonroad_extensions.carla.execute --plan <plan.pkl> --scenario <scenario_N.xml> --out <folder>

The CARLA server runs elsewhere (ROADLOGIC_CARLA_HOST, port ROADLOGIC_CARLA_PORT, default 2000). The CARLA
client exists only for Windows Python, so the driving happens in carla_drive.py under ROADLOGIC_CARLA_PYTHON
(default C:\\Users\\<you>\\dev\\carla-venv), and this side exchanges JSON files with it in WORK, a folder on the
Windows drive. The plan is mapped as for BeamNG (map_plan_beamng: a timed script per car), the road is the
CommonRoad road as OpenDRIVE (opendrive.py).
"""
import argparse
import glob
import json
import os
import pickle
import shutil
import subprocess
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"


def windows_user_dir():
    found = sorted(glob.glob("/mnt/c/Users/*/dev/carla-venv"))
    if not found:
        raise FileNotFoundError("no carla-venv under C:\\Users\\<you>\\dev, set ROADLOGIC_CARLA_PYTHON")
    return os.path.dirname(found[0])


def win(path):
    return subprocess.run(["wslpath", "-w", path], capture_output=True, text=True, check=True).stdout.strip()


def drive(job, work):
    """Run carla_drive.py on the Windows side and return its trace."""
    os.makedirs(work, exist_ok=True)
    shutil.copy(os.path.join(HERE, "carla_drive.py"), work)
    job_file, trace_file = os.path.join(work, "job.json"), os.path.join(work, "trace.json")
    json.dump(job, open(job_file, "w"))
    if os.path.exists(trace_file):
        os.remove(trace_file)
    python = os.environ.get("ROADLOGIC_CARLA_PYTHON", win(os.path.join(windows_user_dir(), "carla-venv", "Scripts", "python.exe")))
    done = subprocess.run([POWERSHELL, "-NoProfile", "-Command",
                           f"& '{python}' '{win(os.path.join(work, 'carla_drive.py'))}' '{win(job_file)}' '{win(trace_file)}'"],
                          cwd="/mnt/c", capture_output=True, text=True)
    if done.returncode != 0 or not os.path.exists(trace_file):
        raise RuntimeError(f"carla_drive.py failed: {done.stdout[-1500:]} {done.stderr[-1500:]}")
    return json.load(open(trace_file))["trace"]


def simulate(plan_pkl, cr_scenario, out, host=None, port=None, video=None):
    """One stored plan in CARLA. Writes <out>/simulation_00001/{executed_scenario.xml, carla_trace.json}, and an
    mp4 from a chase camera to `video` if given (frames saved on the Windows side, joined here with ffmpeg)."""
    from commonroad.common.file_reader import CommonRoadFileReader
    from commonroad_extensions.beamng.execute import write_executed
    from commonroad_extensions.carla.opendrive import road_xodr
    from commonroad_extensions.plan_execution.map_plan import map_plan_beamng
    road, _ = CommonRoadFileReader(os.path.join(ROOT, "cr_scenarios", "threelanes.xml")).open()
    with open(plan_pkl, "rb") as f:
        plan = map_plan_beamng(road, pickle.load(f), anchor_lane_idx=1)
    job = {"host": host or os.environ.get("ROADLOGIC_CARLA_HOST", "127.0.0.1"),
           "port": int(port or os.environ.get("ROADLOGIC_CARLA_PORT", "2000")),
           "xodr": road_xodr(road), "agents": plan["agents"],
           "road_y": float(sum(l.center_vertices[0][1] for l in road.lanelet_network.lanelets) / len(road.lanelet_network.lanelets)), "plan_end": plan["plan_end"], "dt": plan["dt"]}
    work = os.path.join(windows_user_dir(), "roadlogic_carla")
    frames = os.path.join(work, "frames")
    if video:
        os.makedirs(frames, exist_ok=True)
        for f in glob.glob(os.path.join(frames, "frame_*.png")):
            os.remove(f)
        job["video_dir"] = win(frames)
    trace = drive(job, work)
    if video:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "20", "-pattern_type", "glob",
                        "-i", os.path.join(frames, "frame_*.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", video],
                       check=True)
    sim = os.path.join(out, "simulation_00001")
    os.makedirs(sim, exist_ok=True)
    from commonroad_extensions.beamng.execute import collisions, off_road
    from commonroad_extensions.beamng.road import road_layout
    json.dump({"agents": plan["agents"], "trace": trace, "off_road": off_road(road_layout(road), trace),
               "collisions": collisions(trace)},
              open(os.path.join(sim, "carla_trace.json"), "w"))
    write_executed(cr_scenario, plan["agents"], trace, os.path.join(sim, "executed_scenario.xml"))
    return os.path.join(sim, "executed_scenario.xml")


class Session:
    """The batch interface of the BeamNG backend (execute.Session) for CARLA. The server runs elsewhere and
    stays up, each scenario builds a fresh world."""

    def __init__(self, log_dir=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def simulate(self, plan_pkl, cr_scenario, out, video=None):
        if video:
            os.makedirs(os.path.dirname(video), exist_ok=True)
        return simulate(plan_pkl, cr_scenario, out, video=video)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    warnings.simplefilter("ignore")
    sys.path.insert(0, ROOT)
    print("wrote", simulate(args.plan, args.scenario, args.out))


if __name__ == "__main__":
    main()
