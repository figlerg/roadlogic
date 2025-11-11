# visualize_experiments.py
import os, json, glob
import click
import matplotlib.pyplot as plt
from matplotlib import rcParams
import re
import itertools
import pandas as pd
from collections import defaultdict
import numpy as np

# LaTeX-friendly settings (vector fonts, serif)
rcParams.update({
    "text.usetex": True,
    "font.family": "serif",
    "font.serif": ["Computer Modern Roman"],
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
})

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
  
  "exp_007": "drive past static obstacle",
  "exp_007_b": "drive past static obstacle (partitioned)",
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
@click.option("--names", default=None,
              help='Optional mapping (path to JSON or inline JSON, e.g. \'{"exp_001_b":"overtake"}\').')
@click.option("--out", default="experiments_src/vis/experiments_summary.pdf", show_default=True,
              help="Output figure filename (PDF recommended).")
@click.option("--pattern", multiple=True, default=["experiments_src/logs/*.json"], show_default=True,
              help="One or more glob patterns of experiment json files.")
@click.option("--mode", type=click.Choice(["combined", "success", "timing"]),
              default="combined", show_default=True,
              help="What to plot: combined (default), only success rates, or only timing.")
def main(pattern, names, out, mode):
    # --- load and merge names ---
    name_map = names_default.copy()
    user_map = _load_names(names)
    name_map.update(user_map)

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

        match = re.match(r"exp_(\d+[a-z_]*)", base)
        exp_id = match.group(1) if match else base

        label = name_map.get(base, base)
        labels.append(f"{exp_id} • {label}")
        percents.append(pct)
        totals.append(tot)

    if max(percents, default=0) <= 1.0:
        percents = [v * 100 for v in percents]

    x = np.arange(len(labels))

    # --- timing data (only if needed) ---
    step_durations = defaultdict(dict)
    df = None
    if mode in ("combined", "timing"):
        step_alias = {
            "create_variability_instances": "partition",
            "variability_experiments": "plan",
            "generate-osc-scenarios": "plan",
            "execute-all-scenarios": "execute",
            "compute-metrics": "instrument",
            "generate-summary": "monitor",
        }
        order_bases = [os.path.splitext(os.path.basename(p))[0] for p in files]

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
            df = pd.DataFrame(step_durations).T.fillna(0)
            cols = [c for c in ["partition", "plan", "execute", "instrument", "monitor"] if c in df.columns]
            df = df.reindex(order_bases).fillna(0)
            df = df[cols]

    # --- figure setup depending on mode ---
    if mode == "combined":
        fig, (ax1, ax2) = plt.subplots(
            2, 1,
            figsize=(max(6, len(labels) * 1.3), 7.5),
            sharex=True,
            gridspec_kw={'height_ratios': [2.5, 1]}
        )
    elif mode == "success":
        fig, ax1 = plt.subplots(
            1, 1,
            figsize=(max(6, len(labels) * 1.3), 4.0),
        )
        ax2 = None
    else:  # timing
        fig, ax2 = plt.subplots(
            1, 1,
            figsize=(max(6, len(labels) * 1.3), 4.0),
        )
        ax1 = None

    # --- Top: success plot ---
    if mode in ("combined", "success"):
        ax1.bar(x, percents, color="tab:blue", alpha=0.9)
        ax1.set_ylabel(r"\% positive traces")
        ax1.set_title("Experiment results")
        ax1.set_ylim(0, max(percents) * 1.25 if percents else 100)
        ax1.grid(axis="y", linestyle="--", alpha=0.3)

        if mode == "success":
            ax1.set_xticks(x)
            ax1.set_xticklabels(labels, rotation=45, ha="right")

    # --- Bottom: timing plot ---
    if mode in ("combined", "timing"):
        if df is not None and not df.empty:
            colors = {
                "partition": "#A8D5BA",
                "plan": "#F7B7A3",
                "execute": "#A7C7E7",
                "instrument": "#C6B8E3",
                "monitor": "#FDDFA9",
            }

            bottom = np.zeros(len(df))
            for step in df.columns:
                heights = df[step].values
                ax2.bar(x, heights, bottom=bottom, color=colors.get(step, "gray"), label=step)
                bottom += heights

            total_times = df.sum(axis=1).astype(int)
            max_total = max(total_times) if len(total_times) else 0
            ax2.set_ylim(0, max_total * 1.15)

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

        if mode == "timing":
            ax2.set_xticks(x)
            ax2.set_xticklabels(labels, rotation=45, ha="right")

    # shared x for combined
    if mode == "combined":
        ax2.set_xticks(x)
        ax2.set_xticklabels(labels, rotation=45, ha="right")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    plt.tight_layout()
    plt.savefig(out, bbox_inches="tight")
    print(f"Wrote {out}")

if __name__ == "__main__":
    main()
