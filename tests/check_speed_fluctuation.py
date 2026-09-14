"""How steady is the simulated speed, compared to what the plan asked for?

The plan is discrete: one step is one second and one segment is one metre, so a speed of 5mps
means the car covers 5 segments in a step. The simulation is continuous and samples every 0.1s,
and nothing in the planning problem pins the speed between waypoints: map_plan builds its goal
states with velocity=None. So the simulated speed is free to wander inside a second, which
matters for any keep on speed and for the tolerance of keep_speed().

This reports, per agent:
  dt                     the sampling interval of the trace
  max step change        the largest |v(t) - v(t-1)| between two samples
  worst spread           the largest max-min inside one second
  per-second average     the distance covered per second, which is what the plan constrains

Needs a simulated scenario folder holding CURRV.csv and LONGPOS.csv, which means CURRV has to be
among the computed metrics. Run the pipeline with:

    make ... selected_metrics="LANE LONGPOS CURRV" compute-selected-metrics-for-all-scenarios

Run with:
    python tests/check_speed_fluctuation.py <folder with scenario_* subfolders> [--max-step 0.5]
"""

import argparse
import csv
import os
import sys
from collections import defaultdict


def read_series(path, column):
    """{agent_id: [(time, value), ...]} from one metric CSV, ordered by time."""
    out = defaultdict(list)
    if not os.path.isfile(path):
        return out
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out[row["agent_id"]].append((float(row["time"]), float(row[column])))
    for rows in out.values():
        rows.sort()
    return out


def per_second_average_speed(positions):
    """Distance covered in each whole second, which is the plan's notion of speed."""
    by_second = {}
    for t, s in positions:
        second = int(round(t))
        if abs(t - second) < 1e-6:
            by_second[second] = s
    seconds = sorted(by_second)
    return [(seconds[i], by_second[seconds[i]] - by_second[seconds[i - 1]])
            for i in range(1, len(seconds))]


def report(folder, max_step, quiet=False):
    """Returns (findings, worst_step) for one simulated scenario folder."""
    speeds = read_series(os.path.join(folder, "CURRV.csv"), "velocity")
    positions = read_series(os.path.join(folder, "LONGPOS.csv"), "longitudinal_position")

    if not speeds:
        return [f"{os.path.basename(folder)}: no CURRV.csv, rerun the metrics with CURRV"], 0.0

    findings, worst_step = [], 0.0
    for agent, rows in sorted(speeds.items()):
        values = [v for _, v in rows]
        times = [t for t, _ in rows]
        dt = round(times[1] - times[0], 4) if len(times) > 1 else 0
        steps = [abs(values[i] - values[i - 1]) for i in range(1, len(values))]
        max_step_seen = max(steps) if steps else 0.0
        worst_step = max(worst_step, max_step_seen)

        within = defaultdict(list)
        for t, v in rows:
            within[int(t)].append(v)
        spreads = [max(vs) - min(vs) for vs in within.values() if len(vs) > 1]
        worst_spread = max(spreads) if spreads else 0.0

        averages = [d for _, d in per_second_average_speed(positions.get(agent, []))]

        if not quiet:
            print(f"  agent {agent}: dt={dt}s, {len(values)} samples, "
                  f"v in [{min(values):.2f}, {max(values):.2f}] mps")
            print(f"     largest change between samples : {max_step_seen:.3f} mps")
            print(f"     worst spread inside one second : {worst_spread:.3f} mps")
            if averages:
                print(f"     distance per second            : "
                      f"{[round(a, 2) for a in averages]}")

        if max_step_seen > max_step:
            findings.append(
                f"{os.path.basename(folder)} agent {agent}: speed changes by up to "
                f"{max_step_seen:.3f} mps between samples {dt}s apart, over the {max_step} mps "
                f"a stability keep tolerates"
            )
    return findings, worst_step


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", help="folder holding scenario_* subfolders, or one of them")
    ap.add_argument("--max-step", type=float, default=0.5,
                    help="tolerated change between two samples, default matches "
                         "Monitor.STABILITY_TOLERANCE")
    ap.add_argument("--quiet", action="store_true", help="only print findings")
    args = ap.parse_args(argv)

    scenarios = sorted(
        os.path.join(args.folder, d) for d in os.listdir(args.folder)
        if d.startswith("scenario_") and os.path.isdir(os.path.join(args.folder, d))
    ) or [args.folder]

    findings = []
    for scenario in scenarios:
        if not args.quiet:
            print(f"=== {os.path.basename(scenario)}")
        found, _ = report(scenario, args.max_step, quiet=args.quiet)
        findings += found

    print()
    if findings:
        print(f"{len(findings)} finding(s):")
        for f in findings:
            print(f"  {f}")
        print("\nA speed keep compares against the plan's speed, which is distance per second.\n"
              "The instantaneous speed is a different quantity and wanders between waypoints.")
        return 1
    print(f"Speed stays within {args.max_step} mps between samples in every trace.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
