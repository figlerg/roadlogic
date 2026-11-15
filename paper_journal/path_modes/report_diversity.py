"""Tables for the README from the result files, so every number there can be regenerated.

    python paper_journal/path_modes/report_diversity.py

Reads paper_curves_*.jsonl (the paper's restarts, rerun), conflicts_*.jsonl (rise0.7 with conflict
budgets), final_*.jsonl (the candidate grid with wall-clock budgets) and independent_*.jsonl, and prints
markdown. Every run in those files is shown, none is left out.
"""
import glob, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
load = lambda pattern: [json.loads(l) for f in sorted(glob.glob(os.path.join(HERE, pattern))) for l in open(f)]
SPECS = ["exp_001", "exp_002", "exp_003", "exp_004", "exp_005", "exp_006", "exp_007"]


def cell(curve, k):
    c = (curve or {}).get(str(k))
    return f"{c[0]:.2f} / {c[1]:.0f} s" if c else "-"


def row(label, r):
    if r.get("failed"):
        return f"| {label} | failed: {r['failed']} | | | | |"
    c = r.get("curve")
    return (f"| {label} | {r['plans']} | {cell(c, 10)} | {cell(c, 20)} | {cell(c, 50)} | "
            f"{r.get('mean_similarity', '-') if 'mean_similarity' in r else '-'} |")


paper = {r["spec"]: r for r in load("paper_curves_*.jsonl")}
conflicts = load("conflicts_*.jsonl")
final = load("final_*.jsonl")

print("## rise0.7 with a deterministic conflict budget against the paper's restarts\n")
print("Cells: mean pairwise similarity of the first k plans / seconds until the k-th. Lower is more varied.\n")
for spec in SPECS:
    runs = [r for r in conflicts if r["spec"] == spec]
    if spec not in paper and not runs:
        continue
    print(f"### {spec}\n")
    print("| method | plans | k = 10 | k = 20 | k = 50 | mean, all plans |")
    print("|---|---|---|---|---|---|")
    if spec in paper:
        p = dict(paper[spec])
        print(row("paper restarts (rerun)", p))
    for r in sorted(runs, key=lambda r: (r.get("controller", ""), r.get("conflicts", 0), r.get("repetition", 0))):
        label = f"rise0.7, {r.get('conflicts')} conflicts"
        if r.get("controller") == "controller_params.lp":
            label += ", parameter space"
        if r.get("repetition"):
            label += f", run {r['repetition']}"
        print(row(label, r))
    print()

print("## The candidate grid (wall-clock budget of 10 s per plan, 4 jobs at a time)\n")
print("These depend on machine load, see the README. Kept for completeness.\n")
for spec in SPECS:
    runs = [r for r in final if r["spec"] == spec]
    if not runs:
        continue
    print(f"### {spec}\n")
    print("| method | plans | k = 10 | k = 20 | k = 50 | mean, all plans |")
    print("|---|---|---|---|---|---|")
    for r in runs:
        label = r["method"]
        if r["method"].startswith("rise"):
            label += f", cap {r.get('cap')}, +{r.get('extra')} horizons"
        if r.get("controller") in ("controller_params.lp", "params"):
            label += ", parameter space"
        print(row(label, r))
    print()

print("## Measures the IoU constraint does not target\n")
print("| set | plans | distinct footprints | lane-change patterns | start configurations | goal timings |")
print("|---|---|---|---|---|---|")
for r in load("independent_*.jsonl"):
    print(f"| {r['set']} | {r['plans']} | {r['footprints']} | {r['lane_patterns']} | {r['starts']} | {r['goal_timings']} |")
