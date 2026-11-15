"""Diverse plans from one open clingo Control, without restarting it.

    python paper_journal/path_modes/diverse.py <spec> <method> <n> [rule_injection]

Methods, each a way to steer the next plan away from the earlier ones:
  step<k>         every k-th model as it comes, the paper's diversity_step (step60), step1 = consecutive
  basic           after each plan, forbid the combination of all cars' states at step 1, the BASIC
                  heuristic of create_scenarios/dynamic_feedback.py, here without a restart
  strict          after each plan, forbid each car's state at step 1 separately, the STRICT heuristic
  iou<theta>      after each plan B_k, require IoU(A, B_k) <= theta for every later plan A, on the
                  footprint of the paper's similarity measure (map_plan.get_covered_cell)
  combo           after each plan, forbid its combination of start configuration and driving
                  parameters (brake_turn, accel_turn when DIVERSE_CONTROLLER chooses them): the paper's
                  "one plan per sampled parameter combination", without restarting
  risecombo<theta>  rise and combo together: a new parameter combination and IoU <= theta
  rise<theta>     as iou, but whenever no plan comes within the budget, once there is a first plan,
                  theta goes up by 0.1, up to 1 (identical footprints forbidden). At 1 the search moves
                  to the next horizon, which starts again at theta, since an incremental Control
                  cannot go back to an earlier horizon

Settings from the environment:
  DIVERSE_EXTRA   horizons searched past the first plan, default 2 (the planner's early stop), -1 none
  DIVERSE_BUDGET  seconds a plan may take once there is a first one, default 10
  DIVERSE_CONFLICTS  instead of seconds, a budget in solver conflicts per plan (clingo solve_limit),
                  which does not depend on machine load, so reruns give identical results
  DIVERSE_IMAX    longest plan, default 25
  DIVERSE_CONTROLLER  controller rules to use instead of create_scenarios/controller.lp, e.g.
                  paper_journal/path_modes/controller_params.lp, which makes the driving constants
                  choices
  DIVERSE_CAP     for rise: the loosest theta allowed, default 1. Below 1, a horizon where nothing comes
                  even at the cap is left for the next one, so longer plans are preferred over near-copies
  DIVERSE_FORGET  e.g. varScores,signs: the solver forgets its variable scores and saved signs on every
                  step (clasp --forget-on-step), keeping grounding and learned nogoods, so it is not
                  drawn back towards its previous plan
  DIVERSE_SAVE    a folder to pickle the plans into, 0001.pkl, ... in the order found
  DIVERSE_HEUR    1: clingo's domain heuristic, told to prefer leaving the cells of earlier plans empty
                  (#heuristic fp(X,L,T) : b_k(X,L). [1, false]), for the footprint methods

How it works: clingo's multi-shot API lets a program part be added and grounded into a running
Control between two solve calls (ctl.add, then ctl.ground). The grounding and what the solver learned
stay. Added parts may only contain constraints and fresh facts, never redefine an atom, and only see
atoms that exist when they are grounded. That is why the footprint constraints are guarded by
query(H) for their horizon and added again when the horizon grows. The step-1 constraints of basic and
strict do not depend on the horizon.

Prints one JSON line: plans, seconds, mean and max pairwise similarity with the paper's matrix code,
the plan lengths, and for rise the theta each plan was found under. Plans along the shortest path.
Run from the repository root with the venv active.
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

SPEC, METHOD, N = sys.argv[1], sys.argv[2], int(sys.argv[3])
RULES = [os.environ.get("DIVERSE_CONTROLLER", CONTROLLER_LP)] + sys.argv[4:5]
EXTRA = int(os.environ.get("DIVERSE_EXTRA", "2"))
BUDGET = float(os.environ.get("DIVERSE_BUDGET", "10"))
HEUR = os.environ.get("DIVERSE_HEUR", "0") == "1"
CONFLICTS = int(os.environ.get("DIVERSE_CONFLICTS", "0"))
CAP = Fraction(os.environ.get("DIVERSE_CAP", "1")).limit_denominator(20)
IMAX = int(os.environ.get("DIVERSE_IMAX", "25"))
ENC = os.path.join("planning", "asp", "encoding")
BASE = [os.path.join(ENC, f) for f in ("constants.lp", "facts.lp", "dynamics.lp")]

STEP = int(METHOD[4:]) if METHOD.startswith("step") else 1
THETA = Fraction(METHOD[3:] if METHOD.startswith("iou") else METHOD.replace("risecombo", "rise")[4:]).limit_denominator(20) \
    if METHOD.startswith(("iou", "rise")) else None
FOOTPRINT_METHOD = THETA is not None

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
if HEUR:
    ctl.configuration.solver.heuristic = "Domain"
FORGET = os.environ.get("DIVERSE_FORGET", "")
if FORGET:
    ctl.configuration.solver.forget_on_step = FORGET
if FOOTPRINT_METHOD:
    ctl.add("check", ["t"], FOOTPRINT)
for f in BASE + [os.path.join(folder, "instance.lp")] + RULES:
    ctl.load(f)
ctl.add("check", ["t"], "#external query(t).")

parts = 0
footprints = []  # (k, size), the facts b_k(X,L) are in the Control
theta = THETA


def add(program):
    global parts
    parts += 1
    ctl.add(f"part_{parts}", [], program)
    ctl.ground([(f"part_{parts}", [])])


level = 0  # each bound gets its own external guard level(J), released when the bound is loosened


def new_level():
    """Switch off the constraints of the current bound and open a new guard for the next one."""
    global level
    ctl.release_external(Function("level", [Number(level)]))
    level += 1
    add(f"#external level({level}).")
    ctl.assign_external(Function("level", [Number(level)]), True)


def iou_constraint(k, size, horizon, bound):
    p, q = bound.numerator, bound.denominator
    compare = ">=" if bound == 1 else ">"  # theta = 1: IoU < 1, no identical footprint
    add(f":- query({horizon}), level({level}), "
        f"#sum{{ {q + p},X,L : fp(X,L,_), b{k}(X,L) ; -{p},X,L : fp(X,L,_) }} {compare} {p * size}.")


def step1_states(plan):
    return [str(h).replace(" ", "") for h in plan.holds if h[-1] == 1]


def steer_away(plan, horizon):
    """Constrain later plans away from this one, as the method says."""
    if METHOD == "basic":
        states = step1_states(plan)
        if states:
            add(f":- {', '.join(states)}.")
    if METHOD == "combo" or METHOD.startswith("risecombo"):
        chosen = [str(h).replace(" ", "") for h in plan.holds if h[-1] == 0]
        chosen += [str(a) for a in plan if getattr(a, "name", "") in ("brake_turn", "accel_turn")]
        add(f":- {', '.join(chosen)}.")
    if METHOD == "strict":
        for state in step1_states(plan):
            add(f":- {state}.")
    if FOOTPRINT_METHOD:
        k = len(footprints)
        cells = get_covered_cell(plan, float("inf"))
        add("".join(f"b{k}({x},{l})." for x, l in sorted(cells))
            + (f"#heuristic fp(X,L,T) : b{k}(X,L), fp(X,L,T). [1, false]" if HEUR else ""))
        footprints.append((k, len(cells)))
        iou_constraint(k, len(cells), horizon, theta)


if FOOTPRINT_METHOD:
    add("#external level(0).")
    ctl.assign_external(Function("level", [Number(0)]), True)
def next_plan(handle):
    """The next model of an open solve within the budget, or None (none left, or out of budget)."""
    handle.resume()
    if CONFLICTS:
        handle.wait()  # the conflict limit set on the configuration ends the search
        return handle.model()
    if not handle.wait(BUDGET if first_horizon is not None else None):
        handle.cancel()
        return None
    return handle.model()


def limit(on):
    """The conflict budget applies once there is a first plan, never before."""
    if CONFLICTS:
        ctl.configuration.solve.solve_limit = f"{CONFLICTS},umax" if on else "umax,umax"


start, plans, thetas, first_horizon, count = time.time(), [], [], None, 0
found_at = []  # seconds at which each plan was found
for step in range(imax):
    if first_horizon is not None and EXTRA >= 0 and step > first_horizon + EXTRA:
        break
    ground = [("check", [Number(step)])]
    if step > 0:
        ctl.release_external(Function("query", [Number(step - 1)]))
        ground.append(("step", [Number(step)]))
    else:
        ground.append(("base", []))
    ctl.ground(ground)
    ctl.assign_external(Function("query", [Number(step)]), True)
    if METHOD.startswith("rise") and theta != THETA:
        theta = THETA  # each horizon starts strict again
        new_level()
    for k, size in footprints:  # the earlier plans' footprint constraints, for this horizon's atoms
        iou_constraint(k, size, step, theta)
    found_here = False

    if METHOD.startswith("step"):
        # plain enumeration, every STEP-th model
        limit(first_horizon is not None)
        with ctl.solve(yield_=True, async_=True) as handle:
            while len(plans) < N:
                model = next_plan(handle)
                if model is None:
                    break
                first_horizon = step if first_horizon is None else first_horizon
                if count % STEP == 0:
                    plans.append(MyModel(model))
                    found_at.append(time.time() - start)
                count += 1
    else:
        # one solve call per plan, the steering constraint added in between
        while len(plans) < N:
            limit(first_horizon is not None)
            with ctl.solve(yield_=True, async_=True) as handle:
                model = next_plan(handle)
                model = MyModel(model) if model is not None else None
            if model is None:
                # loosen once there is any plan, horizons before the first one are just too short
                if METHOD.startswith("rise") and theta < CAP and first_horizon is not None:
                    # nothing under this bound within the budget: loosen it, re-add all constraints
                    theta = min(CAP, theta + Fraction(1, 10))
                    new_level()
                    for k, size in footprints:
                        iou_constraint(k, size, step, theta)
                    continue
                break
            first_horizon = step if first_horizon is None else first_horizon
            found_here = True
            plans.append(model)
            found_at.append(time.time() - start)
            thetas.append(float(theta) if theta is not None else None)
            steer_away(model, step)
    if len(plans) >= N:
        break
seconds = round(time.time() - start, 1)
if os.environ.get("DIVERSE_SAVE"):
    import pickle
    os.makedirs(os.environ["DIVERSE_SAVE"], exist_ok=True)
    for i, plan in enumerate(plans, 1):
        with open(os.path.join(os.environ["DIVERSE_SAVE"], f"{i:04d}.pkl"), "wb") as f:
            pickle.dump(plan, f)

mean = worst = None
if len(plans) > 1:
    with quiet():
        matrix = np.array(compute_similarity_matrix(plans, up_to_time=float("inf")))
    off = matrix[~np.eye(len(plans), dtype=bool)]
    mean, worst = round(float(off.mean()), 3), round(float(off.max()), 3)
# the variety of the first k plans and the time until the k-th, for comparing at equal k
curve = {}
for k in (5, 10, 20, 30, 40, 50):
    if len(plans) >= k:
        sub = matrix[:k, :k]
        curve[k] = [round(float(sub[~np.eye(k, dtype=bool)].mean()), 3), round(found_at[k - 1], 1)]
print(json.dumps({"spec": SPEC.split("/")[-3] if "experiments_src" in SPEC else os.path.basename(SPEC),
                  "method": METHOD, "extra": EXTRA, "budget": BUDGET, "heur": HEUR, "cap": float(CAP), "conflicts": CONFLICTS, "forget": FORGET, "n": N, "plans": len(plans),
                  "seconds": seconds, "seconds_per_plan": round(seconds / max(len(plans), 1), 2),
                  "mean_similarity": mean, "max_similarity": worst,
                  "lengths": sorted({p.max_t for p in plans}),
                  "thetas": sorted(set(thetas)) if METHOD.startswith("rise") else None,
                  "controller": os.path.basename(RULES[0]), "curve": curve}))
