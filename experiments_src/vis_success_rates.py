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
# Compact ACM-like sizing
rcParams.update({
    "font.size": 8,
    "axes.titlesize": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
})

names_default= {
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
  "exp_004_b":   "Overtake + fixed lane (var.)",

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
    order_bases = []
    for p in files:
        base = os.path.splitext(os.path.basename(p))[0]
        order_bases.append(base)

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        pct = data.get("percent_positive_traces", 0)
        tot = data.get("total_runs", 0)

        # compact, professional x-labels: ID + short name
        m = re.match(r"exp_(\d+)(_[a-z])?$", base)
        exp_id = (m.group(1) + (m.group(2) or "")) if m else base
        disp   = name_map.get(base, base)

        labels.append(f"{exp_id} • {disp}")
        percents.append(pct)
        totals.append(tot)

    # if values in [0,1], convert to %
    if max(percents, default=0) <= 1.0:
        percents = [v * 100 for v in percents]

    x = np.arange(len(labels))

    # --- timing data (only if needed) ---
    step_durations = defaultdict(dict)
    df = None
    if mode in ("combined", "timing"):
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
            # cols = [c for c in ["sampling", "plan", "execute", "instrument", "monitor"] if c in df.columns]
            cols = [c for c in ["plan", "execute", "instrument", "monitor"] if c in df.columns]
            # keep order of input files
            df = df.reindex(order_bases).fillna(0)
            df = df[cols]

    # Target ~double-column width ~6.9in; cap width so plots don't bloat
    base_w = min(6.9, max(3.2, 0.18*len(labels) + 2.2))  # scales a bit with N, capped
    COMBINED_H = 3.4
    SINGLE_H   = 2.1


    if "exp_*_b" in pattern[0]:
        figtitle = "Parameter Variation Results"
    if "exp_00[0-9]" in pattern[0]:
        figtitle = "Vanilla Pipeline "


    # --- figure setup depending on mode ---
    if mode == "combined":
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(base_w, COMBINED_H),
            sharex=True, gridspec_kw={'height_ratios':[2.2, 1]} # was 2.2
        )
    elif mode == "success":
        fig, ax1 = plt.subplots(1, 1, figsize=(base_w, SINGLE_H))
        ax2 = None
    else:  # timing
        fig, ax2 = plt.subplots(1, 1, figsize=(base_w, SINGLE_H))
        ax1 = None

    # --- Top: success plot ---
    if mode in ("combined", "success"):
        ax1.bar(x, percents, width=0.7, color="tab:blue", alpha=0.9)
        ax1.set_ylabel(r"\% positive traces")
        # ax1.set_title(figtitle)
        ax1.set_ylim(0, max(percents) * 1.25 if percents else 100)
        ax1.grid(axis="y", linestyle="--", alpha=0.3)

        if mode == "success":
            ax1.set_xticks(x)
            ax1.set_xticklabels(labels, rotation=35, ha="right", fontsize=6.5)

    # --- Bottom: timing plot ---
    if mode in ("combined", "timing"):
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
                heights = df[step].values
                ax2.bar(x, heights, width=0.7, bottom=bottom,
                        color=colors.get(step, "gray"), label=step)
                bottom += heights

            total_times = df.sum(axis=1).astype(int)
            max_total = max(total_times) if len(total_times) else 0
            ax2.set_ylim(0, max_total * 1.25)

            for i, t in enumerate(total_times):
                hrs, rem = divmod(t, 3600)
                mins, secs = divmod(rem, 60)
                label_time = (f"{hrs}h{mins:02d}m" if hrs else f"{mins}m{secs:02d}s" if mins else f"{secs}s")
                ax2.text(i, t + max_total * 0.02, label_time,
                         ha="center", va="bottom", fontsize=6.5, color="#333")

            ax2.set_ylabel("Time (s)")
            ax2.grid(axis="y", linestyle="--", alpha=0.3)

            # compact legend with short labels, outside
            alias_short = {"sampling":"Var.", "plan":"Plan", "execute":"Exec.", "instrument":"Instr.", "monitor":"Mon."}
            h, lab = ax2.get_legend_handles_labels()
            lab = [alias_short.get(s, s) for s in lab]
            leg = ax2.legend(h, lab,
                 loc="upper center",
                 bbox_to_anchor=(0.5, 1.35),   # was 1.32
                 ncol=len(lab),
                 frameon=True,
                 handlelength=1.0,
                 columnspacing=0.9,
                 borderaxespad=0.0,
                 fontsize=6.5)
            # reserve space for legend row
            if mode == "combined":
                fig.subplots_adjust(top=0.86)
            else:
                fig.subplots_adjust(top=0.83)

        else:
            ax2.text(0.5, 0.5, "No timing data found", ha="center", va="center")

        if mode == "timing":
            ax2.set_xticks(x)
            ax2.set_xticklabels(labels, rotation=35, ha="right", fontsize=6.5)

    # shared x for combined
    if mode == "combined":
        ax2.set_xticks(x)
        ax2.set_xticklabels(labels, rotation=35, ha="right", fontsize=6.5)

    # if mode == "timing":
        # ax2.set_title(figtitle)


    os.makedirs(os.path.dirname(out), exist_ok=True)
    # tighter padding; legend space handled via subplots_adjust
    plt.tight_layout(pad=0.6)
    plt.savefig(out, bbox_inches="tight")
    print(f"Wrote {out}")

if __name__ == "__main__":
    main()
