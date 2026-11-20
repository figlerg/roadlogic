"""The HSCC paper's benchmark figures (Fig. 5 and Fig. 8), drawn three times with the same plot code:
from the paper's runs, from the benchmark rerun on the current code with the paper's settings, and
from the rerun with the current defaults.

    python paper_journal/plots/compare_paper_figures.py

Reads experiments_src/<exp>/out/ (the paper, only read) and paper_journal/benchmark/out/<exp>/ (the
rerun, run_benchmark.py). Stages each source in the input format of vis_success_rates.py, a summary
log per experiment and a times.jsonl per experiment, under paper_journal/plots/compare/<source>/, and
writes the figures there as PDF and PNG.

The planning times compare directly, the paper and the rerun ran on the same machine. The rerun ran 3
experiments at a time with 3 simulations each, the paper one simulation at a time, so the execution,
instrumentation and monitoring times are not comparable. The rerun reuses the paper's sampled
instances for the variability experiments, so it has no sampling step.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PAPER = os.path.join(ROOT, "experiments_src")
RERUN = os.path.join(ROOT, "paper_journal", "benchmark", "out")
OUT = os.path.join(HERE, "compare")
EXPS = [f"exp_00{i}" for i in range(1, 8)] + [f"exp_00{i}_b" for i in range(1, 8)]
STEPS = {"simulate": "execute-all-scenarios", "metrics": "compute-metrics", "monitor": "generate-summary"}


def stage_paper(folder):
    for exp in EXPS:
        src = os.path.join(PAPER, exp, "out")
        if os.path.exists(os.path.join(src, "cr_simulations", "summary_log.json")):
            shutil.copy(os.path.join(src, "cr_simulations", "summary_log.json"), os.path.join(folder, "logs", f"{exp}.json"))
            os.makedirs(os.path.join(folder, "times", exp, "out"), exist_ok=True)
            shutil.copy(os.path.join(src, "times.jsonl"), os.path.join(folder, "times", exp, "out", "times.jsonl"))


def stage_rerun(folder, config):
    for exp in EXPS:
        out = os.path.join(RERUN, exp)
        summary = os.path.join(out, f"sim_{config}", "summary_log.json")
        times_file = os.path.join(out, "times.json")
        if not (os.path.exists(summary) and os.path.exists(times_file)):
            continue
        shutil.copy(summary, os.path.join(folder, "logs", f"{exp}.json"))
        times = json.load(open(times_file))
        plan_step = "variability_experiments" if exp.endswith("_b") else "generate-osc-scenarios"
        rows = [{"step": plan_step, "seconds": times["plan"]}]
        rows += [{"step": step, "seconds": times[f"{config}_{key}"]} for key, step in STEPS.items()
                 if f"{config}_{key}" in times]
        os.makedirs(os.path.join(folder, "times", exp, "out"), exist_ok=True)
        with open(os.path.join(folder, "times", exp, "out", "times.jsonl"), "w") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))


def total_seconds(folder, pattern):
    """The longest total time of one experiment in a staged source, for a common time axis."""
    import glob
    totals = [sum(json.loads(l)["seconds"] for l in open(f) if json.loads(l)["step"] != "compute similarity")
              for f in glob.glob(os.path.join(folder, "times", pattern, "out", "times.jsonl"))]
    return max(totals, default=0)


def draw(folder, split_deviated, time_ymax):
    script = os.path.join(HERE, "vis_success_rates.py")
    logs = os.path.join(folder, "logs")
    figures = [("vanilla_combined", "exp_00[0-9].json", "combined"),
               ("fig8_variability_combined_outcome", "exp_*_b.json", "combined_outcome")]
    for name, pattern, mode in figures:
        pdf = os.path.join(folder, f"{name}.pdf")
        pattern_dir = "exp_00?_b" if "_b" in pattern else "exp_00?"
        cmd = [sys.executable, script, "--pattern", os.path.join(logs, pattern), "--mode", mode,
               "--times-root", os.path.join(folder, "times"), "--out", pdf, "--width", "5.5",
               "--time-ymax", str(time_ymax[pattern_dir])]
        if split_deviated:
            cmd.append("--split-deviated")
        subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
        # the PNG for viewing, rendered from the PDF at a readable resolution
        subprocess.run(["pdftoppm", "-png", "-r", "220", "-singlefile", pdf, pdf[:-4]], check=True)


def main():
    sources = [("paper", None), ("rerun_paper_settings", "paper"), ("rerun_defaults", "default")]
    for name, config in sources:
        folder = os.path.join(OUT, name)
        shutil.rmtree(folder, ignore_errors=True)
        os.makedirs(os.path.join(folder, "logs"))
        stage_paper(folder) if config is None else stage_rerun(folder, config)
    # the same time axis in all three versions of a figure
    time_ymax = {p: max(total_seconds(os.path.join(OUT, name), p) for name, _ in sources) for p in ("exp_00?", "exp_00?_b")}
    for name, config in sources:
        draw(os.path.join(OUT, name), split_deviated=config == "default", time_ymax=time_ymax)
        print("wrote", os.path.join(OUT, name))


if __name__ == "__main__":
    main()
