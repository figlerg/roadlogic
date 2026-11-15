"""Measures of variety the IoU constraint does not target directly, for folders of pickled plans.

    python paper_journal/path_modes/independent.py <label>=<folder> ...

Per folder: number of plans, distinct footprints (exact cell sets), distinct lane-change patterns (each
car's lane sequence with repeats removed), distinct start configurations (all states at step 0), and
distinct goal timings (the goal times of each plan's first witness). Prints one JSON line per folder.
"""
import glob, json, os, pickle, sys
sys.path.insert(0, "tests")
from plan_checks import goal_witnesses, lanes_of, states
from commonroad_extensions.plan_execution.map_plan import get_covered_cell

for arg in sys.argv[1:]:
    label, folder = arg.split("=", 1)
    plans = [pickle.load(open(f, "rb")) for f in sorted(glob.glob(os.path.join(folder, "*.pkl")))]
    actors = sorted({a for a, *_ in states(plans[0])}) if plans else []

    def pattern(p):
        out = []
        for a in actors:
            lanes = lanes_of(p, a)
            out.append(tuple(l for i, l in enumerate(lanes) if i == 0 or l != lanes[i - 1]))
        return tuple(out)

    print(json.dumps({
        "set": label, "plans": len(plans),
        "footprints": len({frozenset(get_covered_cell(p, float("inf"))) for p in plans}),
        "lane_patterns": len({pattern(p) for p in plans}),
        "starts": len({tuple(sorted(str(s) for s in states(p) if s[1] == 0)) for p in plans}),
        "goal_timings": len({tuple(goal_witnesses(p)[0]) if goal_witnesses(p) else () for p in plans}),
    }))
