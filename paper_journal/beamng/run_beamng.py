"""Simulate planned scenarios of benchmark experiments in BeamNG.tech and judge them with the monitor.

    python paper_journal/beamng/run_beamng.py <experiment out folder> [more folders] [options]
    python paper_journal/beamng/run_beamng.py paper_journal/benchmark/out/exp_004 --scenarios 0002 --video
    python paper_journal/beamng/run_beamng.py paper_journal/benchmark/out/* --per-exp 1 --results stress.jsonl

Reads the plans and CommonRoad scenarios that run_benchmark.py stored in each experiment folder
(serialized_models/, cr_scenarios/, in/spec.osc). Writes <experiment>/sim_beamng/: per scenario the trace
(executed_scenario.xml, beamng_trace.json, LANE, LONGPOS, CURRV), the verdict, with --video an mp4, plus
summary_log.json, the same layout as sim_default/ (the CommonRoad simulation). A scenario that fails in
BeamNG is logged in sim_beamng/failed.jsonl and the run goes on.

Each scenario runs in a fresh BeamNG process (execute.Session), so every run is reproducible. --results appends one JSON line per experiment:
the BeamNG verdicts next to the CommonRoad ones (sim_default) for the same scenarios.

Needs BeamNG.tech 0.38.5 on Windows (found under C:\\Users\\<you>\\BeamNG, or ROADLOGIC_BEAMNG_HOME) and
beamngpy 1.35.1 (pip install --no-deps beamngpy==1.35.1 msgpack). Run from the repository root with the venv
active.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


def env():
    e = dict(os.environ)
    e["PYTHONPATH"] = os.pathsep.join([ROOT, os.path.join(ROOT, "monitoring", "syma-arv"),
                                       os.path.join(ROOT, "monitoring", "syma"), e.get("PYTHONPATH", "")])
    return e


def stored(exp):
    return sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(exp, "serialized_models", "*.pkl")))


def executed(out, n):
    return os.path.join(out, f"scenario_{n}", "simulation_00001", "executed_scenario.xml")


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
    quiet = dict(cwd=ROOT, env=env(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["make", "-s", "-k", "compute-selected-metrics-for-all-scenarios",
                    "selected_metrics=LANE LONGPOS CURRV"] + common, **quiet)
    summary = os.path.join(out, "summary_log.json")
    if os.path.exists(summary):
        os.remove(summary)
    subprocess.run(["make", "-s", "-k", "generate-summary", f"OSC_FILE={os.path.join(exp, 'in', 'spec.osc')}"] + common,
                   **quiet)
    return json.load(open(summary)) if os.path.exists(summary) else None


def verdicts(summary, scenarios):
    """POSITIVE / negative / none per scenario number, from a summary_log.json."""
    if summary is None:
        return {n: None for n in scenarios}
    pos, neg = set(summary["positive traces"]), set(summary["negative traces"])
    return {n: "POSITIVE" if f"scenario_{n}" in pos else "negative" if f"scenario_{n}" in neg else None for n in scenarios}


def from_traces(out, scenarios, backend, key):
    """Per scenario an entry of the simulator's trace file: "off_road" (cars that left the asphalt, when)
    or "collisions" (pairs of cars that touched, when)."""
    rows = {}
    for n in scenarios:
        f = os.path.join(out, f"scenario_{n}", "simulation_00001", f"{backend}_trace.json")
        found = json.load(open(f)).get(key, {}) if os.path.exists(f) else {}
        rows[n] = {k: t for k, t in found.items() if t is not None}
    return rows


def run_experiment(session, exp, scenarios, video, skip_done, backend="beamng"):
    out = os.path.join(exp, f"sim_{backend}")
    os.makedirs(out, exist_ok=True)
    done, seconds = [], {}
    for n in scenarios:
        if skip_done and os.path.exists(executed(out, n)):
            done.append(n)
            continue
        shutil.rmtree(os.path.join(out, f"scenario_{n}"), ignore_errors=True)    # no stale results, no overwrite prompt
        t = time.time()
        try:
            mp4 = os.path.join(out, f"scenario_{n}", f"scenario_{n}.mp4") if video else None
            session.simulate(os.path.join(exp, "serialized_models", f"{n}.pkl"),
                             os.path.join(exp, "cr_scenarios", f"scenario_{n}.xml"), os.path.join(out, f"scenario_{n}"), mp4)
            done.append(n)
        except Exception as e:
            with open(os.path.join(out, "failed.jsonl"), "a") as f:
                f.write(json.dumps({"scenario": n, "error": repr(e)[-500:], "trace": traceback.format_exc()[-2000:]}) + "\n")
            print(f"  scenario {n} FAILED: {repr(e)[:200]}", flush=True)
        seconds[n] = round(time.time() - t, 1)
    summary = judge(exp, out, done) if done else None
    default = os.path.join(exp, "sim_default", "summary_log.json")
    return {"experiment": os.path.basename(exp), "scenarios": scenarios, "simulated": done,
            "failed": [n for n in scenarios if n not in done], "seconds": seconds, "off_road": from_traces(out, done, backend, "off_road"),
            "collisions": from_traces(out, done, backend, "collisions"),
            "backend": backend, "beamng": verdicts(summary, scenarios),
            "commonroad": verdicts(json.load(open(default)) if os.path.exists(default) else None, scenarios)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("experiments", nargs="+")
    ap.add_argument("--scenarios", nargs="*", help="scenario numbers, e.g. 0002 0005 (default all)")
    ap.add_argument("--per-exp", type=int, help="only the first N scenarios of each experiment")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--skip-done", action="store_true", help="keep scenarios that already have a BeamNG trace")
    ap.add_argument("--results", help="append one JSON line per experiment here")
    ap.add_argument("--backend", choices=["beamng", "carla"], default="beamng",
                    help="carla: the server at ROADLOGIC_CARLA_HOST, results in sim_carla/")
    a = ap.parse_args()
    warnings.simplefilter("ignore")
    if a.backend == "carla":
        from commonroad_extensions.carla.execute import Session
    else:
        from commonroad_extensions.beamng.execute import Session
    experiments = [e.rstrip("/") for e in a.experiments if stored(e.rstrip("/"))]
    for e in a.experiments:
        if not stored(e.rstrip("/")):
            print(f"skipped {e}: no stored plans (serialized_models/)", flush=True)
    with Session(os.path.join(ROOT, "demo_output", "beamng_logs")) as session:
        for exp in experiments:
            scenarios = a.scenarios or stored(exp)
            scenarios = scenarios[:a.per_exp] if a.per_exp else scenarios
            t = time.time()
            row = run_experiment(session, exp, scenarios, a.video, a.skip_done, a.backend)
            b, c = row["beamng"], row["commonroad"]
            agree = sum(b[n] == c[n] for n in scenarios if b[n] and c[n])
            print(f"{row['experiment']}: {a.backend} {list(b.values()).count('POSITIVE')}/{len(scenarios)} positive, "
                  f"CommonRoad {list(c.values()).count('POSITIVE')}/{len(scenarios)}, same verdict {agree}, "
                  f"failed {len(row['failed'])}, off road {sum(bool(v) for v in row['off_road'].values())}, "
                  f"collisions {sum(bool(v) for v in row['collisions'].values())}, "
                  f"{time.time() - t:.0f} s", flush=True)
            if a.results:
                with open(a.results, "a") as f:
                    f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
