# vis_success_rates.py
import os, json, glob
import click
import matplotlib.pyplot as plt
from matplotlib import rcParams
import re
import itertools
import pandas as pd
from collections import defaultdict
import numpy as np

# LaTeX-friendly settings
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

# ============================================================
# === PLOTTING FUNCTIONS =====================================
# ============================================================

def plot_success(ax, x, labels, percents, mode):
    ax.bar(x, percents, width=0.7, color="tab:blue", alpha=0.9)
    ax.set_ylabel(r"\% positive traces")
    ax.set_ylim(0, max(percents) * 1.35 if percents else 100)
    ax.grid(axis="y", linestyle="--", alpha=0.3)

    if mode == "success":
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=6.5)


def plot_outcome(ax, x, labels, outcome_triplets, mode):
    pos_vals  = [t[0] for t in outcome_triplets]
    cost_vals = [t[1] for t in outcome_triplets]
    tout_vals = [t[2] for t in outcome_triplets]

    bottom = np.zeros(len(labels))

    ax.bar(x, pos_vals, 0.7, bottom=bottom,
           color="#4C72B0", label="Sat")
    bottom += pos_vals

    ax.bar(x, cost_vals, 0.7, bottom=bottom,
           color="#DD8452", label="Unsat")
    bottom += cost_vals

    ax.bar(x, tout_vals, 0.7, bottom=bottom,
           color="#888888", label="Timeout")

    ax.set_ylabel("Outcome fractions")
    ax.set_ylim(0, 1.05)
    ax.grid(axis="y", linestyle="--", alpha=0.3)

    ax.legend(loc="upper center",
              bbox_to_anchor=(0.5, 1.25),
              ncol=3, frameon=True, fontsize=6.5)

    if mode == "outcome":
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=6.5)


def plot_timing(ax, x, labels, df, mode, fig):
    if df is None or df.empty:
        ax.text(0.5, 0.5, "No timing data found", ha="center", va="center")
        return

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
        ax.bar(x, heights, width=0.7, bottom=bottom,
               color=colors.get(step, "gray"), label=step)
        bottom += heights

    total_times = df.sum(axis=1).astype(int)
    max_total = max(total_times) if len(total_times) else 0
    ax.set_ylim(0, max_total * 1.35)

    for i, t in enumerate(total_times):
        hrs, rem = divmod(t, 3600)
        mins, secs = divmod(rem, 60)
        label_time = (
            f"{hrs}h{mins:02d}m" if hrs
            else f"{mins}m{secs:02d}s" if mins
            else f"{secs}s"
        )
        ax.text(i, t + max_total * 0.02, label_time,
                ha="center", va="bottom", fontsize=6.5, color="#333")

    ax.set_ylabel("Time (s)")
    ax.grid(axis="y", linestyle="--", alpha=0.3)

    alias_short = {
        "sampling": "Var.",
        "plan": "Plan",
        "execute": "Exec.",
        "instrument": "Instr.",
        "monitor": "Mon.",
    }
    h, lab = ax.get_legend_handles_labels()
    lab = [alias_short.get(s, s) for s in lab]

    ax.legend(
        h, lab,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.45),
        ncol=len(lab),
        frameon=True,
        handlelength=1.0,
        columnspacing=0.9,
        borderaxespad=0.0,
        fontsize=6.5,
    )

    if mode in ("combined", "combined_outcome"):
        fig.subplots_adjust(top=0.86)
    else:
        fig.subplots_adjust(top=0.83)

    if mode == "timing":
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=6.5)

# ============================================================
# === MAIN ====================================================
# ============================================================

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
@click.option("--names", default=None)
@click.option("--out", default="experiments_src/vis/experiments_summary.pdf")
@click.option("--pattern", multiple=True, default=["experiments_src/logs/*.json"])
@click.option("--mode", type=click.Choice(
    ["combined", "success", "timing", "outcome", "combined_outcome"]),
    default="combined")
def main(pattern, names, out, mode):

    name_map = names_default.copy()
    name_map.update(_load_names(names))

    files = sorted(set(itertools.chain.from_iterable(glob.glob(p) for p in pattern)))
    if not files:
        raise SystemExit(f"No files matched pattern: {pattern}")

    labels, percents, totals = [], [], []
    order_bases = []
    outcome_triplets = []

    for p in files:
        base = os.path.splitext(os.path.basename(p))[0]
        order_bases.append(base)

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        tot = data.get("total_runs", 0)
        pos = data.get("num_positive_traces", 0)
        succ = data.get("successful_runs", 0)
        tout = data.get("num_timeout", 0)

        if tot > 0:
            outcome_triplets.append((
                pos / tot,
                max(succ - pos, 0) / tot,
                tout / tot
            ))
        else:
            outcome_triplets.append((0, 0, 0))

        percents.append(pos / tot * 100 if tot else 0)

        m = re.match(r"exp_(\d+)(?:_([a-z]))?$", base)
        if m:
            num, suff = m.group(1), m.group(2)
            exp_label = f"{num}-b" if suff is None else f"{num}-r" if suff == "b" else f"{num}-{suff}"
        else:
            exp_label = base

        disp = name_map.get(base, base)
        labels.append(f"{exp_label} • {disp}")

    x = np.arange(len(labels))

    # --- timing data ---
    df = None
    if mode in ("combined", "timing", "combined_outcome"):
        step_durations = defaultdict(dict)
        step_alias = {
            "create_variability_instances": "sampling",
            "variability_experiments": "plan",
            "generate-osc-scenarios": "plan",
            "execute-all-scenarios": "execute",
            "compute-metrics": "instrument",
            "generate-summary": "monitor",
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
                        step_durations[base][step] = \
                            step_durations[base].get(step, 0) + entry["seconds"]
                    except:
                        pass

        if step_durations:
            df = pd.DataFrame(step_durations).T.fillna(0)
            df = df.reindex(order_bases).fillna(0)
            df = df[[c for c in ["plan", "execute", "instrument", "monitor"] if c in df.columns]]

    # --- figure layout ---
    base_w = min(6.9, max(3.2, 0.18 * len(labels) + 2.2))
    COMBINED_H, SINGLE_H = 3.4, 2.1

    if mode in ("combined", "combined_outcome"):
        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(base_w, COMBINED_H),
            sharex=True, gridspec_kw={"height_ratios": [2.2, 1]}
        )
    elif mode in ("success", "outcome"):
        fig, ax1 = plt.subplots(1, 1, figsize=(base_w, SINGLE_H))
        ax2 = None
    else:
        fig, ax2 = plt.subplots(1, 1, figsize=(base_w, SINGLE_H))
        ax1 = None

    if mode in ("combined", "success"):
        plot_success(ax1, x, labels, percents, mode)

    if mode in ("outcome", "combined_outcome"):
        plot_outcome(ax1, x, labels, outcome_triplets, mode)

    if mode in ("combined", "timing", "combined_outcome"):
        plot_timing(ax2, x, labels, df, mode, fig)

    if mode in ("combined", "combined_outcome"):
        ax2.set_xticks(x)
        ax2.set_xticklabels(labels, rotation=35, ha="right", fontsize=6.5)

    # if mode == "combined_outcome":
    #     ax2.legend(loc="upper center",
    #         bbox_to_anchor=(0.5, 1.3),
    #         ncol=3, frameon=True, fontsize=6.5)


    os.makedirs(os.path.dirname(out), exist_ok=True)
    plt.tight_layout(pad=0.6)
    plt.savefig(out, bbox_inches="tight")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
