"""Tables comparing the HSCC paper's benchmark with the current code, from the output of
run_benchmark.py. Writes paper_journal/benchmark/results.md and prints it.

The paper's numbers are read from experiments_src/<exp>/out, which this script never writes to.
A control column judges the paper's own stored traces with the current monitor, so a change in
verdicts can be told apart from a change in planning or simulation.

    python paper_journal/benchmark/report.py
"""
import collections
import glob
import json
import os
import sys
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out")
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "monitoring", "syma"), os.path.join(ROOT, "monitoring", "syma-arv")]

from run_benchmark import CONFIGS, INCONSISTENT, NEW, PAPER_VANILLA, PAPER_VARIABILITY  # noqa: E402


def load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def paper_planning_seconds(exp):
    total = 0
    for line in open(os.path.join(ROOT, "experiments_src", exp, "out", "times.jsonl")):
        step = json.loads(line)
        if step["step"] in ("generate-osc-scenarios", "variability_experiments"):
            total += step["seconds"]
    return total


def planning_status(summary_path, vanilla_runs=None):
    """(planned, no plan, timed out) from a variability summary.json, or the run count for vanilla."""
    if vanilla_runs is not None:
        return vanilla_runs, 0, 0
    report = load(summary_path, {})
    counts = collections.Counter(v.get("status") if isinstance(v, dict) else str(v) for v in report.values())
    return counts["SAT"], counts["NoModelException"], counts["TimeoutError"]


def verdicts(summary_log):
    log = load(summary_log)
    if not log:
        return None
    return log["num_positive_traces"], log["successful_runs"], log["total_runs"]


def control(exp):
    """Positive traces when the paper's own stored traces are judged by the current monitor."""
    from monitoring.Monitor import Monitor, valuations_sanity_check
    spec = os.path.join(ROOT, "experiments_src", exp, "in", "spec.osc")
    positive = checked = 0
    for folder in sorted(glob.glob(os.path.join(ROOT, "experiments_src", exp, "out", "cr_simulations", "scenario_*"))):
        if not os.path.exists(os.path.join(folder, "LANE.csv")):
            continue
        mon = Monitor.from_osc2_file(spec)
        trace = mon.read_valuations(os.path.join(folder, "LANE.csv"), os.path.join(folder, "LONGPOS.csv"),
                                    os.path.join(folder, "CURRV.csv"))
        cut = valuations_sanity_check(trace)
        trace = trace[:cut] if cut else trace
        try:
            mon.initialize()
            for row in trace:
                mon.update(row)
        except KeyError:
            continue
        checked += 1
        final = [loc for loc in mon.syma_aut.locations if loc.final][0]
        positive += not mon.state[final]
    return positive, checked


def cell(v):
    return "not run" if v is None else f"{v[0]}/{v[1]}"


def paper_table():
    rows = ["| experiment | planning s, paper | planning s, now | planned / no plan / timeout, paper | same, now "
            "| positive, paper | paper traces, current monitor | positive, now | positive, speedfix |",
            "|---|---:|---:|---|---|---|---|---|---|"]
    for exp in PAPER_VANILLA + PAPER_VARIABILITY:
        paper_out = os.path.join(ROOT, "experiments_src", exp, "out")
        now_out = os.path.join(OUT, exp)
        times = load(os.path.join(now_out, "times.json"), {})
        vanilla = exp in PAPER_VANILLA
        paper_status = planning_status(os.path.join(paper_out, "summary.json"), 10 if vanilla else None)
        now_runs = len(glob.glob(os.path.join(now_out, "cr_scenarios", "*.xml")))
        now_status = planning_status(os.path.join(now_out, "summary.json"), now_runs if vanilla else None) \
            if times else None
        paper_v = verdicts(os.path.join(paper_out, "cr_simulations", "summary_log.json"))
        rows.append("| " + " | ".join([
            exp, str(paper_planning_seconds(exp)), str(times.get("plan", "not run")),
            " / ".join(map(str, paper_status)), " / ".join(map(str, now_status)) if now_status else "not run",
            cell(paper_v), cell(control(exp)),
            cell(verdicts(os.path.join(now_out, "sim_now", "summary_log.json"))),
            cell(verdicts(os.path.join(now_out, "sim_speedfix", "summary_log.json"))),
        ]) + " |")
    return rows


def new_table():
    rows = ["| example | what it shows | planning s | plans | positive, now | positive, speedfix |",
            "|---|---|---:|---:|---|---|"]
    for name, what in NEW.items():
        out = os.path.join(OUT, name)
        times = load(os.path.join(out, "times.json"), {})
        rows.append("| " + " | ".join([
            f"`{name}`", what, str(times.get("plan", "not run")),
            str(len(glob.glob(os.path.join(out, "cr_scenarios", "*.xml")))) if times else "not run",
            cell(verdicts(os.path.join(out, "sim_now", "summary_log.json"))),
            cell(verdicts(os.path.join(out, "sim_speedfix", "summary_log.json"))),
        ]) + " |")
    return rows


def inconsistent_table():
    rows = ["| example | the contradiction | result | seconds |", "|---|---|---|---:|"]
    for name, what in INCONSISTENT.items():
        times = load(os.path.join(OUT, name, "times.json"), {})
        rows.append(f"| `{name}` | {what} | {times.get('outcome', 'not run')} | {times.get('plan', '')} |")
    return rows


def main():
    warnings.simplefilter("ignore")
    lines = ["# Benchmark: the HSCC paper against the current code", "",
             "Generated by `python paper_journal/benchmark/report.py` from the output of `run_benchmark.py`.",
             "`a/b` means a positive traces out of b runs that produced a monitoring result.", "",
             "## The paper's benchmark", ""] + paper_table() + [
             "", "## New examples, N=10 each", ""] + new_table() + [
             "", "## Inconsistent specifications, planning only", ""] + inconsistent_table()
    text = "\n".join(lines) + "\n"
    with open(os.path.join(HERE, "results.md"), "w") as f:
        f.write(text)
    print(text)


if __name__ == "__main__":
    main()
