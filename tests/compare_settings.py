"""Compare planner settings on the benchmark specs: padding and duration handling.

Each spec is planned three times:

  paper      two padding steps after the last goal, duration ignored. What the HSCC paper used.
  duration   the same, but the spec's duration is honoured. Isolates the effect of durations.
  new        no padding, duration honoured. The plan ends at the first step at which all goals are
             met, and the spec's duration rules out plans that are too short or too long.

Reported per spec: solve time, horizon of the first plan, and cross-checks. Each check re-solves a
plan with its trace fixed under another setting, to see whether that setting accepts it too:
  duration plans under paper, same horizon. Durations only restrict, so these should all pass.
  paper plans under duration, same horizon. A failure is a paper plan the duration rules out.
  new plans plus two steps under duration. A failure is a plan that ends in a state padding
  would have rejected, for example one step before an unavoidable safety violation.

Run with:
    source venv/bin/activate
    python tests/compare_settings.py                  # vanilla benchmarks, N=5
    python tests/compare_settings.py exp_002 --n 10
    python tests/compare_settings.py exp_004          # slow, 45 minutes in the paper run
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
    "paper": dict(pad_after_goals=True, honour_duration=False),
    "duration": dict(pad_after_goals=True, honour_duration=True),
    "new": dict(pad_after_goals=False, honour_duration=True),
}


def rules_for(exp):
    injection = os.path.join(ROOT, "experiments_src", exp, "in", "rule_injection.lp")
    rules = [CONTROLLER_LP]
    if os.path.getsize(injection) > 0:
        rules.append(injection)
    return rules


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
                                    next(nx.all_simple_paths(graph.graph, graph.initial, graph.final)))

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
    print(f"\n{exp}")
    for name, (models, elapsed) in runs.items():
        print(f"  {name:<9} {elapsed:8.1f}s   horizon t={models[0].max_t:<3} {len(models)} plans")

    checks = []
    for m in runs["duration"][0]:
        checks.append(("duration plan accepted by paper",
                       accepted_horizon(exp, "paper", m, 0) == m.max_t))
    for m in runs["paper"][0]:
        checks.append(("paper plan accepted by duration",
                       accepted_horizon(exp, "duration", m, 0) == m.max_t))
    for m in runs["new"][0]:
        checks.append(("new plan plus two steps accepted by duration",
                       accepted_horizon(exp, "duration", m, 2) == m.max_t + 2))

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
