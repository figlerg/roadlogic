"""Shared plan accessors, invariant checkers and the case-runner harness.

Used by tests/run_keep_tests.py and tests/run_speed_tests.py. Both drive specs through the
planner and then assert directly on the resulting ASP plans, so everything here works on a
MyModel: holds(state(V, loc(S,L), dyn(Vel_lon, Vel_lat)), T).

Checks return None when the property holds, or a string describing the first violation.
"""

import os
import shutil
import tempfile
import traceback
import warnings
from dataclasses import dataclass
from typing import Callable, List, Optional

from planning.Planner import Planner

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# All three copies of controller.lp in the repo are byte identical, so the choice is
# arbitrary. This is the one create_scenarios/create_plan_scenarios.py loads.
CONTROLLER_LP = os.path.join(ROOT, "create_scenarios", "controller.lp")

N_PLANS = 3
IMAX = 12

# No unit conversion anywhere. The encoding is integer valued: segments are metres, steps are
# seconds, longitudinal velocity is metres per second. Specs are written in m, s and mps only,
# and TranslationGraphVisitor.SUPPORTED_UNITS rejects anything else. So a literal in a spec is
# the number that appears in the plan, and these checks compare against it directly.

# ---------------------------------------------------------------- plan accessors

def states(model):
    """Yield (actor, time, segment, lane, v_lon, v_lat) for every holds/state atom."""
    for pred in model.holds:
        if pred.arguments[0].name != "state":
            continue
        yield (
            str(pred.actor),
            pred.time,
            pred.loc[0],
            pred.loc[1],
            pred.dyn[0],
            pred.dyn[1],
        )


def lanes_of(model, actor):
    """Lane per time step for one actor, ordered by time."""
    rows = [(t, lane) for a, t, _s, lane, _vl, _vt in states(model) if a == actor]
    return [lane for _t, lane in sorted(rows)]


def speeds_of(model, actor):
    """Longitudinal velocity per time step for one actor, ordered by time."""
    rows = [(t, v_lon) for a, t, _s, _l, v_lon, _vt in states(model) if a == actor]
    return [v for _t, v in sorted(rows)]


# ---------------------------------------------------------------- invariant checks
#
# Each check takes one plan and returns None if the invariant holds, or a string
# explaining the first violation.

def lane_equals(actor, value):
    def check(model):
        seq = lanes_of(model, actor)
        if not seq:
            return f"no states for actor {actor}"
        bad = [(t, lane) for t, lane in enumerate(seq) if lane != value]
        if bad:
            return f"{actor}.lane != {value} at {bad[:5]}, full trace {seq}"
        return None

    check.description = f"{actor}.lane == {value} at every step"
    return check


def lane_constant(actor):
    def check(model):
        seq = lanes_of(model, actor)
        if not seq:
            return f"no states for actor {actor}"
        if len(set(seq)) != 1:
            return f"{actor}.lane is not constant, trace {seq}"
        return None

    check.description = f"{actor}.lane is constant, value free"
    return check


def lane_not_constant(actor):
    """Weak discriminator for phase-scoped keeps.

    A phase-scoped invariant must NOT pin the lane for the whole trace, otherwise the
    scoping is being ignored and everything is treated as scenario scope. This says
    nothing about the phase window itself, which needs phase boundaries in the plan.
    Tighten once the encoding exposes them.
    """

    def check(model):
        seq = lanes_of(model, actor)
        if not seq:
            return f"no states for actor {actor}"
        if len(set(seq)) == 1:
            return (
                f"{actor}.lane is constant over the whole trace {seq}, "
                "so the phase scope was widened to scenario scope"
            )
        return None

    check.description = f"{actor}.lane varies outside the constrained phase"
    return check


def speed_between(actor, low, high):
    def check(model):
        seq = speeds_of(model, actor)
        if not seq:
            return f"no states for actor {actor}"
        bad = [(t, v) for t, v in enumerate(seq) if not low <= v <= high]
        if bad:
            return f"{actor}.speed outside [{low}, {high}] at {bad[:5]}, full trace {seq}"
        return None

    check.description = f"{actor}.speed in [{low}, {high}] at every step"
    return check


