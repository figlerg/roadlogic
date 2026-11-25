"""Simulation settings compared spec by spec, 10 scenarios each, everything else at the defaults.

    python paper_journal/benchmark/initial_speed.py <out.jsonl> <spec> [<spec> ...]
    COMPARE_SETTINGS='{"acc4": {"ROADLOGIC_CLASP_ARGS": "-c max_velocity_change_lon=4"}}' python ...

By default: cars starting from rest against starting at the plan's initial speed
(ROADLOGIC_INITIAL_SPEED). COMPARE_SETTINGS gives other named settings as JSON. One JSON line per spec
and setting: positive traces, and how many of them skipped a waypoint. Runs go to
demo_output/is_<spec>_<setting>. Run from the repository root with the venv active.
"""
import glob, json, os, sys
sys.path.insert(0, "tests")
from demo_pipeline import OUT, monitor_verdict, run_experiment

SETTINGS = json.loads(os.environ.get("COMPARE_SETTINGS", "null")) or \
    {"rest": {}, "plan": {"ROADLOGIC_INITIAL_SPEED": "plan"}}
out, specs = sys.argv[1], sys.argv[2:]
for spec in specs:
    name = os.path.splitext(os.path.basename(spec))[0]
    for label, settings in SETTINGS.items():
        run = f"is_{name}_{label}"
        try:
            run_experiment(run, spec, settings, scenarios=10, force=True)
            sims = sorted(glob.glob(os.path.join(OUT, "_work", run, "out", "cr_simulations", "scenario_*")))
            verdicts = [monitor_verdict(spec, s) for s in sims]
            deviated = [bool(glob.glob(os.path.join(s, "**", "missed_waypoints.csv"), recursive=True)
                             and any(os.path.getsize(f) > 0 and len(open(f).read().splitlines()) > 1
                                     for f in glob.glob(os.path.join(s, "**", "missed_waypoints.csv"), recursive=True)))
                        for s in sims]
            row = {"spec": spec, "initial_speed": label, "settings": settings, "scenarios": len(sims),
                   "positive": verdicts.count("POSITIVE"),
                   "positive_deviated": sum(v == "POSITIVE" and d for v, d in zip(verdicts, deviated)),
                   "verdicts": verdicts}
        except Exception as e:
            row = {"spec": spec, "initial_speed": label, "failed": str(e)[-500:]}
        with open(out, "a") as f:
            f.write(json.dumps(row) + "\n")
        print(json.dumps({k: v for k, v in row.items() if k != "verdicts"}), flush=True)
