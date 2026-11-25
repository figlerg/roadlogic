"""Simulate planned scenarios of a benchmark experiment in BeamNG.tech and judge them with the monitor.

    python paper_journal/beamng/run_beamng.py <experiment out folder> [scenario numbers] [--video]
    python paper_journal/beamng/run_beamng.py paper_journal/benchmark/out/exp_004 0002 --video

Reads the plans and CommonRoad scenarios that run_benchmark.py stored in the experiment folder
(serialized_models/, cr_scenarios/, in/spec.osc), all scenarios if no numbers are given. Writes
<experiment>/sim_beamng/: per scenario the trace (executed_scenario.xml, beamng_trace.json, LANE, LONGPOS,
CURRV), the verdict, and with --video an mp4, plus summary_log.json for all of them, the same layout as
sim_default/ (the CommonRoad simulation). One BeamNG process per scenario, about a minute each.

Needs BeamNG.tech 0.38.5 on Windows (found under C:\\Users\\<you>\\BeamNG, or ROADLOGIC_BEAMNG_HOME) and
beamngpy 1.35.1 (pip install --no-deps beamngpy==1.35.1 msgpack). Run from the repository root with the venv
active.
"""
import argparse
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def env():
    e = dict(os.environ)
    e["PYTHONPATH"] = os.pathsep.join([ROOT, os.path.join(ROOT, "monitoring", "syma-arv"),
                                       os.path.join(ROOT, "monitoring", "syma"), e.get("PYTHONPATH", "")])
    return e


def simulate(exp, n, out, video):
    cmd = [sys.executable, "-m", "commonroad_extensions.beamng.execute",
           "--plan", os.path.join(exp, "serialized_models", f"{n}.pkl"),
           "--scenario", os.path.join(exp, "cr_scenarios", f"scenario_{n}.xml"),
           "--out", os.path.join(out, f"scenario_{n}")]
    if video:
        cmd += ["--video", os.path.join(out, f"scenario_{n}", f"scenario_{n}.mp4")]
    return subprocess.run(cmd, cwd=ROOT, env=env()).returncode == 0


def judge(exp, out, scenarios):
    """Metrics and monitor with the makefile, as for the CommonRoad simulation. The makefile takes the
    scenario list from a folder of CommonRoad files, so it gets a folder with only the simulated ones."""
    chosen = os.path.join(out, "_scenarios")
    os.makedirs(chosen, exist_ok=True)
    for f in glob.glob(os.path.join(chosen, "*.xml")):
        os.remove(f)
    for n in scenarios:
        os.symlink(os.path.abspath(os.path.join(exp, "cr_scenarios", f"scenario_{n}.xml")),
                   os.path.join(chosen, f"scenario_{n}.xml"))
    common = [f"SCENARIOS_FOLDER={chosen}", f"OUTPUT_FOLDER={out}"]
    subprocess.run(["make", "-s", "compute-selected-metrics-for-all-scenarios", "selected_metrics=LANE LONGPOS CURRV"]
                   + common, cwd=ROOT, env=env())
    if os.path.exists(os.path.join(out, "summary_log.json")):
        os.remove(os.path.join(out, "summary_log.json"))
    subprocess.run(["make", "-s", "-k", "generate-summary", f"OSC_FILE={os.path.join(exp, 'in', 'spec.osc')}"] + common,
                   cwd=ROOT, env=env())
    return json.load(open(os.path.join(out, "summary_log.json")))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiment")
    ap.add_argument("scenarios", nargs="*", help="e.g. 0002 0005, default all")
    ap.add_argument("--video", action="store_true")
    a = ap.parse_args()
    exp = a.experiment.rstrip("/")
    scenarios = a.scenarios or sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(exp, "serialized_models", "*.pkl")))
    out = os.path.join(exp, "sim_beamng")
    done = [n for n in scenarios if simulate(exp, n, out, a.video)]
    if not done:
        sys.exit("no scenario simulated")
    summary = judge(exp, out, done)
    print(f"{summary['num_positive_traces']}/{len(done)} positive:", " ".join(summary["positive traces"]),
          "| negative:", " ".join(summary["negative traces"]) or "-")
    print("output:", out)


if __name__ == "__main__":
    main()
