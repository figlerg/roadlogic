# vis_vanilla_timing.py
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
# Compact ACM-like sizing
rcParams.update({
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
})

names_default = {
  "exp_001":   "Follow",
  "exp_001_b": "Follow (var.)",
  "exp_001_c": "Follow (car1 fixed)",

  "exp_002":   "Overtake",
  "exp_002_b": "Overtake (var.)",
  "exp_002_c": "Overtake (car1 fixed)",

  "exp_003":   "Overtake + 3rd actor",
  "exp_003_b": "Overtake + 3rd actor (var.)",
  "exp_003_c": "Overtake + 3rd actor (car1 fixed)",

  "exp_004":   "Overtake + fixed lane",
  "exp_004_b": "Overtake + fixed lane (var.)",

  "exp_005":   "Overtake + obstacle",
  "exp_005_b": "Overtake + obstacle (var.)",
  "exp_005_c": "Overtake + obstacle (car1 fixed)",

  "exp_006":   "Change lane",
  "exp_006_b": "Change lane (var.)",
  "exp_006_c": "Change lane (car1 fixed)",

  "exp_007":   "Dodge obstacle",
  "exp_007_b": "Dodge obstacle (var.)",
}

def _load_names(names_arg):
    if not names_arg:
        return {}
    if isinstance(names_arg, dict):
        return names_arg
    if os.path.exists(names_arg):
        with open(names_arg, "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(names_arg)

@click.command()
@click.option(
    "--names",
    default=None,
    help="JSON file or inline JSON mapping experiment ids to labels."
)
@click.option(
    "--out",
    default="paper/03_success_time/vis_vanilla_timing.pdf",
    show_default=True,
)
@click.option(
    "--pattern",
    multiple=True,
    default=["experiments_src/logs/exp_00[0-9].json"],
    show_default=True,
    help="Glob(s) for vanilla summary JSON logs."
)
def main(pattern, names, out):
    # --- load names ---
    name_map = names_default.copy()
    name_map.update(_load_names(names))

    files = sorted(set(itertools.chain.from_iterable(glob.glob(p) for p in pattern)))
    if not files:
        raise SystemExit(f"No files matched pattern: {pattern}")

    labels = []
    order_bases = []

    for p in files:
        base = os.path.splitext(os.path.basename(p))[0]
        order_bases.append(base)

        # === unified naming scheme (same as combined script) ===
        m = re.match(r"exp_(\d+)(?:_([a-z]))?$", base)
        if m:
            num = m.group(1)      # "001"
            suff = m.group(2)     # "b", "c", or None

            if suff is None:
                # vanilla → baseline
                exp_label = f"{num}-b"
            elif suff == "b":
                # variability → refined
                exp_label = f"{num}-r"
            else:
                # other suffixes if needed
                exp_label = f"{num}-{suff}"
        else:
            exp_label = base

        disp = name_map.get(base, base)
        labels.append(f"{exp_label} • {disp}")

    x = np.arange(len(labels))

    # --- load timing data ---
    step_durations = defaultdict(dict)
    df = None

    step_alias = {
        "create_variability_instances": "sampling",
        "variability_experiments":     "plan",
        "generate-osc-scenarios":      "plan",
        "execute-all-scenarios":       "execute",
        "compute-metrics":             "instrument",
        "generate-summary":            "monitor",
    }

    for p in files:
        base = os.path.splitext(os.path.basename(p))[0]
        times_path = os.path.join("experiments_src", base, "out", "times.jsonl")
        if not os.path.exists(times_path):
            continue
        with open(times_path, "r", encoding="utf-8") as tf:
            for line in tf:
                try:
                    entry = json.loads(line)
                    step = step_alias.get(entry["step"], entry["step"])
                    step_durations[base][step] = step_durations[base].get(step, 0) + entry["seconds"]
                except Exception:
                    continue

    if step_durations:
        df = pd.DataFrame(step_durations).T.fillna(0)
        cols = [c for c in ["plan","execute","instrument","monitor"] if c in df.columns]
        df = df.reindex(order_bases).fillna(0)
        df = df[cols]

    # --- layout size ---
    base_w   = min(6.9, max(3.2, 0.18 * len(labels) + 2.2))
    SINGLE_H = 2.6

    # factor to control how much vertical margin above tallest bar
    Y_MARGIN = 1.2   # <<< dial this up/down to change how much the bars fill the frame

    fig, ax2 = plt.subplots(1, 1, figsize=(base_w, SINGLE_H))

    if df is not None and not df.empty:
        colors = {
            "sampling":  "#A8D5BA",
            "plan":       "#F7B7A3",
            "execute":    "#A7C7E7",
            "instrument": "#C6B8E3",
            "monitor":    "#FDDFA9",
        }

        bottom = np.zeros(len(df))
        for step in df.columns:
            ax2.bar(x, df[step].values, 0.7, bottom=bottom,
                    color=colors.get(step,"gray"), label=step)
            bottom += df[step].values

        total_times = df.sum(axis=1).astype(int)
        max_total = max(total_times) if len(total_times) else 0

        # === y-limit tuning point ===
        ax2.set_ylim(0, max_total * Y_MARGIN)

        # optional: if 10000 is meaningless, you can remove or adapt this
        # ax2.set_yticks([10000])

        for i, t in enumerate(total_times):
            hrs, rem = divmod(t, 3600)
            mins, secs = divmod(rem, 60)
            if hrs:
                label = f"{hrs}h{mins:02d}m"
            elif mins:
                label = f"{mins}m{secs:02d}s"
            else:
                label = f"{secs}s"
            ax2.text(i, t + max_total * 0.02, label,
                     ha="center", va="bottom", fontsize=6.5)

        ax2.set_ylabel("Time (s)")
        ax2.grid(axis="y", linestyle="--", alpha=0.3)

        alias = {"sampling":"Var.","plan":"Plan","execute":"Exec.","instrument":"Instr.","monitor":"Mon."}
        h, lab = ax2.get_legend_handles_labels()
        lab = [alias.get(s, s) for s in lab]

        ax2.legend(
            h, lab,
            loc="upper center",
            # legend minimal nach oben geschoben
            bbox_to_anchor=(0.5, 1.20),  # <<< move this up/down vertically
            ncol=len(lab),
            frameon=True,
            fontsize=6.5,
            handlelength=1.0,
        )
        fig.subplots_adjust(top=0.83)
    else:
        ax2.text(0.5, 0.5, "No timing data",
                 ha="center", va="center")

    ax2.set_xticks(x)
    ax2.set_xticklabels(labels, rotation=35, ha="right", fontsize=6.5)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    plt.tight_layout(pad=0.6)
    plt.savefig(out, bbox_inches="tight")
    print(f"Wrote {out}")

if __name__ == "__main__":
    main()
