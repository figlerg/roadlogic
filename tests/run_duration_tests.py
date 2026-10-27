"""Runner for the duration test specifications.

The standard allows `duration` on a composition, serial(duration: ...) and so on, and on a single
invocation, car1.drive(duration: ...). It bounds the time from the start of the composition or
invocation to its end. A composition or invocation covers phases k1..k2 of the plan, so its
duration bounds T(k2) - T(k1-1), with T0 = 0. The checks read the goal times out of the plan.

Durations are in s, and one s is one step.

Run with:
    source venv/bin/activate
    python tests/run_duration_tests.py                        # all cases
    python tests/run_duration_tests.py duration_nested.osc -v # walk one through the pipeline
"""

import os
import sys

from plan_checks import (
    HERE,
    Case,
    all_of,
    explain,
    last_goal_between,
    run_cases,
    span_between,
)

CASES = [
    Case(
        "duration_min.osc",
        "minimum duration rules out a zero-length plan",
        invariant=last_goal_between(4, 10),
    ),
    Case(
        "duration_exact.osc",
        "a single value pins the duration",
        invariant=last_goal_between(5, 5),
    ),
    Case(
        "duration_max_ok.osc",
        "a pass that fits in 20s",
        invariant=last_goal_between(1, 20),
    ),
    Case(
        "duration_max_unsat.osc",
        "the same pass cannot fit in 2s",
        sat=False,
    ),
    Case(
        "duration_nested.osc",
        "durations on two nested parallel compositions",
        invariant=all_of(span_between(0, 1, 2, 3), span_between(1, 2, 4, 6)),
    ),
    Case(
        "one_of_nested.osc",
        "durations and a keep inside the alternatives of a one_of: only the chosen one's apply",
        invariant=last_goal_between(4, 12),
    ),
    Case(
        "duration_nested_deep.osc",
        "durations on every level: scenario, parallel, serial and single invocations",
        invariant=all_of(span_between(0, 1, 2, 3), span_between(1, 2, 1, 2), span_between(2, 3, 2, 4),
                         span_between(1, 3, 3, 6), last_goal_between(5, 9)),
    ),
    Case(
        "duration_invocation.osc",
        "durations on single invocations, inside a composition duration",
        invariant=all_of(span_between(0, 1, 3, 4), span_between(1, 2, 2, 5),
                         last_goal_between(3, 20)),
    ),
    Case(
        "duration_conflict_unsat.osc",
        "two phases of at least 3s cannot fit into 5s",
        sat=False,
    ),
    Case(
        "duration_wrong_unit.osc",
        "a duration in m is rejected",
        raises=ValueError,
    ),
    Case(
        "duration_overlap.osc",
        "the unsupported overlap parameter is rejected, not ignored",
        raises=NotImplementedError,
    ),
]


def main(argv):
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
        rc = 0
        for case in cases:
            try:
                explain(os.path.join(HERE, case.spec))
            except Exception as exc:
                print(f"\n{case.spec} stopped: {type(exc).__name__}: {exc}")
                rc = 1
        return rc

    return run_cases(cases, prefix="duration_tests_")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
