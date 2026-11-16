"""Check that the pure OpenSCENARIO journal specs (specs_paper/) plan like the paper's spec plus its
hand-written rule injection (experiments_src/<exp>/in/).

    python paper_journal/benchmark/check_specs_paper.py [exp_004 exp_005 exp_007] [--n 10] [--dir specs_paper]

Plans n plans each way and compares them: identical plans (same states at every step), the plan
lengths, and the planning time.
"""
import contextlib, hashlib, io, os, sys, tempfile, time, warnings
sys.path.insert(0, "tests")
warnings.simplefilter("ignore")
from plan_checks import CONTROLLER_LP, Planner
from planning.asp.generate_plans import NoModelException

args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and not sys.argv[i - 1].startswith("--")]
n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 10
exps = [a for a in args if a.startswith("exp_")] or ["exp_004", "exp_005", "exp_007"]
HERE = os.path.dirname(os.path.abspath(__file__))
SPECS = sys.argv[sys.argv.index("--dir") + 1] if "--dir" in sys.argv else os.path.join(HERE, "specs_paper")


def plan(spec, rules):
    start = time.time()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            plans = Planner(spec, out_path=tempfile.mkdtemp()).plans(n=n, external_rules=[CONTROLLER_LP] + rules,
                                                                    visualize=False, imax=25)
    except NoModelException:
        plans = []
    prints = [hashlib.md5(str(sorted(p.holds, key=str)).encode()).hexdigest()[:8] for p in plans]
    return prints, sorted({p.max_t for p in plans}), time.time() - start


for exp in exps:
    src = os.path.join("experiments_src", exp, "in")
    old = plan(os.path.join(src, "spec.osc"), [os.path.join(src, "rule_injection.lp")])
    new = plan(os.path.join(SPECS, f"{exp}.osc"), [])
    same = "identical plans, same order" if old[0] == new[0] else \
        f"{len(set(old[0]) & set(new[0]))} of {len(old[0])} plans shared"
    print(f"{exp}: paper spec + injection {len(old[0])} plans, lengths {old[1]}, {old[2]:.1f} s | "
          f"journal spec {len(new[0])} plans, lengths {new[1]}, {new[2]:.1f} s | {same}", flush=True)
