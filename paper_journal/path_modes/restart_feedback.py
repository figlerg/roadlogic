"""The BASIC and STRICT heuristics of create_scenarios/dynamic_feedback.py as they were run there: after
each plan a constraint is added with Planner.add_rule, and the next plan comes from a new solve with a
fresh clingo Control, so the engine restarts every time. The simulation-based VALIDITY heuristic is left
out. The same output as diverse.py, so the two can be compared.

    python paper_journal/path_modes/restart_feedback.py <spec> basic|strict <n> [rule_injection]

Run from the repository root with the venv active.
"""
import contextlib, io, json, os, sys, tempfile, time, warnings

sys.path.insert(0, "tests")
sys.path.insert(0, "create_scenarios")
warnings.simplefilter("ignore")
import numpy as np
from plan_checks import CONTROLLER_LP, Planner
from planning.asp.generate_plans import NoModelException
from commonroad_extensions.plan_execution.map_plan import compute_similarity_matrix
from dynamic_feedback import not_conjunction, not_rule

SPEC, METHOD, N = sys.argv[1], sys.argv[2], int(sys.argv[3])
RULES = [CONTROLLER_LP] + sys.argv[4:5]
quiet = lambda: contextlib.redirect_stdout(io.StringIO())

with quiet():
    planner = Planner(SPEC, out_path=tempfile.mkdtemp())
start, plans = time.time(), []
while len(plans) < N and time.time() - start < 1700:
    try:
        with quiet():
            plan = planner.plans(n=1, external_rules=RULES, visualize=False)[0]
    except (NoModelException, TimeoutError):
        break  # the constraints rule out every further plan
    plans.append(plan)
    states = [h for h in plan.holds if h[-1] == 1]
    if METHOD == "strict":
        for a in states:
            planner.add_rule(not_rule(a, t=0))
    else:
        planner.add_rule(not_conjunction(states, t=0))
seconds = round(time.time() - start, 1)

mean = worst = None
if len(plans) > 1:
    with quiet():
        matrix = np.array(compute_similarity_matrix(plans, up_to_time=float("inf")))
    off = matrix[~np.eye(len(plans), dtype=bool)]
    mean, worst = round(float(off.mean()), 3), round(float(off.max()), 3)
print(json.dumps({"spec": SPEC.split("/")[-3], "method": f"{METHOD}_restart", "n": N, "plans": len(plans),
                  "seconds": seconds, "seconds_per_plan": round(seconds / max(len(plans), 1), 2),
                  "mean_similarity": mean, "max_similarity": worst,
                  "lengths": sorted({p.max_t for p in plans})}))
