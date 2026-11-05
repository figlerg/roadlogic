"""Waypoints a simulated car skipped because it could not satisfy them.

With ROADLOGIC_FINAL_SLACK on, a car that drives past a waypoint without reaching it, too early, too
late or outside its speed window, moves on to the next one instead of leaving the simulation. The
macro agent logs each such waypoint in missed_waypoints.csv in the simulation folder. A trace can
still satisfy the specification then, but it did not follow the plan, and the summaries count it
apart: positive, and of those, deviated from the plan.
"""
import csv
import glob
import os


def missed_waypoints(scenario_folder):
    """The skipped waypoints of one simulated scenario, as a list of dicts, empty if none."""
    from commonroad_extensions.plan_execution.id_hash import decode

    rows = []
    for path in sorted(glob.glob(os.path.join(scenario_folder, "simulation_*", "missed_waypoints.csv"))):
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                row["car"] = decode(int(row["agent_id"]))
                rows.append(row)
    return rows


def deviation_note(scenario_folder):
    """'' when the cars followed the plan, otherwise one line naming each skipped waypoint."""
    rows = missed_waypoints(scenario_folder)
    if not rows:
        return ""
    return "plan not followed: " + "; ".join(f"{r['car']} waypoint {r['waypoint']} ({r['reason']})" for r in rows)
