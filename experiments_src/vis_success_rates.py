# visualize_experiments.py
import os, json, glob
import click
import matplotlib.pyplot as plt
import re
import itertools
import pandas as pd
from collections import defaultdict
import numpy as np


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
@click.option("--names", default=None, help='Optional mapping (path to JSON or inline JSON, e.g. \'{"exp_001_b":"overtake"}\').')
@click.option("--out", default="experiments_src/vis/experiments_summary.png", show_default=True, help="Output image filename.")
@click.option("--pattern", multiple=True, default=["logs/*.json"], show_default=True,
              help="One or more glob patterns of experiment json files.")
def main(pattern, names, out):
    # --- load and merge names ---
    name_map = names_default.copy()
    user_map = _load_names(names)
    name_map.update(user_map)

    # files = sorted(glob.glob(pattern))
    files = sorted(set(itertools.chain.from_iterable(glob.glob(p) for p in pattern)))

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


    # assume imports are at top of your file
    # insert this as the plotting section at the end of visualize_experiments.py

    # === Combined plots for success rates + timing ===
    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=(max(6, len(labels) * 1.3), 7.5),  # slightly taller to avoid label overlap
        sharex=True,
        gridspec_kw={'height_ratios': [2.5, 1]}
    )

    # === Top plot: success rates ===
    x = np.arange(len(labels))
    ax1.bar(x, percents, color="tab:blue", alpha=0.9)
    ax1.set_ylabel("% positive traces")
    ax1.set_title("Experiment Results and Runtime Breakdown")
    ax1.set_ylim(0, max(percents) * 1.25 if percents else 100)
    ax1.grid(axis="y", linestyle="--", alpha=0.3)

    # === Bottom plot: timing breakdown ===
    step_alias = {
        "create_variability_instances": "partition",
        "variability_experiments": "plan",
        "generate-osc-scenarios": "plan",
        "execute-all-scenarios": "execute",
        "generate-summary": "monitor",
    }

    step_durations = defaultdict(dict)
    for p in files:
        base = os.path.splitext(os.path.basename(p))[0]
        exp_dir = os.path.join("experiments_src", base)
        times_path = os.path.join(exp_dir, "out", "times.jsonl")
        if not os.path.exists(times_path):
            continue
        with open(times_path, "r", encoding="utf-8") as tf:
            for line in tf:
                try:
                    entry = json.loads(line)
                    step = step_alias.get(entry.get("step"), entry.get("step", "unknown"))
                    step_durations[base][step] = step_durations[base].get(step, 0) + entry.get("seconds", 0)
                except json.JSONDecodeError:
                    continue

    if step_durations:
        df = pd.DataFrame(step_durations).fillna(0).T
        df = df[[c for c in ["partition", "plan", "execute", "monitor"] if c in df.columns]]

        colors = {
            "partition": "#A8D5BA",  # calm pastel green
            "plan": "#F7B7A3",       # soft red/orange
            "execute": "#A7C7E7",    # pastel blue
            "monitor": "#FDDFA9",    # light orange/yellow
        }

        bottom = np.zeros(len(df))
        for step in df.columns:
            ax2.bar(df.index, df[step], bottom=bottom, color=colors.get(step, "gray"), label=step)
            bottom += df[step].values

        total_times = df.sum(axis=1).astype(int)
        max_total = max(total_times) if len(total_times) else 0
        ax2.set_ylim(0, max_total * 1.15)  # taller frame for labels

        for i, t in enumerate(total_times):
            hrs, rem = divmod(t, 3600)
            mins, secs = divmod(rem, 60)
            label_time = (
                f"{hrs}h{mins:02d}m" if hrs else
                f"{mins}m{secs:02d}s" if mins else
                f"{secs}s"
            )
            ax2.text(i, t + max_total * 0.02, label_time,
                    ha="center", va="bottom", fontsize=8, color="#333")


        ax2.set_ylabel("Time (s)")
        ax2.grid(axis="y", linestyle="--", alpha=0.3)
        ax2.legend(
            frameon=True,
            loc="center right",
            title="Runtime phases",
            fontsize=8,
            title_fontsize=9,
        )
    else:
        ax2.text(0.5, 0.5, "No timing data found", ha="center", va="center")

    # === Shared x-axis labels only at bottom ===
    ax2.set_xticks(x)
    ax2.set_xticklabels(
        [name_map.get(os.path.splitext(os.path.basename(p))[0], os.path.splitext(os.path.basename(p))[0]) for p in files],
        rotation=45, ha="right"
    )

    plt.tight_layout()
    plt.savefig(out.replace(".png", "_combined.png"), dpi=150, bbox_inches="tight")
    print(f"Wrote {out.replace('.png', '_combined.png')}")

if __name__ == "__main__":
    main()
