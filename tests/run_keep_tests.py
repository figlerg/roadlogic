"""Runner for the keep-feature test specifications.

Pragmatic end-to-end check: parse each tests/keep*.osc, run the planner, and verify directly on
the resulting ASP plans that the declared invariant was honored. Negative specs must come back
with no plan at all, which is what an inconsistent specification looks like in our encoding
(7.6.1: the set of accepted traces is empty).

Nothing of the keep feature is implemented yet, so every case is expected to raise
NotImplementedError from TranslationGraphVisitor and report PENDING. That keeps this file useful
before, during and after the work.

Accessors, checkers and the case harness live in tests/plan_checks.py, shared with
tests/run_speed_tests.py.

Run with:
    source venv/bin/activate
    python tests/run_keep_tests.py                # all keep cases
    python tests/run_keep_tests.py keep.osc       # a subset
    python tests/run_keep_tests.py --self-test    # check the invariant checkers themselves
    python tests/run_keep_tests.py keep.osc -v    # walk one spec through the pipeline
"""

import os
import sys
import tempfile
import warnings

from typing import List

from plan_checks import (
    HERE,
    explain,
    CONTROLLER_LP,
    IMAX,
    ROOT,
    Case,
    Planner,
    gap_between,
    lane_constant,
    lane_equals,
    lane_not_constant,
    lanes_of,
    run_cases,
    speed_above,
    speed_between,
    speeds_of,
)


# ---------------------------------------------------------------- cases

# Bounds are in mps, which is what the .osc literals say and what the plan contains. No
# conversion, so these numbers must simply match the specs.
CASES: List[Case] = [
    Case(
        "keep.osc",
        "behavior-scoped keep, hardcoded lane",
        invariant=lane_equals("car1", 2),
    ),
    Case(
        "keep_scenario_scope.osc",
        "scenario-member keep holds for the whole scenario",
        invariant=lane_equals("car1", 2),
    ),
    Case(
        "keep_hard_qualifier.osc",
        "explicit hard qualifier behaves like the unqualified default",
        invariant=lane_equals("car1", 2),
    ),
    Case(
        "keep_phase_scope.osc",
        "keep on one phase of a serial only",
        invariant=lane_not_constant("car1"),
    ),
    Case(
        "keep_lane_free.osc",
        "constant lane via a free parameter, the desugared keep_lane",
        invariant=lane_constant("car1"),
    ),
    Case(
        "keep_lane_modifier.osc",
        "keep_lane() surface form, must match keep_lane_free.osc",
        invariant=lane_constant("car1"),
    ),
    Case(
        "keep_speed_range.osc",
        "range invariant on a physical quantity",
        invariant=speed_between("car1", 5, 10),
    ),
    Case(
        "keep_speed_comparison.osc",
        "single-sided comparison on a physical quantity",
        invariant=speed_above("car1", 3),
    ),
    Case(
        "keep_relational_distance.osc",
        "relational invariant via the domain model's space_gap method",
        invariant=gap_between("ego", "car1", 5, 100),
    ),
    Case(
        "keep_relational_modifier.osc",
        "same invariant via an at-less position modifier, must match the space_gap form",
        invariant=gap_between("ego", "car1", 5, 100),
    ),
    Case(
        "keep_inconsistent_direct.osc",
        "contradicting lane keeps on one actor, 7.6.2.3 case 1",
        sat=False,
    ),
    Case(
        "keep_inconsistent_speed.osc",
        "the standard's 7.6.2.3 example, written in mps since kph is not accepted",
        sat=False,
    ),
    Case(
        "keep_inconsistent_parallel.osc",
        "conflict only visible across parallel branches, the less obvious case",
        sat=False,
    ),
    Case(
        "keep_inconsistent_nonlocal.osc",
        "7.6.2.3 case 2, unsatisfiable only through interplay over time",
        sat=False,
    ),
]