def speed_above(actor, low):
    def check(model):
        seq = speeds_of(model, actor)
        if not seq:
            return f"no states for actor {actor}"
        bad = [(t, v) for t, v in enumerate(seq) if v <= low]
        if bad:
            return f"{actor}.speed <= {low} at {bad[:5]}, full trace {seq}"
        return None

    check.description = f"{actor}.speed > {low} at every step"
    return check


def gap_between(follower, leader, low, high):
    """Longitudinal gap leader - follower stays within [low, high] at every step.

    Bounds are in ASP segments, which docs/method.md:83 says are meters.
    """
    def check(model):
        rows = {}
        for a, t, seg, _l, _vl, _vt in states(model):
            rows.setdefault(a, {})[t] = seg
        if follower not in rows or leader not in rows:
            missing = [a for a in (follower, leader) if a not in rows]
            return f"no states for actor(s) {missing}"
        bad = []
        for t in sorted(set(rows[follower]) & set(rows[leader])):
            gap = rows[leader][t] - rows[follower][t]
            if not low <= gap <= high:
                bad.append((t, gap))
        if bad:
            return f"gap {leader} - {follower} outside [{low}, {high}] at {bad[:5]}"
        return None

    check.description = f"{leader} - {follower} gap in [{low}, {high}] at every step"
    return check


def all_of(*checks):
    def check(model):
        for c in checks:
            msg = c(model)
            if msg is not None:
                return msg
        return None

    check.description = " and ".join(c.description for c in checks)
    return check

def speed_equals(actor, value):
    def check(model):
        seq = speeds_of(model, actor)
        if not seq:
            return f"no states for actor {actor}"
        bad = [(t, v) for t, v in enumerate(seq) if v != value]
        if bad:
            return f"{actor}.speed != {value} at {bad[:5]}, full trace {seq}"
        return None

    check.description = f"{actor}.speed == {value} at every step"
    return check


def speed_constant(actor):
    def check(model):
        seq = speeds_of(model, actor)
        if not seq:
            return f"no states for actor {actor}"
        if len(set(seq)) != 1:
            return f"{actor}.speed is not constant, trace {seq}"
        return None

    check.description = f"{actor}.speed is constant, value free"
    return check


def goal_witnesses(model):
    """Goal-time tuples from the plan, one per goal/n atom.

    A plan carries goal(T1,...,Tn-1,t): the times at which the successive phase goals are
    met, plus the horizon. Several witnesses can hold for one trace, which is why the goal
    assertion in the instance uses wildcards. Returns a list of (T1,...,Tn-1) tuples with the
    trailing horizon dropped.
    """
    return [tuple(pred.arguments[:-1]) for pred in model.goal]


def speed_at_start(actor, value):
    def check(model):
        seq = speeds_of(model, actor)
        if not seq:
            return f"no states for actor {actor}"
        if seq[0] != value:
            return f"{actor}.speed at start is {seq[0]}, expected {value}, full trace {seq}"
        return None

    check.description = f"{actor}.speed == {value} at t=0"
    return check


def at_goal(goal_index, per_step, description):
    """Lift a per-step predicate to a phase goal time.

    An `at: end` modifier is a point constraint at a phase goal, not at the last step of the
    plan: the goal rule requires t > T_last + 1, so the trace deliberately runs past it. The
    goal time therefore has to be read out of the plan rather than assumed.

    `per_step(model, t)` returns None if the property holds at step t, else a message. The
    result holds if any witness satisfies it at its goal time, which is the existential reading
    of the goal assertion.
    """
    def check(model):
        witnesses = goal_witnesses(model)
        if not witnesses:
            return "plan carries no goal atom, cannot locate the goal time"

        seen = []
        for w in witnesses:
            if goal_index > len(w):
                return f"plan has {len(w)} goal times, asked for T{goal_index}"
            t = w[goal_index - 1]
            msg = per_step(model, t)
            if msg is None:
                return None
            seen.append(f"T{goal_index}={t}: {msg}")
        return f"no witness satisfies it. " + "; ".join(seen)

    check.description = f"{description} at goal T{goal_index}"
    return check


