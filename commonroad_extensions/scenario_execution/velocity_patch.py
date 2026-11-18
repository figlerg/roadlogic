"""Keep a simulated car at the speed the plan asked for, waypoint by waypoint.

Each car gets its goals one at a time (macro_agent_simulation.MacroAgent). Frenetix's velocity planner
aims at the speed that reaches the current goal on time, distance left over time left, and never reads
the speed window a goal can carry. A simulated car starts from rest and runs late, so it speeds up to
catch up, past the speed the specification asks for.

This patch replaces `calculate_desired_velocity` with one that

  1. picks the goal state the car is currently heading for, by time step,
  2. aims at the speed needed to cover the remaining distance in the remaining time, as Frenetix does,
  3. clamps that into the velocity window of that goal, when it has one,
  4. falls back to the original method whenever it cannot do the above.

Without a window it behaves as Frenetix as shipped (identical traces). The windows are built in
map_plan.py, only for cars whose speed the specification constrains. The stock clipping against the
current velocity is kept, so the target still moves smoothly.

Reversing it: set ROADLOGIC_VELOCITY_PATCH=0, or drop the apply_velocity_patch() call in
stitched_execution.py. Nothing in Frenetix itself is edited.
"""

import os

from cr_scenario_handler.utils.velocity_planner import VelocityPlanner

# On by default, together with the speed windows of map_plan.py (SOURCE=range, SCOPE=constrained),
# see tests/demo.ipynb section 8. 0 gives Frenetix as shipped, as in the HSCC paper.
ENABLED = os.environ.get("ROADLOGIC_VELOCITY_PATCH", "1") != "0"

# How the waypoint's speed window is used. "clamp" forces the target into it. "average" ignores it
# and aims only at the speed needed to reach the waypoint on time. The window is built in map_plan.py,
# see GOAL_VELOCITY_SOURCE there and tests/demo.ipynb, section 8.
MODE = os.environ.get("ROADLOGIC_VELOCITY_PATCH_MODE", "clamp")

_ATTRIBUTE = "_roadlogic_original_calculate_desired_velocity"


def current_goal_state(planning_problem, time_step):
    """The goal state the agent is heading for at this time step, or None."""
    states = getattr(planning_problem.goal, "state_list", None)
    if not states:
        return None
    for state in states:
        interval = getattr(state, "time_step", None)
        if interval is not None and time_step <= interval.end:
            return state
    return states[-1]


def velocity_bounds(goal_state):
    """(low, high) of a goal state's velocity window, or None when it carries no velocity."""
    interval = getattr(goal_state, "velocity", None)
    if interval is None:
        return None
    start, end = getattr(interval, "start", None), getattr(interval, "end", None)
    if start is None or end is None:
        # a plain number rather than an interval
        try:
            value = float(interval)
        except (TypeError, ValueError):
            return None
        return value, value
    return min(start, end), max(start, end)


def calculate_desired_velocity(self, x_0, s_position) -> float:
    """Aim for the current waypoint, inside the speed window the plan asked for."""
    goal_state = current_goal_state(self.planning_problem, x_0.time_step)
    if goal_state is None:
        return getattr(self, _ATTRIBUTE)(x_0, s_position)

    bounds = velocity_bounds(goal_state)

    target = None
    position = getattr(goal_state, "position", None)
    center = getattr(position, "center", None) if position is not None else None
    interval = getattr(goal_state, "time_step", None)
    if center is not None and interval is not None:
        goal_s = self._calculate_goal_s_position([center])
        # aim at the middle of the arrival window, as the original does
        remaining_steps = (interval.start + interval.end) / 2 - x_0.time_step
        remaining_time = remaining_steps * self.DT
        if goal_s is not None and remaining_time > 0:
            target = (goal_s - s_position) / remaining_time

    if target is None:
        # nothing to aim at, for instance past the last waypoint
        if bounds is None:
            return getattr(self, _ATTRIBUTE)(x_0, s_position)
        target = sum(bounds) / 2

    if bounds is not None and MODE == "clamp":
        target = min(max(target, bounds[0]), bounds[1])

    return self.clip_velocity(target, x_0.velocity)


def apply_velocity_patch():
    """Install the patch once. Does nothing when ROADLOGIC_VELOCITY_PATCH=0."""
    if not ENABLED or hasattr(VelocityPlanner, _ATTRIBUTE):
        return False
    setattr(VelocityPlanner, _ATTRIBUTE, VelocityPlanner.calculate_desired_velocity)
    VelocityPlanner.calculate_desired_velocity = calculate_desired_velocity
    return True
