"""Runner for planning every path through the automaton.

A one_of branches the automaton, and a parallel gives one path per order in which its branches'
phases can end. The planner plans every path, in one of three modes (live, the default, spread, and
first, the paper's), see PATH_MODE in planning/Planner.py. These checks plan a few specs and look at
the plans together, which the single-spec cases in plan_checks.py cannot.

Run with:
    source venv/bin/activate
    python tests/run_path_tests.py
"""

import os
import sys
import tempfile
import time
import traceback
import warnings

from plan_checks import CONTROLLER_LP, HERE, IMAX, Planner, lanes_of, states


def plan(spec, n, **settings):
    """The plans for a spec, or [] when it has none."""
    from planning.asp.generate_plans import NoModelException

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        planner = Planner(os.path.join(HERE, spec), out_path=tempfile.mkdtemp(prefix="path_tests_"), **settings)
        try:
            return planner.plans(n=n, external_rules=[CONTROLLER_LP], visualize=False, imax=IMAX)
        except NoModelException:
            return []


def final_lanes(plans):
    return sorted({lanes_of(p, "car1")[-1] for p in plans})


# ---------------------------------------------------------------- checks, each returns None or a failure

def first_alternative_impossible():
    plans = plan("one_of_first_impossible.osc", n=2)
    if not plans:
        return "no plan, although the second alternative is possible"
    if final_lanes(plans) != [3]:
        return f"car1 should end in lane 3 through the second alternative, ends in {final_lanes(plans)}"


def first_path_only_misses_it():
    # the old behaviour, kept behind a switch to reproduce the paper
    plans = plan("one_of_first_impossible.osc", n=1, path_mode="first")
    if plans:
        return "in first mode only the first path is planned, which has no plan here"


def every_alternative_impossible():
    plans = plan("one_of_all_impossible.osc", n=1)
    if plans:
        return f"expected no plan, got {len(plans)}"


def both_alternatives_planned():
    for mode in ("live", "spread"):
        plans = plan("one_of_nested.osc", n=4, path_mode=mode)
        if final_lanes(plans) != [1, 3]:
            return f"{mode}: expected plans through both alternatives (car1 ending in lanes 1 and 3), got {final_lanes(plans)}"
        if any(not getattr(p, "path", None) for p in plans):
            return f"{mode}: every plan should record the path it was planned on"


def no_duplicate_plans():
    plans = plan("keep_phase_scope.osc", n=6)
    seen = [tuple(sorted(states(p))) for p in plans]
    if len(set(seen)) != len(seen):
        return f"{len(seen) - len(set(seen))} of {len(seen)} plans are duplicates"
    if len(plans) != 6:
        return f"asked for 6 plans, got {len(plans)}"


def duplicates_count_once():
    # two paths that yield the same plan: it must be taken once, the next plan taking its place
    from types import SimpleNamespace as Plan
    import planning.Planner as P
    same = ["holds(state(car1,loc(0,1),dyn(1,0)),0)"]
    fake = {0: [Plan(holds=same, name="a"), Plan(holds=["x"], name="b")],
            1: [Plan(holds=list(same), name="a again"), Plan(holds=["y"], name="c")]}

    def fake_path(self, paths, k, *rest):
        yield from fake[k]

    original = P.Planner._plans_on_path
    P.Planner._plans_on_path = fake_path
    try:
        names = [m.name for m in plan("one_of_nested.osc", n=3)]
    finally:
        P.Planner._plans_on_path = original
    if names != ["a", "c", "b"]:
        return f"expected a, c, b (the copy of a skipped, c taken in its place), got {names}"


def early_stop_returns_quickly():
    # 13 paths and a single plan: asking for 6 used to search every horizon on every path
    started = time.time()
    plans = plan("parallel_single_plan.osc", n=6)
    seconds = time.time() - started
    if len(plans) != 1:
        return f"expected the single plan, got {len(plans)}"
    if seconds > 30:
        return f"took {seconds:.0f} s, early stop should end the search for more plans at once"


CHECKS = [
    (first_alternative_impossible, "one_of whose first alternative is impossible still has plans"),
    (first_path_only_misses_it, "first mode keeps the paper's first-path behaviour"),
    (every_alternative_impossible, "one_of whose alternatives are all impossible has no plan"),
    (both_alternatives_planned, "live and spread both give plans from both alternatives of a one_of"),
    (no_duplicate_plans, "parallel interleavings do not yield the same plan twice"),
    (duplicates_count_once, "a plan found on two paths counts once, the next one takes its place"),
    (early_stop_returns_quickly, "asking for more plans than exist ends quickly with early stop"),
]


def main():
    failed = 0
    for check, note in CHECKS:
        try:
            msg = check()
        except Exception:
            msg = traceback.format_exc().strip()
        failed += msg is not None
        print(f"[{'PASS' if msg is None else 'FAIL':>4}] {check.__name__}\n       {note}")
        if msg:
            for line in msg.splitlines():
                print(f"       {line}")
    print(f"\n{len(CHECKS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
