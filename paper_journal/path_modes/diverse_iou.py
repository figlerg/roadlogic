"""Diverse plans from one open clingo Control: each new plan has footprint IoU at most theta with every
earlier plan.

    python paper_journal/path_modes/diverse_iou.py <spec> <theta> [n] [rule_injection]

The footprint of a plan is the set of (position, lane) cells its cars cover over the whole plan,
interpolated between steps, exactly as get_covered_cell in map_plan.py, the paper's similarity measure.
After each plan B_k the Control gets, without restarting, the facts b_k(X,L) and the constraint
IoU(A, B_k) <= theta, written with theta = p/q as one weighted sum:

    q * |A & B_k| <= p * |A | B_k|   <=>   (q+p) * |A & B_k| - p * |A| <= p * |B_k|

theta = 1 forbids only an identical footprint (IoU < 1, a strict comparison). The constraints are guarded by query(H) for the horizon
they were grounded at, and added again when the horizon grows, because a constraint only sees the
atoms that existed when it was grounded. Early stop at h + 2, as in the planner. A plan gets BUDGET
seconds once there is one: if none comes, that horizon is done.

Prints one JSON line: plans, seconds, mean and max pairwise IoU similarity (the paper's matrix code).
Plans along the shortest path. Run from the repository root with the venv active.
"""
import contextlib, io, json, os, sys, tempfile, time, warnings
from fractions import Fraction

sys.path.insert(0, "tests")
warnings.simplefilter("ignore")
import networkx as nx
import numpy as np
from clingo import Control, Function, Number
from plan_checks import CONTROLLER_LP, Planner
from planning.asp.MyModel import MyModel
from commonroad_extensions.plan_execution.map_plan import compute_similarity_matrix, get_covered_cell

SPEC, THETA = sys.argv[1], Fraction(sys.argv[2]).limit_denominator(20)
N = int(sys.argv[3]) if len(sys.argv) > 3 else 10
RULES = [CONTROLLER_LP] + sys.argv[4:5]
IMAX, EXTRA = 25, 2
BUDGET = float(os.environ.get("DIVERSITY_BUDGET", "10"))
ENC = os.path.join("planning", "asp", "encoding")
BASE = [os.path.join(ENC, f) for f in ("constants.lp", "facts.lp", "dynamics.lp")]
P, Q = THETA.numerator, THETA.denominator

# The footprint cells of step t, as get_covered_cell: the state itself, and between the states at t-1
# and t every position from S0 to S, the first half of them in the old lane, the rest in the new one.
FOOTPRINT = """
fp(S,L,0) :- holds(state(V,loc(S,L),_),0), t = 0.
fp(X,L0,t) :- holds(state(V,loc(S0,L0),_),t-1), holds(state(V,loc(S,L),_),t), X = S0..S, X - S0 < (S - S0 + 1) / 2.
fp(X,L,t)  :- holds(state(V,loc(S0,L0),_),t-1), holds(state(V,loc(S,L),_),t), X = S0..S, X - S0 >= (S - S0 + 1) / 2.
"""

quiet = lambda: contextlib.redirect_stdout(io.StringIO())
with quiet():
    planner = Planner(SPEC, out_path=tempfile.mkdtemp())
G = planner.translation_graph
path = sorted(nx.all_simple_paths(G.graph, G.initial, G.final), key=len)[0]
folder = tempfile.mkdtemp()
with quiet():
    planner.create_asp_instance([a.id for a in G.actors], path, folder)
imax = IMAX if planner._horizon_cap is None else min(IMAX, planner._horizon_cap + 1)

ctl = Control()
ctl.configuration.solve.models = 0
ctl.configuration.solve.parallel_mode = 1
ctl.add("check", ["t"], FOOTPRINT)
for f in BASE + [os.path.join(folder, "instance.lp")] + RULES:
    ctl.load(f)
ctl.add("check", ["t"], "#external query(t).")

footprints = []  # (k, size) per plan, its b_k facts are in the Control
parts = 0


def constrain(k, size, horizon):
    """IoU(A, B_k) <= theta for plans at this horizon."""
    global parts
    parts += 1
    name = f"iou_{parts}"
    # theta = 1 means IoU < 1, an identical footprint, so the comparison is strict there
    compare = ">=" if THETA == 1 else ">"
    ctl.add(name, [], f":- query({horizon}), #sum{{ {Q + P},X,L : fp(X,L,_), b{k}(X,L) ; "
                      f"-{P},X,L : fp(X,L,_) }} {compare} {P * size}.")
    ctl.ground([(name, [])])


def remember(plan, horizon):
    k = len(footprints)
    cells = get_covered_cell(plan, float("inf"))
    name = f"fp_{k}"
    ctl.add(name, [], "".join(f"b{k}({x},{l})." for x, l in sorted(cells)))
    ctl.ground([(name, [])])
    footprints.append((k, len(cells)))
    constrain(k, len(cells), horizon)


start, plans, first_horizon = time.time(), [], None
for step in range(imax):
    if first_horizon is not None and step > first_horizon + EXTRA:
        break
    ground = [("check", [Number(step)])]
    if step > 0:
        ctl.release_external(Function("query", [Number(step - 1)]))
        ground.append(("step", [Number(step)]))
    else:
        ground.append(("base", []))
    ctl.ground(ground)
    ctl.assign_external(Function("query", [Number(step)]), True)
    for k, size in footprints:  # earlier plans' constraints, for this horizon's atoms
        constrain(k, size, step)
    while len(plans) < N:
        model = None
        with ctl.solve(yield_=True, async_=True) as handle:
            handle.resume()
            if handle.wait(BUDGET if first_horizon is not None else None):
                model = handle.model()
                model = MyModel(model) if model is not None else None
            else:
                handle.cancel()
        if model is None:
            break
        if first_horizon is None:
            first_horizon = step
        plans.append(model)
        remember(model, step)
    if len(plans) >= N:
        break
seconds = round(time.time() - start, 1)

mean = worst = None
if len(plans) > 1:
    with quiet():
        matrix = np.array(compute_similarity_matrix(plans, up_to_time=float("inf")))
    off = matrix[~np.eye(len(plans), dtype=bool)]
    mean, worst = round(float(off.mean()), 3), round(float(off.max()), 3)
print(json.dumps({"spec": SPEC.split("/")[-3] if "experiments_src" in SPEC else os.path.basename(SPEC),
                  "theta": float(THETA), "n": N, "plans": len(plans), "seconds": seconds,
                  "seconds_per_plan": round(seconds / max(len(plans), 1), 2),
                  "mean_similarity": mean, "max_similarity": worst,
                  "lengths": sorted({p.max_t for p in plans})}))
