"""Compare the tuple and boundary goal encodings on the benchmark specs.

Each spec is planned under three configurations:

  original   tuple encoding, two padding steps     what the HSCC paper used
  boundary   boundary encoding, two padding steps  should accept exactly the same plans
  cut        boundary encoding, no padding         stops at the step the last goal is met
  tuple_cut  tuple encoding, no padding            the same cut on the old encoding

Reported per spec: solve time, horizon of the first plan, how many of the first N plans are the
same trace as one of the original's first N, and a cross-check. The cross-check re-solves each
plan with its trace fixed, under the other configuration, to confirm that one accepts it too:
  boundary plans under original, at the same horizon
  original plans under boundary, at the same horizon
  cut plans under original, which should need exactly the two padding steps more
  cut plans under tuple_cut and back, at the same horizon

Run with:
    source venv/bin/activate
    python tests/compare_goal_encodings.py                  # vanilla benchmarks, N=5
    python tests/compare_goal_encodings.py exp_002 --n 10
    python tests/compare_goal_encodings.py exp_004          # slow, 45 minutes in the paper run
"""

import argparse
import os
import sys
import tempfile
import time
import warnings

import networkx as nx

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from planning.Planner import Planner  # noqa: E402
from planning.asp.generate_plans import generate_plans, NoModelException  # noqa: E402

CONTROLLER_LP = os.path.join(ROOT, "create_scenarios", "controller.lp")
DEFAULT_SPECS = ["exp_001", "exp_002", "exp_003", "exp_005", "exp_006", "exp_007"]

CONFIGS = {
    "original": dict(goal_encoding="tuple", pad_after_goals=True),
    "boundary": dict(goal_encoding="boundary", pad_after_goals=True),
    "cut": dict(goal_encoding="boundary", pad_after_goals=False),
    "tuple_cut": dict(goal_encoding="tuple", pad_after_goals=False),
}


def rules_for(exp):
    injection = os.path.join(ROOT, "experiments_src", exp, "in", "rule_injection.lp")
    rules = [CONTROLLER_LP]
    if os.path.getsize(injection) > 0:
        rules.append(injection)
    return rules


def trace(model):
    """The plan as a set of holds atoms, which is what makes two plans the same."""
    return frozenset(str(pred) for pred in model.holds)


def plan(exp, config, n, imax):
    spec = os.path.join(ROOT, "experiments_src", exp, "in", "spec.osc")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        planner = Planner(spec, out_path=tempfile.mkdtemp(), **CONFIGS[config])
        start = time.perf_counter()
        models = planner.plans(n=n, external_rules=rules_for(exp), visualize=False, imax=imax)
        elapsed = time.perf_counter() - start
    return models, elapsed


def accepted_horizon(exp, config, model, slack):
    """Fix the model's trace and ask the configuration for its first accepting horizon.

    Returns that horizon, or None if nothing up to the trace length plus `slack` accepts it.
    """
    spec = os.path.join(ROOT, "experiments_src", exp, "in", "spec.osc")
    out = tempfile.mkdtemp()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        planner = Planner(spec, out_path=out, **CONFIGS[config])
        graph = planner.translation_graph
        planner.create_asp_instance([a.id for a in graph.actors],
                                    next(nx.all_simple_paths(graph.graph, "init", "fin")))

    fixed = os.path.join(out, "fixed_trace.lp")
    with open(fixed, "w") as f:
        f.write("#program check(t).\n")
        for pred in model.holds:
            f.write(f":- query(t), not {pred}.\n")

    files = [os.path.join(out, "instance.lp")] + rules_for(exp) + [fixed]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            found = generate_plans(files=files, n=1, imax=model.max_t + slack + 1, time_limit=300)
    except (NoModelException, TimeoutError):
        return None
    return found[0].max_t


def compare(exp, n, imax):
    runs = {name: plan(exp, name, n, imax) for name in CONFIGS}
    base_models, _ = runs["original"]
    base_traces = {trace(m) for m in base_models}

    print(f"\n{exp}")
    for name, (models, elapsed) in runs.items():
        same = sum(trace(m) in base_traces for m in models)
        print(f"  {name:<9} {elapsed:8.1f}s   horizon t={models[0].max_t:<3} "
              f"{len(models)} plans, {same} identical to an original plan")

    checks = []
    for m in runs["boundary"][0]:
        checks.append(("boundary plan accepted by original", accepted_horizon(exp, "original", m, 0) == m.max_t))
    for m in base_models:
        checks.append(("original plan accepted by boundary", accepted_horizon(exp, "boundary", m, 0) == m.max_t))
    for m in runs["cut"][0]:
        checks.append(("cut plan plus two steps accepted by original",
                       accepted_horizon(exp, "original", m, 2) == m.max_t + 2))
    for m in runs["cut"][0]:
        checks.append(("cut plan accepted by tuple_cut", accepted_horizon(exp, "tuple_cut", m, 0) == m.max_t))
    for m in runs["tuple_cut"][0]:
        checks.append(("tuple_cut plan accepted by cut", accepted_horizon(exp, "cut", m, 0) == m.max_t))

    for label in dict.fromkeys(label for label, _ in checks):
        results = [ok for lbl, ok in checks if lbl == label]
        print(f"  {label:<46} {sum(results)}/{len(results)}")

    return runs, checks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("specs", nargs="*", default=DEFAULT_SPECS)
    ap.add_argument("--n", type=int, default=5, help="plans per configuration")
    ap.add_argument("--imax", type=int, default=30)
    args = ap.parse_args(argv)

    failed = 0
    for exp in args.specs:
        _, checks = compare(exp, args.n, args.imax)
        failed += sum(not ok for _, ok in checks)
    print(f"\n{failed} cross-checks failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
