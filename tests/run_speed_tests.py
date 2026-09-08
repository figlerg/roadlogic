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
"""

import sys

from plan_checks import (
    Case,
    run_cases,
    speed_at,
    speed_between,
    speed_equals,
    speed_faster_than,
)

CASES = [
    Case(
        "speed_start_end.osc",
        "point speed at both ends of a segment, no invariant machinery needed",
        invariant=lambda m: (speed_at("ego", "start", 5)(m)
                             or speed_at("ego", "end", 10)(m)),
    ),
    Case(
        "speed_constant.osc",
        "fixed speed for the whole segment via at: all",
        invariant=speed_equals("ego", 5),
    ),
    Case(
        "speed_range.osc",
        "speed held inside a range, the 7.3.12.4.1 in-constraint desugaring",
        invariant=speed_between("ego", 5, 10),
    ),
    Case(
        "speed_overtake_keep.osc",
        "overtake with car1 at constant speed, needs speed plus the keep work",
        invariant=speed_equals("car1", 5),
    ),
    Case(
        "speed_relative.osc",
        "relative speed via faster_than, maps to RelativeConstraint with Modifier.SPEED",
        invariant=speed_faster_than("ego", "car1"),
    ),
]

# speed_start_end uses a lambda, so give it a description like the other checkers have.
CASES[0].invariant.description = "ego.speed == 5mps at start and 10mps at end"


def main(argv):
    only = argv[1:] if len(argv) > 1 else None
    cases = [c for c in CASES if not only or c.spec in only
             or c.spec.removesuffix(".osc") in only]
    if not cases:
        print(f"No cases matched {only}. Known specs: {[c.spec for c in CASES]}")
        return 2
    return run_cases(cases, prefix="speed_tests_")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
