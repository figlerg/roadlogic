"""Runner for the speed modifier test specifications.

The speed modifier is planned as its own commit landing before the keep work, see
docs/keep-spec.md section 1b. Nothing is implemented yet, so every case is expected to report
PENDING with a NotImplementedError from TranslationGraphVisitor.

Checks run on the ASP plan, not on the Frenetix simulation: they read Vel_lon out of
holds(state(V, loc(S,L), dyn(Vel_lon, Vel_lat)), T). A plan whose speeds are right is the
precondition for a simulation whose speeds are right, and it is the part these changes can break.

Speed literals are in mps and no conversion happens: mps is one segment per step, which is
exactly the Vel_lon integer in the plan. Only m, s and mps are accepted, see section 7 of
docs/keep-spec.md.

Run with:
    source venv/bin/activate
    python tests/run_speed_tests.py                   # all cases
    python tests/run_speed_tests.py speed_range.osc   # a subset
    python tests/run_speed_tests.py speed_range.osc -v   # walk it through the pipeline
"""

import os
import sys

from plan_checks import (
    HERE,
    Case,
    explain,
    in_keep_windows,
    run_cases,
    speed_at_goal,
    speed_at_start,
    speed_between,
    speed_equals,
    faster_at_goal,
)

CASES = [
    Case(
        "speed_start_end.osc",
        "point speed at both ends of a segment, no invariant machinery needed",
        invariant=lambda m: (speed_at_start("ego", 5)(m)
                             or speed_at_goal("ego", 1, 10)(m)),
    ),
    Case(
        "speed_constant.osc",
        "fixed speed for the whole segment via at: all",
        invariant=in_keep_windows(speed_equals("ego", 5)),
    ),
    Case(
        "speed_range.osc",
        "speed held inside a range, the 7.3.12.4.1 in-constraint desugaring",
        invariant=in_keep_windows(speed_between("ego", 5, 10)),
    ),
    Case(
        "speed_overtake_keep.osc",
        "overtake with car1 at constant speed, needs speed plus the keep work",
        invariant=in_keep_windows(speed_equals("car1", 5)),
        # Held at 5mps car1 cannot change lane (min_change_speed is 6), so ego has to merge back
        # in front of it, which takes longer. With padding the first plan is at horizon 12.
        imax=14,
    ),
    Case(
        "speed_relative.osc",
        "relative speed via faster_than at the phase goal, a RelativeConstraint with Modifier.SPEED",
        invariant=faster_at_goal("ego", "car1", 1),
    ),
]

# speed_start_end uses a lambda, so give it a description like the other checkers have.
CASES[0].invariant.description = "ego.speed == 5mps at t=0 and 10mps at goal T1"


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

    return run_cases(cases, prefix="speed_tests_")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
