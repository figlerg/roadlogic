"""The planning time of one spec under the clingo options in ROADLOGIC_CLASP_ARGS.

    ROADLOGIC_CLASP_ARGS="--configuration=trendy" python paper_journal/profiling/time_plans.py <spec> [n]

Plans n plans (default 10) with the planner's defaults and prints one JSON line: the time to the first
plan, the total time, the plan lengths and a fingerprint of the plans, so runs under different options
can be checked for giving the same plans. Run from the repository root with the venv active.
"""
import contextlib, hashlib, io, json, os, sys, tempfile, time, warnings
sys.path.insert(0, "tests")
warnings.simplefilter("ignore")
from plan_checks import CONTROLLER_LP, Planner
from planning.asp.generate_plans import NoModelException

spec = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
start, first, plans = time.time(), None, []
try:
    with contextlib.redirect_stdout(io.StringIO()):
        planner = Planner(spec, out_path=tempfile.mkdtemp())
        # plans() returns a list, so the time to the first plan is taken from a separate n=1 call
        planner.plans(n=1, external_rules=[CONTROLLER_LP], visualize=False, imax=25)
        first = time.time() - start
        start2 = time.time()
        plans = Planner(spec, out_path=tempfile.mkdtemp()).plans(n=n, external_rules=[CONTROLLER_LP],
                                                                 visualize=False, imax=25)
        total = time.time() - start2
except NoModelException:
    total = time.time() - start
prints = hashlib.md5("".join(sorted(str(sorted(p.holds, key=str)) for p in plans)).encode()).hexdigest()[:8]
print(json.dumps({"spec": spec, "clasp_args": os.environ.get("ROADLOGIC_CLASP_ARGS", ""), "n": n,
                  "first_plan_s": round(first, 1) if first else None, "n_plans_s": round(total, 1),
                  "plans": len(plans), "lengths": sorted({max(h[1] for h in p.holds) for p in plans}),
                  "fingerprint": prints}))
