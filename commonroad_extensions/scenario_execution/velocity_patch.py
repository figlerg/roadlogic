"""Aim the motion planner at the speed the plan asked for, waypoint by waypoint.

The stock velocity planner in Frenetix was written for a planning problem with a single goal. It
reads `goal.state_list[0]` and nothing else, so with our multi-goal problems it keeps aiming at the
first waypoint for the whole run. Once the car is past it the distance goes negative, the remaining
time runs out, and the desired velocity falls back to whatever the car is doing already. That is
why a simulated car overshoots a planned speed by several mps.

This patch replaces `calculate_desired_velocity` with one that

  1. picks the goal state the car is currently heading for, by time step,
  2. aims at the speed needed to cover the remaining distance in the remaining time,
  3. clamps that into the velocity window the plan put on that waypoint, when there is one,
  4. falls back to the original method whenever it cannot do the above.

The stock clipping against the current velocity is kept, so the target still moves smoothly.

Reversing it: set ROADLOGIC_VELOCITY_PATCH=0, or drop the apply_velocity_patch() call in
stitched_execution.py. Nothing in Frenetix itself is edited.
"""

import os

from cr_scenario_handler.utils.velocity_planner import VelocityPlanner

ENABLED = os.environ.get("ROADLOGIC_VELOCITY_PATCH", "1") != "0"

# How the waypoint's speed window is used. "clamp" forces the target into it. "average" ignores it
# and aims only at the speed needed to reach the waypoint on time. The window comes from the plan's
# speed at the waypoint, which in dynamics.lp is the speed the car leaves that step with, not the one
# it arrives with, so for a jerky plan it can point the wrong way. See tests/demo.ipynb, section 8.
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