def speed_at_goal(actor, goal_index, value):
    def per_step(model, t):
        seq = speeds_of(model, actor)
        if not seq:
            return f"no states for actor {actor}"
        if t >= len(seq):
            return f"goal time {t} is past the trace {seq}"
        if seq[t] != value:
            return f"{actor}.speed is {seq[t]}, expected {value}, full trace {seq}"
        return None

    return at_goal(goal_index, per_step, f"{actor}.speed == {value}")


def faster_at_goal(fast, slow, goal_index):
    def per_step(model, t):
        a, b = speeds_of(model, fast), speeds_of(model, slow)
        if not a or not b:
            missing = [x for x, seq in ((fast, a), (slow, b)) if not seq]
            return f"no states for actor(s) {missing}"
        if t >= len(a) or t >= len(b):
            return f"goal time {t} is past a trace"
        if a[t] <= b[t]:
            return f"{fast} is {a[t]}, {slow} is {b[t]}, not faster"
        return None

    return at_goal(goal_index, per_step, f"{fast}.speed > {slow}.speed")


def speed_faster_than(fast, slow):
    def check(model):
        a, b = speeds_of(model, fast), speeds_of(model, slow)
        if not a or not b:
            missing = [x for x, s in ((fast, a), (slow, b)) if not s]
            return f"no states for actor(s) {missing}"
        bad = [(t, x, y) for t, (x, y) in enumerate(zip(a, b)) if x <= y]
        if bad:
            return f"{fast} not faster than {slow} at {bad[:5]}"
        return None

    check.description = f"{fast}.speed > {slow}.speed at every step"
    return check


# ---------------------------------------------------------------- case harness

PASS, FAIL, PENDING = "PASS", "FAIL", "PENDING"


@dataclass
class Case:
    spec: str
    note: str
    sat: bool = True
    invariant: Optional[Callable] = None


def run_case(case: Case, out_dir: str, spec_dir: str = HERE):
    """Plan one spec and check it. Returns (status, detail)."""
    spec_path = os.path.join(spec_dir, case.spec)
    if not os.path.exists(spec_path):
        return FAIL, f"spec file missing: {spec_path}"

    case_dir = os.path.join(out_dir, os.path.splitext(case.spec)[0])
    os.makedirs(case_dir, exist_ok=True)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            planner = Planner(spec_path, out_path=case_dir)
            plans = planner.plans(n=N_PLANS, external_rules=[CONTROLLER_LP],
                                  visualize=False, imax=IMAX)
    except NotImplementedError as exc:
        return PENDING, str(exc)
    except Exception:
        return FAIL, traceback.format_exc().strip()

    if not case.sat:
        if plans:
            return FAIL, f"expected no plan but got {len(plans)}, so the conflict went undetected"
        return PASS, "no plan, specification correctly rejected as inconsistent"

    if not plans:
        return FAIL, "expected at least one plan but the program was unsatisfiable"

    for i, plan in enumerate(plans):
        msg = case.invariant(plan)
        if msg is not None:
            return FAIL, f"plan {i + 1}/{len(plans)} violates the invariant: {msg}"

    return PASS, f"{len(plans)} plans, all satisfy {case.invariant.description}"


def run_cases(cases: List[Case], prefix: str, spec_dir: str = HERE):
    """Run a list of cases, print a board, return a process exit code."""
    out_dir = tempfile.mkdtemp(prefix=prefix)
    results = []

    print(f"Running {len(cases)} cases, artifacts in {out_dir}\n")
    for case in cases:
        status, detail = run_case(case, out_dir, spec_dir)
        results.append((status, case, detail))
        print(f"[{status:>7}] {case.spec}")
        print(f"          {case.note}")
        for line in detail.splitlines():
            print(f"          {line}")
        print()

    counts = {s: sum(1 for r, _c, _d in results if r == s) for s in (PASS, FAIL, PENDING)}
    print(f"{counts[PASS]} passed, {counts[FAIL]} failed, {counts[PENDING]} pending")

    if counts[FAIL] == 0:
        shutil.rmtree(out_dir, ignore_errors=True)
    else:
        print(f"Artifacts of the failing runs kept in {out_dir}")

    return 1 if counts[FAIL] else 0


