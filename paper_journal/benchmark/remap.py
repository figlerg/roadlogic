"""Turn stored plans into CommonRoad scenarios again, with the speed-window settings of the current
environment. The plans themselves are not recomputed, so two settings can share one planning run.

    python paper_journal/benchmark/remap.py --exp-out <out folder of a run> --osc-file <spec> --target <folder>
"""
import argparse
import glob
import os
import pickle
import sys
import tempfile
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exp-out", required=True)
    ap.add_argument("--osc-file", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--cr-scenario", default=os.path.join(ROOT, "cr_scenarios", "threelanes.xml"))
    args = ap.parse_args()
    warnings.simplefilter("ignore")

    from commonroad.common.file_reader import CommonRoadFileReader
    from commonroad_extensions.plan_execution.map_plan import map_plan
    from create_scenarios.create_plan_scenarios import speed_constrained_actors
    from planning.Planner import Planner

    scenario, _ = CommonRoadFileReader(args.cr_scenario).open()
    actors = speed_constrained_actors(Planner(args.osc_file, out_path=tempfile.mkdtemp()).translation_graph)
    os.makedirs(args.target, exist_ok=True)
    plans = sorted(glob.glob(os.path.join(args.exp_out, "serialized_models", "*.pkl")))
    for path in plans:
        stem = os.path.splitext(os.path.basename(path))[0]
        with open(path, "rb") as f:
            plan = pickle.load(f)
        map_plan(scenario=scenario, plan_model=plan, anchor_lane_idx=1,
                 save_path=os.path.join(args.target, f"scenario_{stem}.xml"), speed_actors=actors)
    print(f"remapped {len(plans)} plans into {args.target}")


if __name__ == "__main__":
    main()
