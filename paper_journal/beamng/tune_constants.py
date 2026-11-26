"""Are the planner's constants simulator specific? Plans a few scenarios per spec under different ASP
constants (planning/asp/encoding/constants.lp, overridden with ROADLOGIC_CLASP_ARGS "-c name=value"),
simulates them in the CommonRoad simulation (Frenetix) and in BeamNG, and records both verdicts.

    python paper_journal/beamng/tune_constants.py <out.jsonl> --settings base gap8 --specs exp_003 exp_005 --n 3

Runs go to paper_journal/benchmark/out/tune_<spec>_<setting>/ (sim_default/ and sim_beamng/). One JSON line
per spec and setting. Run from the repository root with the venv active.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "paper_journal", "benchmark"))
sys.path.insert(0, HERE)
import run_benchmark as rb          # noqa: E402
import run_beamng as rbn            # noqa: E402

SETTINGS = {
    "base": "",
    "gap8": "-c safety_distance=8",                                   # a larger gap between cars in one lane
    "gap8_back10": "-c safety_distance=8 -c safety_distance_back=10",  # and behind a lane change
    "acc4": "-c max_velocity_change_lon=4",                            # gentler acceleration
}


def spec_file(name):
    for folder in (rb.SPECS_PAPER, rb.SPECS):
        if os.path.exists(os.path.join(folder, f"{name}.osc")):
            return os.path.join(folder, f"{name}.osc")
    raise FileNotFoundError(name)


def one(spec, setting, n, session):
    folder = rb.prepare(f"tune_{spec}_{setting}", spec_file(spec))
    log = os.path.join(folder, "log.txt")
    extra = {"ROADLOGIC_CLASP_ARGS": SETTINGS[setting]} if SETTINGS[setting] else {}
    ok, plan_s = rb.run([rb.PYTHON, "create_scenarios/create_plan_scenarios.py", "--osc-file",
                         os.path.join(folder, "in", "spec.osc"), "--n", str(n), "--output-folder", folder,
                         "--cr-scenario", rb.CR_SCENARIO, "--step-length", "60", "--rule-injection",
                         os.path.join(folder, "in", "rule_injection.lp")], log, extra)
    row = {"spec": spec, "setting": setting, "clasp": SETTINGS[setting], "plan_s": plan_s, "planned": ok}
    if not ok:
        return row
    rb.simulate(folder, os.path.join(folder, "cr_scenarios"), "default", 3, log)
    scenarios = rbn.stored(folder)
    r = rbn.run_experiment(session, folder, scenarios, video=False, skip_done=False)
    row.update({k: r[k] for k in ("scenarios", "beamng", "commonroad", "failed")})
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--settings", nargs="+", default=["base", "gap8"])
    ap.add_argument("--specs", nargs="+", default=["exp_002", "exp_003", "exp_005", "keep_lane_modifier"])
    ap.add_argument("--n", type=int, default=3)
    a = ap.parse_args()
    from commonroad_extensions.beamng.execute import Session
    with Session(os.path.join(ROOT, "demo_output", "beamng_logs")) as session:
        for setting in a.settings:
            for spec in a.specs:
                t = time.time()
                row = one(spec, setting, a.n, session)
                with open(a.out, "a") as f:
                    f.write(json.dumps(row) + "\n")
                b, c = row.get("beamng", {}), row.get("commonroad", {})
                print(f"{spec} {setting}: BeamNG {list(b.values()).count('POSITIVE')}/{len(b)}, "
                      f"CommonRoad {list(c.values()).count('POSITIVE')}/{len(c)}, {time.time() - t:.0f} s", flush=True)


if __name__ == "__main__":
    main()