# ---------------------------------------------------------------- checker self-test

# Every keep case is PENDING until the feature exists, so the checks above would otherwise
# never execute. This exercises them against a plan from an existing, unconstrained spec,
# where the expected verdicts are known from the trace itself.
SELF_TEST_SPEC = os.path.join(ROOT, "experiments_src", "exp_002_b", "in", "spec.osc")


def self_test():
    """Run every invariant checker against a real plan. Returns a process exit code."""
    import warnings

    out_dir = tempfile.mkdtemp(prefix="keep_selftest_")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        planner = Planner(SELF_TEST_SPEC, out_path=out_dir)
        plans = planner.plans(n=1, external_rules=[CONTROLLER_LP], visualize=False, imax=IMAX)

    if not plans:
        print(f"Self-test cannot run: {SELF_TEST_SPEC} produced no plan.")
        return 2

    model = plans[0]
    lanes = lanes_of(model, "car1")
    speeds = speeds_of(model, "car1")
    print(f"Reference plan from {os.path.relpath(SELF_TEST_SPEC, ROOT)}")
    print(f"  car1 lanes  {lanes}")
    print(f"  car1 speeds {speeds}")
    print(f"  ego  lanes  {lanes_of(model, 'ego')}\n")

    constant = len(set(lanes)) == 1
    lo, hi = min(speeds), max(speeds)

    # (label, checker, whether it should report the invariant as holding)
    probes = [
        ("lane_equals actual value", lane_equals("car1", lanes[0]), constant),
        ("lane_equals impossible value", lane_equals("car1", 99), False),
        ("lane_constant", lane_constant("car1"), constant),
        ("lane_not_constant", lane_not_constant("car1"), not constant),
        ("speed_above below minimum", speed_above("car1", lo - 1), True),
        ("speed_above above maximum", speed_above("car1", hi), False),
        ("speed_between full range", speed_between("car1", lo, hi), True),
        ("speed_between empty range", speed_between("car1", hi + 1, hi + 2), False),
        ("unknown actor", lane_equals("no_such_actor", 1), False),
    ]

    bad = 0
    for label, check, should_hold in probes:
        msg = check(model)
        holds = msg is None
        ok = holds == should_hold
        bad += not ok
        print(f"[{'ok ' if ok else 'BAD'}] {label:<30} {'holds' if holds else 'violation'}")
        if msg:
            print(f"      {msg}")

    print()
    if bad:
        print(f"{bad} checkers do not behave as expected, the keep suite cannot be trusted")
        return 1
    print("All invariant checkers behave correctly.")
    if not constant:
        print(f"car1 changes lane in the unconstrained baseline ({lanes}), so the lane keeps "
              "in the test corpus do constrain something real.")
    else:
        print(f"WARNING: car1 already holds a constant lane ({lanes}) without any keep, so the "
              "lane cases would pass trivially. Pick a different baseline or lane value.")
    return 0



# ---------------------------------------------------------------- driver

def main(argv):
    if "--self-test" in argv:
        return self_test()

    argv = list(argv)
    verbose = "--verbose" in argv or "-v" in argv
    argv = [a for a in argv if a not in ("--verbose", "-v")]

    only = argv[1:] if len(argv) > 1 else None
    cases = [c for c in CASES if not only or c.spec in only
             or c.spec.removesuffix(".osc") in only]
    if not cases:
        print(f"No cases matched {only}. Known specs: {[c.spec for c in CASES]}")
        return 2

    if verbose:
        # Walk each specification through the pipeline and print every stage, rather than
        # reporting a board. Meant for eyeballing one or two examples.
        rc = 0
        for case in cases:
            try:
                explain(os.path.join(HERE, case.spec))
            except Exception as exc:
                print(f"\n{case.spec} stopped: {type(exc).__name__}: {exc}")
                rc = 1
        return rc

    return run_cases(cases, prefix="keep_tests_")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
