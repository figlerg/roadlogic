"""Plan the paper's experiments as the pipeline does (10 plans, every 60th model) and print, per
experiment, the number of plans, the time and a fingerprint of each plan, as JSON.

    python paper_journal/path_modes/compare_paper.py <code root> <out.json> [exp ...]

<code root> is the folder whose planning/ package is used, so the same script can run an older
checkout. Settings come from the environment (ROADLOGIC_PATH_MODE, ROADLOGIC_EXTRA_HORIZON). Run
from the repository root with the venv active.
"""
import contextlib, hashlib, io, json, os, sys, tempfile, time, warnings

code, out = os.path.abspath(sys.argv[1]), sys.argv[2]
exps = sys.argv[3:] or ["exp_001", "exp_002", "exp_003", "exp_005", "exp_006", "exp_007"]
REPO = os.getcwd()
sys.path.insert(0, code)
warnings.simplefilter("ignore")
from planning.Planner import Planner

results = {}
for exp in exps:
    spec = os.path.join(REPO, "experiments_src", exp, "in", "spec.osc")
    rules = [os.path.join(REPO, "create_scenarios", "controller.lp"),
             os.path.join(REPO, "experiments_src", exp, "in", "rule_injection.lp")]
    start = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        plans = Planner(spec, out_path=tempfile.mkdtemp()).plans(n=10, external_rules=rules, visualize=False,
                                                                diversity_step=60)
    results[exp] = {"plans": len(plans), "seconds": round(time.time() - start, 1),
                    "fingerprints": [hashlib.md5(str(sorted(p.holds, key=str)).encode()).hexdigest()[:8] for p in plans]}
    print(exp, results[exp]["plans"], results[exp]["seconds"], flush=True)
json.dump(results, open(out, "w"), indent=1)
