"""Runner for the monitoring side of the keep feature.

The monitor checks a finished trace against the same automaton the planner used. A simulation is
slow and noisy, so these cases take the trace straight from the ASP plan instead: a plan is by
construction a positive trace, which makes it a reliable starting point. Each case then perturbs
that trace so the keep is broken, and the monitor has to reject it. Without the perturbation a
passing monitor might simply be accepting everything.

Verdicts come from the boolean ring, where False means satisfied.

Run with:
    source venv/bin/activate
    python tests/run_monitor_tests.py
    python tests/run_monitor_tests.py keep_scenario_scope.osc
"""

import copy
import os
import sys
import tempfile
import warnings
from dataclasses import dataclass
from typing import Callable, List, Optional

from plan_checks import CONTROLLER_LP, HERE, IMAX, ROOT, Planner, states

# The two syma packages are vendored and are not installed into the venv, so they are put on the
# path here the same way the makefile does it. Keeps this runner usable like the others.
for vendored in ("monitoring/syma", "monitoring/syma-arv"):
    path = os.path.join(ROOT, vendored)
    if path not in sys.path:
        sys.path.insert(0, path)

from monitoring.Monitor import Monitor, with_previous
from syma_arv.monitor.boolean import BooleanMonitor


def valuations_from_plan(model):
    """The plan as a list of monitor valuations, one per time step."""
    rows = {}
    for actor, t, segment, lane, v_lon, _v_lat in states(model):
        row = rows.setdefault(t, {})
        row[f"l({actor})"] = lane
        row[f"p({actor})"] = segment
        row[f"v({actor})"] = v_lon
    return with_previous([rows[t] for t in sorted(rows)])


def stretch(trace, factor=3):
    """Repeat every step, the way a simulation samples a plan several times per second.

    The planner may satisfy two goals at the same step, but the automaton takes at most one
    transition per step, so a plan trace at one step per second can be too short to walk the
    automaton to its end. A simulated trace samples far more often and does not have that
    problem. See docs/keep-spec.md.
    """
    plain = [{k: v for k, v in row.items() if "_prev(" not in k} for row in trace]
    return with_previous([row for row in plain for _ in range(factor)])


def verdict(spec_path, trace):
    """True when the monitor accepts the trace.

    Every ring is a cost algebra: zero means satisfied. The boolean ring says False, but a guard
    that is just True evaluates to the integer 0 (AbstractEvaluator.visitTrue), and MinMax gives
    0.0, so the test is falsiness rather than a particular zero.
    """
    mon = Monitor.from_osc2_file(spec_path, ring=BooleanMonitor)
    mon.initialize()
    for row in trace:
        mon.update(row)
    final = [loc for loc in mon.syma_aut.locations if loc.final]
    assert len(final) == 1, f"expected one final location, got {final}"
    return not mon.state[final[0]]


# ---------------------------------------------------------------- perturbations
#
# Each takes a trace and returns a broken copy. The prev variables are rebuilt afterwards, so a
# stability keep sees the change the same way it would in a real trace.

def _rebuild(trace):
    plain = [{k: v for k, v in row.items() if "_prev(" not in k} for row in trace]
    return with_previous(plain)


def set_at(variable, step, value):
    def perturb(trace):
        out = copy.deepcopy(trace)
        index = step if step >= 0 else len(out) + step
        out[index][variable] = value
        return _rebuild(out)

    perturb.description = f"{variable} := {value} at step {step}"
    return perturb


def bump_at(variable, step, delta):
    def perturb(trace):
        out = copy.deepcopy(trace)
        index = step if step >= 0 else len(out) + step
        out[index][variable] = out[index][variable] + delta
        return _rebuild(out)

    perturb.description = f"{variable} shifted by {delta} at step {step}"
    return perturb


@dataclass
class Case:
    spec: str
    note: str
    # Breaks the keep. The monitor must reject the result. None means the trace is only checked
    # as a positive one.
    perturbation: Optional[Callable] = None
    # A perturbation the monitor must still accept, for instance drift below the tolerance.
    tolerated: Optional[Callable] = None
    imax: int = IMAX


CASES: List[Case] = [
    Case(
        "keep_scenario_scope.osc",
        "lane keep over the whole scenario",
        perturbation=set_at("l(car1)", 1, 3),
    ),
    Case(
        "keep_adjacent_phases.osc",
        "the first keep must already hold on the step its phase is entered",
        perturbation=set_at("l(car1)", 0, 2),
    ),
    Case(
        "keep_lane_modifier.osc",
        "keep_lane(), a lane change anywhere inside the invocation breaks it",
        perturbation=set_at("l(car1)", 1, 3),
    ),
    Case(
        "speed_overtake_keep.osc",
        "speed(5mps, at: all) over the whole scenario. This is an exact equality, so any drift "
        "breaks it. Only keep_speed() has a tolerance",
        perturbation=bump_at("v(car1)", 3, 2.0),
        imax=14,
    ),
    Case(
        "keep_speed_modifier.osc",
        "keep_speed() on one phase. Only checked as positive: nothing stops the monitor from "
        "ending that phase early, since it does not know the spec's duration",
    ),
    Case(
        "keep_relational_distance.osc",
        "relational keep on the gap between two cars",
        perturbation=set_at("p(ego)", 1, -500),
    ),
    Case(
        "speed_start_end.osc",
        "a spec without any keep still accepts its own plan",
    ),
]


def run_case(case: Case):
    spec_path = os.path.join(HERE, case.spec)
    if not os.path.exists(spec_path):
        return False, f"spec file missing: {spec_path}"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        planner = Planner(spec_path, out_path=tempfile.mkdtemp(prefix="monitor_"))
        plans = planner.plans(n=1, external_rules=[CONTROLLER_LP], visualize=False,
                              imax=case.imax)
    if not plans:
        return False, "the planner found no plan, so there is no trace to monitor"

    trace = stretch(valuations_from_plan(plans[0]))
    details = [f"{len(trace)} steps"]

    if not verdict(spec_path, trace):
        return False, f"the monitor rejects the plan's own trace ({len(trace)} steps)"
    details.append("plan trace accepted")

    if case.perturbation is not None:
        if verdict(spec_path, case.perturbation(trace)):
            return False, f"the monitor accepts a broken trace: {case.perturbation.description}"
        details.append(f"rejects {case.perturbation.description}")

    if case.tolerated is not None:
        if not verdict(spec_path, case.tolerated(trace)):
            return False, f"the monitor rejects tolerated drift: {case.tolerated.description}"
        details.append(f"accepts {case.tolerated.description}")

    return True, ", ".join(details)


def main(argv):
    only = argv[1:] if len(argv) > 1 else None
    cases = [c for c in CASES if not only or c.spec in only
             or c.spec.removesuffix(".osc") in only]
    if not cases:
        print(f"No cases matched {only}. Known specs: {[c.spec for c in CASES]}")
        return 2

    print(f"Running {len(cases)} cases\n")
    failed = 0
    for case in cases:
        try:
            ok, detail = run_case(case)
        except Exception as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        failed += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {case.spec}")
        print(f"       {case.note}")
        print(f"       {detail}\n")

    print(f"{len(cases) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
