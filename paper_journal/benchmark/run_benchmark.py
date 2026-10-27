"""Rerun the HSCC paper's benchmark on the current code, plus new examples for the journal version.

Three groups:

  paper          the 14 experiments of experiments_src, with the paper's N, its 100s planning
                 limit for the variability runs, and the paper's own sampled instances, so the
                 comparison is instance for instance. experiments_src itself is only read.
  new            specifications exercising what is new: keeps, speed, durations on segments.
  inconsistent   specifications that contradict themselves. Success is finding no plan.

Every simulated experiment is planned once and simulated under two settings:

  now        the current defaults
  speedfix   the Frenetix speed patch on, with speed windows spanning the planned speeds, only for
             cars whose speed the specification constrains

Output goes to paper_journal/benchmark/out/, which git ignores. report.py turns it into tables.

    source venv/bin/activate
    python paper_journal/benchmark/run_benchmark.py                 # everything, hours
    python paper_journal/benchmark/run_benchmark.py --only exp_007 keep_scenario_scope
    python paper_journal/benchmark/run_benchmark.py --workers 3 --sim-jobs 3
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out")
SPECS = os.path.join(HERE, "specs")
CR_SCENARIO = os.path.join(ROOT, "cr_scenarios", "threelanes.xml")
PYTHON = sys.executable

PAPER_VANILLA = [f"exp_00{i}" for i in range(1, 8)]
PAPER_VARIABILITY = [f"exp_00{i}_b" for i in range(1, 8)]

# name: what it shows
NEW = {
    "keep_scenario_scope": "the overtake, while car1 keeps its lane for the whole scenario",
    "keep_phase_scope": "car1 changes lane, then keeps lane 2 for its second segment only",
    "keep_lane_change_from_rest": "lane 1 for one segment, lane 2 for the next, windows that tile the plan",
    "keep_lane_modifier": "the keep_lane() shorthand on car1 during the overtake",
    "keep_relational_distance": "a keep on the gap between two cars, through space_gap",
    "speed_reach_target": "reach 8 m/s by the end of the segment",
    "speed_relative": "ego faster than car1 at the end of a segment",
    "speed_rampup_then_hold_timed": "reach 6 m/s within 2 to 4 s, then hold it for 3 to 6 s",
    "duration_invocation": "durations on two invocations, one starting mid-scenario",
}
INCONSISTENT = {
    "keep_inconsistent_direct": "two lane keeps on one car",
    "keep_inconsistent_parallel": "conflicting keeps on parallel branches",
    "keep_inconsistent_nonlocal": "impossible only through the interplay over time",
    "duration_conflict_unsat": "two segments of at least 3 s inside 5 s",
}
NEW_N = 10
CONFIGS = {
    "now": {"ROADLOGIC_VELOCITY_PATCH": "0"},
    "speedfix": {"ROADLOGIC_VELOCITY_PATCH": "1", "ROADLOGIC_GOAL_VELOCITY_SOURCE": "range",
                 "ROADLOGIC_GOAL_VELOCITY_SCOPE": "constrained"},
}


def environment(extra=None):
    env = dict(os.environ)
    extra_path = os.pathsep.join([ROOT, os.path.join(ROOT, "monitoring", "syma-arv"),
                                  os.path.join(ROOT, "monitoring", "syma")])
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") + os.pathsep + extra_path
    env.update(extra or {})
    return env


def run(cmd, log, extra_env=None):
    """Run one step, append its output to log, return (ok, seconds)."""
    start = time.time()
    with open(log, "a") as f:
        f.write(f"\n$ {' '.join(cmd)}\n")
        f.flush()
        done = subprocess.run(cmd, cwd=ROOT, env=environment(extra_env), stdout=f, stderr=subprocess.STDOUT)
    return done.returncode == 0, round(time.time() - start, 1)


def prepare(name, spec, rule_injection=None):
    folder = os.path.join(OUT, name)
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(os.path.join(folder, "in"))
    shutil.copy(spec, os.path.join(folder, "in", "spec.osc"))
    if rule_injection and os.path.exists(rule_injection):
        shutil.copy(rule_injection, os.path.join(folder, "in", "rule_injection.lp"))
    else:
        open(os.path.join(folder, "in", "rule_injection.lp"), "w").close()
    return folder


def simulate(folder, scenarios, config, sim_jobs, log, blueprint=None):
    """Simulate every scenario in a folder under one setting, then compute metrics and verdicts."""
    sims = os.path.join(folder, f"sim_{config}")
    spec = os.path.join(folder, "in", "spec.osc")
    env = CONFIGS[config]
    times = {}
    steps = [
        ("simulate", ["make", f"-j{sim_jobs}", "execute-all-scenarios",
                      f"SCENARIOS_FOLDER={scenarios}", f"OUTPUT_FOLDER={sims}"]),
        ("metrics", ["make", f"-j{sim_jobs}", "compute-selected-metrics-for-all-scenarios",
                     f"SCENARIOS_FOLDER={scenarios}", f"OUTPUT_FOLDER={sims}",
                     "selected_metrics=LANE LONGPOS CURRV"]),
        ("monitor", ["make", "-k", f"-j{sim_jobs}", "generate-summary", f"SCENARIOS_FOLDER={scenarios}",
                     f"OUTPUT_FOLDER={sims}", f"OSC_FILE={spec}"]
                    + ([f"BLUEPRINT_FOLDER={blueprint}"] if blueprint else [])),
    ]
    for label, cmd in steps:
        ok, seconds = run(cmd, log, env)
        times[f"{config}_{label}"] = seconds
        if not ok:
            times[f"{config}_{label}_failed"] = True
    return times


def scenarios_for(folder, config, log):
    """The scenario folder for a setting. The speedfix windows need the plans mapped again."""
    if config == "now":
        return os.path.join(folder, "cr_scenarios"), {}
    target = os.path.join(folder, f"cr_scenarios_{config}")
    ok, seconds = run([PYTHON, os.path.join(HERE, "remap.py"), "--exp-out", folder,
                       "--osc-file", os.path.join(folder, "in", "spec.osc"), "--target", target],
                      log, CONFIGS[config])
    return target, {f"{config}_remap": seconds}


def vanilla(name, spec, rule_injection, n, sim_jobs):
    folder = prepare(name, spec, rule_injection)
    log = os.path.join(folder, "log.txt")
    ok, seconds = run([PYTHON, "create_scenarios/create_plan_scenarios.py", "--osc-file",
                       os.path.join(folder, "in", "spec.osc"), "--n", str(n), "--output-folder", folder,
                       "--cr-scenario", CR_SCENARIO, "--step-length", "60", "--rule-injection",
                       os.path.join(folder, "in", "rule_injection.lp")], log)
    times = {"plan": seconds, "plan_failed": not ok}
    if ok and glob.glob(os.path.join(folder, "cr_scenarios", "*.xml")):
        for config in CONFIGS:
            scenarios, t = scenarios_for(folder, config, log)
            times.update(t)
            times.update(simulate(folder, scenarios, config, sim_jobs, log))
    return times


def variability(name, sim_jobs):
    source = os.path.join(ROOT, "experiments_src", name)
    folder = prepare(name, os.path.join(source, "in", "spec.osc"), os.path.join(source, "in", "rule_injection.lp"))
    log = os.path.join(folder, "log.txt")
    # the paper's own sampled instances, so the comparison is instance for instance
    shutil.copytree(os.path.join(source, "out", "partitions"), os.path.join(folder, "partitions"))
    ok, seconds = run([PYTHON, "create_scenarios/variability_experiments.py", "--output-folder", folder,
                       "--input-folder", os.path.join(folder, "partitions"), "--osc-file",
                       os.path.join(folder, "in", "spec.osc"), "--cr-scenario", CR_SCENARIO,
                       "--rule-injection", os.path.join(folder, "in", "rule_injection.lp"),
                       "--time-limit", "100"], log)
    times = {"plan": seconds, "plan_failed": not ok}
    if glob.glob(os.path.join(folder, "cr_scenarios", "*.xml")):
        for config in CONFIGS:
            scenarios, t = scenarios_for(folder, config, log)
            times.update(t)
            times.update(simulate(folder, scenarios, config, sim_jobs, log,
                                  blueprint=os.path.join(folder, "aux_asp")))
    return times


def inconsistent(name, imax=20):
    """Planning only: an inconsistent specification must come back with no plan."""
    sys.path[:0] = [ROOT]
    from planning.Planner import Planner
    from planning.asp.generate_plans import NoModelException
    folder = prepare(name, os.path.join(SPECS, f"{name}.osc"))
    controller = os.path.join(ROOT, "create_scenarios", "controller.lp")
    start = time.time()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            Planner(os.path.join(folder, "in", "spec.osc"), out_path=folder).plans(
                n=1, external_rules=[controller], visualize=False, imax=imax)
            outcome = "plan found"
        except NoModelException:
            outcome = "no plan"
    return {"plan": round(time.time() - start, 1), "outcome": outcome, "imax": imax}


def run_one(name, sim_jobs):
    started = time.time()
    try:
        if name in PAPER_VANILLA:
            source = os.path.join(ROOT, "experiments_src", name, "in")
            times = vanilla(name, os.path.join(source, "spec.osc"), os.path.join(source, "rule_injection.lp"),
                            10, sim_jobs)
        elif name in PAPER_VARIABILITY:
            times = variability(name, sim_jobs)
        elif name in NEW:
            times = vanilla(name, os.path.join(SPECS, f"{name}.osc"), None, NEW_N, sim_jobs)
        else:
            times = inconsistent(name)
    except Exception:
        times = {"error": traceback.format_exc()[-2000:]}
    times["total"] = round(time.time() - started, 1)
    os.makedirs(os.path.join(OUT, name), exist_ok=True)
    with open(os.path.join(OUT, name, "times.json"), "w") as f:
        json.dump(times, f, indent=1)
    return name, times


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="experiment names to run")
    ap.add_argument("--workers", type=int, default=3, help="experiments run at the same time")
    ap.add_argument("--sim-jobs", type=int, default=3, help="simulations at the same time per experiment")
    ap.add_argument("--skip-done", action="store_true", help="skip experiments that already have a times.json")
    args = ap.parse_args()

    # the slow ones first, so they do not end up last on their own
    everything = (["exp_004_b", "exp_004", "exp_005_b", "exp_002_b", "exp_003_b"]
                  + [e for e in PAPER_VARIABILITY + PAPER_VANILLA if e not in ("exp_004_b", "exp_004", "exp_005_b", "exp_002_b", "exp_003_b")]
                  + list(NEW))
    names = [n for n in everything + list(INCONSISTENT) if not args.only or n in args.only]
    if args.skip_done:
        names = [n for n in names if not os.path.exists(os.path.join(OUT, n, "times.json"))]
    os.makedirs(OUT, exist_ok=True)

    for name in [n for n in names if n in INCONSISTENT]:
        print(name, run_one(name, args.sim_jobs)[1], flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_one, n, args.sim_jobs) for n in names if n not in INCONSISTENT]
        for future in as_completed(futures):
            name, times = future.result()
            print(f"{time.strftime('%H:%M')} {name} done: {json.dumps(times)[:300]}", flush=True)


if __name__ == "__main__":
    main()