# ---------------------------------------------------------------- verbose explanation

def _rule(title, char="="):
    return f"\n{char * 78}\n{title}\n{char * 78}"


def explain(spec_path, n=1, external_rules=None, imax=IMAX, show_source=True,
            show_graph=True, show_instance=True, show_plans=True, printer=print):
    """Walk one specification through the whole pipeline, printing every stage.

    Prints the OSC source, the translation graph with the constraints on each edge, the chosen
    path, the generated ASP instance, and the resulting plans as per-actor traces. Returns the
    list of plans so a notebook can poke at them further.

    Intended for eyeballing a single example, not for the test board. Raises whatever the
    pipeline raises, so an unimplemented feature shows up as its own error rather than being
    swallowed.
    """
    import networkx as nx

    spec_path = os.path.abspath(spec_path)
    out_dir = tempfile.mkdtemp(prefix="explain_")
    rules = external_rules if external_rules is not None else [CONTROLLER_LP]

    printer(_rule(f"SPECIFICATION  {os.path.relpath(spec_path, ROOT)}"))
    if show_source:
        printer(open(spec_path).read().rstrip())

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        planner = Planner(spec_path, out_path=out_dir)

    graph = planner.translation_graph
    if show_graph:
        printer(_rule("TRANSLATION GRAPH"))
        printer(f"actors : {[a.id for a in graph.actors]}")
        printer(f"nodes  : {list(graph.graph.nodes)}")
        path = next(nx.all_simple_paths(graph.graph, 'init', 'fin'))
        printer(f"path   : {' -> '.join(str(p) for p in path)}")
        printer("\nconstraints per edge along that path:")
        for i, (u, v) in enumerate(zip(path, path[1:])):
            gamma = graph.graph.edges[(u, v)]['object']
            role = "init rule" if i == 0 else f"goal{i}"
            printer(f"  [{i}] {u} -> {v}   ({role})")
            if not gamma:
                printer("        (none)")
            for con in sorted(gamma, key=str):
                printer(f"        {type(con).__name__:<20} {con}")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        plans = planner.plans(n=n, external_rules=rules, visualize=False, imax=imax)

    if show_instance:
        printer(_rule("GENERATED ASP INSTANCE  (instance.lp)"))
        printer(open(os.path.join(out_dir, "instance.lp")).read().rstrip())

    if show_plans:
        printer(_rule(f"PLANS  ({len(plans)} found)"))
        for k, model in enumerate(plans, 1):
            printer(_rule(f"plan {k} of {len(plans)}", "-"))
            witnesses = goal_witnesses(model)
            printer(f"goal times (T1..Tn-1) per witness: {witnesses if witnesses else 'none'}")
            rows = {}
            for actor, t, seg, lane, v_lon, v_lat in states(model):
                rows.setdefault(actor, {})[t] = (seg, lane, v_lon, v_lat)
            for actor in sorted(rows):
                steps = sorted(rows[actor])
                printer(f"\n  {actor}")
                printer("    t       " + " ".join(f"{t:>4}" for t in steps))
                printer("    segment " + " ".join(f"{rows[actor][t][0]:>4}" for t in steps))
                printer("    lane    " + " ".join(f"{rows[actor][t][1]:>4}" for t in steps))
                printer("    v_lon   " + " ".join(f"{rows[actor][t][2]:>4}" for t in steps))
                printer("    v_lat   " + " ".join(f"{rows[actor][t][3]:>4}" for t in steps))

    printer(f"\nartifacts in {out_dir}")
    return plans
