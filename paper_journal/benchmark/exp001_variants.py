"""exp_001 and spec fixes for it, 10 simulated scenarios each, one JSON line per variant.

    python paper_journal/benchmark/exp001_variants.py <out.jsonl>

Variants: the journal spec, the spec with a duration on ego's last phase, and the same with speed
windows for every car (ROADLOGIC_GOAL_VELOCITY_SCOPE=all). Runs go to demo_output/x001_<variant>.
Run from the repository root with the venv active.
"""
import glob, json, os, sys
sys.path.insert(0, "tests")
import pandas as pd
from demo_pipeline import DEFAULT, OUT, monitor_verdict, run_experiment
from commonroad_extensions.plan_execution.id_hash import decode

VARIANTS = [("journal", "paper_journal/benchmark/specs_paper/exp_001.osc", DEFAULT),
            ("duration", "paper_journal/benchmark/specs_variants/exp_001_duration.osc", DEFAULT),
            ("duration_all_windows", "paper_journal/benchmark/specs_variants/exp_001_duration.osc",
             {"ROADLOGIC_GOAL_VELOCITY_SCOPE": "all"})]
out = sys.argv[1]
for name, spec, settings in VARIANTS:
    run = f"x001_{name}"
    try:
        run_experiment(run, spec, settings, scenarios=10, force=True)
        sims = sorted(glob.glob(os.path.join(OUT, "_work", run, "out", "cr_simulations", "scenario_*")))
        verdicts, ego_changed = [], []
        for sim in sims:
            verdicts.append(monitor_verdict(spec, sim))
            lanes = pd.read_csv(os.path.join(sim, "LANE.csv"))
            lanes["car"] = lanes.agent_id.map(decode)
            ego_changed.append(int(lanes[lanes.car == "ego"].lane.nunique() > 1))
        row = {"variant": name, "spec": spec, "settings": settings, "scenarios": len(sims),
               "positive": verdicts.count("POSITIVE"), "ego_changed_lane": sum(ego_changed), "verdicts": verdicts}
    except Exception as e:
        row = {"variant": name, "failed": str(e)[-500:]}
    with open(out, "a") as f:
        f.write(json.dumps(row) + "\n")
    print(row)
