# visualize_experiments.py
import os, json, glob
import click
import matplotlib.pyplot as plt
import re



names_default= {
  "exp_001": "follow",
  "exp_001_b": "follow (partitioned)",
  "exp_001_c": "follow (car1 fixed)",
  
  "exp_002": "overtake",
  "exp_002_b": "overtake (partitioned)",
  "exp_002_c": "overtake (car1 fixed)",
  
  "exp_003": "overtake + free actor",
  "exp_003_b": "overtake + free actor (partitioned)",
  "exp_003_c": "overtake + free actor (car1 fixed)",
  
  "exp_004": "overtake + fixed lane",
  "exp_004_b": "overtake + fixed lane (partitioned)",
  "exp_004_c": "overtake + fixed lane (car1 fixed)",
  
  "exp_005": "overtake + static obstacle",
  "exp_005_b": "overtake + static obstacle (partitioned)",
  "exp_005_c": "overtake + static obstacle (car1 fixed)",
  
  "exp_006": "two cars, left lane change",
  "exp_006_b": "two cars, left lane change (partitioned)",
  "exp_006_c": "two cars, left lane change (car1 fixed)",
  
  "exp_007": "follow (basic heuristic)",
  "exp_007_b": "follow (basic heuristic, partitioned)",
  "exp_007_c": "follow (basic heuristic, car1 fixed)",
  
  "exp_008": "drive past static obstacle",
  "exp_008_b": "drive past static obstacle (partitioned)",
}

def _load_names(names_arg):
    if not names_arg:
        return {}
    if isinstance(names_arg, dict):  # just in case
        return names_arg
    if os.path.exists(names_arg):
        with open(names_arg, "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(names_arg)

@click.command()
@click.option("--pattern", default="experiments_src/logs/*.json", show_default=True, help="Glob of experiment json files.")
@click.option("--names", default=None, help='Optional mapping (path to JSON or inline JSON, e.g. \'{"exp_001_b":"overtake"}\').')
@click.option("--out", default="experiments_src/vis/experiments_summary.png", show_default=True, help="Output image filename.")
def main(pattern, names, out):
    # --- load and merge names ---
    name_map = names_default.copy()
    user_map = _load_names(names)
    name_map.update(user_map)

    files = sorted(glob.glob(pattern))
    if not files:
        raise SystemExit(f"No files matched pattern: {pattern}")

    labels, percents, totals = [], [], []
    for p in files:
        base = os.path.splitext(os.path.basename(p))[0]
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        pct = data.get("percent_positive_traces", 0)
        tot = data.get("total_runs", 0)

        # extract full experiment id (e.g. "001_b", "002_c")
        match = re.match(r"exp_(\d+[a-z_]*)", base)
        exp_id = match.group(1) if match else base

        label = name_map.get(base, base)
        labels.append(f"{exp_id} • {label}")
        percents.append(pct)
        totals.append(tot)

    # convert fraction → percentage if necessary
    if max(percents, default=0) <= 1.0:
        percents = [v * 100 for v in percents]

    xticks = [f"{lab}\n(n={n})" for lab, n in zip(labels, totals)]
    plt.figure(figsize=(max(6, len(labels)*1.2), 5))
    plt.bar(range(len(labels)), percents)
    plt.xticks(range(len(labels)), xticks, rotation=45, ha="right")
    plt.ylabel("% positive traces")
    plt.title("Experiment Results")
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    print(f"Wrote {out}")

if __name__ == "__main__":
    main()
