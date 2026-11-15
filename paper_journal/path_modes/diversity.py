"""Ways to get more varied plans from one open clingo Control, without restarting it.

    python paper_journal/path_modes/diversity.py <spec> <method> [n] [rule_injection]

Methods:
  consecutive  the first n models, as they come
  step60       every 60th model, the paper's diversity_step
  lanes        projection on each car's lane at each step: no two plans share a lane sequence
  cells        projection on a coarse grid: lane, 5 m blocks of position, every second step
  goals        projection on goal<k>(T), at which steps each goal holds: plans differ in timing
  lanes_ban    no projection: after each plan, a constraint forbids its lane sequence, solve on
  cells_ban    the same with the coarse grid of cells
  random       each plan from a fresh solve call on the same Control, with another random seed and
               random decision signs, so the search starts somewhere else each time

Projection (#project) makes clingo enumerate one model per distinct combination of the projected
atoms, so each new plan has to differ in what is projected. A strict projection may have few
distinct values, and proving there are no more is expensive, so each plan gets BUDGET seconds: if
none comes, that horizon is done. The budget never applies before the first plan. The *_ban methods
keep the solver in its normal mode and add one integrity constraint per plan to the open Control. Prints one JSON line with the mean
pairwise IoU similarity (the paper's measure, lower is more varied), the time and the number of
plans. Plans along the first path only. Run from the repository root with the venv active.
"""
import contextlib, io, json, os, sys, tempfile, time, warnings

sys.path.insert(0, "tests")
warnings.simplefilter("ignore")
import networkx as nx
import numpy as np
from clingo import Control, Function, Number
from plan_checks import CONTROLLER_LP, Planner
from planning.asp.MyModel import MyModel

SPEC, METHOD = sys.argv[1], sys.argv[2]
N = int(sys.argv[3]) if len(sys.argv) > 3 else 10
RULES = [CONTROLLER_LP] + sys.argv[4:5]
IMAX = 25
BUDGET = float(os.environ.get("DIVERSITY_BUDGET", "5"))
ENC = os.path.join("planning", "asp", "encoding")
BASE = [os.path.join(ENC, f) for f in ("constants.lp", "facts.lp", "dynamics.lp")]

PROJECTIONS = {
    "lanes": """
#program check(t).
plan_lane(V,L,t) :- holds(state(V,loc(_,L),_),t).
#project plan_lane/3.
""",
    "cells": """
#program check(t).
plan_cell(V,L,S/5,t) :- holds(state(V,loc(S,L),_),t), t \\ 2 = 0.
#project plan_cell/4.
""",
}

quiet = lambda: contextlib.redirect_stdout(io.StringIO())
with quiet():
    planner = Planner(SPEC, out_path=tempfile.mkdtemp())
G = planner.translation_graph
path = sorted(nx.all_simple_paths(G.graph, G.initial, G.final), key=len)[0]
folder = tempfile.mkdtemp()
with quiet():
    planner.create_asp_instance([a.id for a in G.actors], path, folder)
imax = IMAX if planner._horizon_cap is None else min(IMAX, planner._horizon_cap + 1)
PROJECTIONS["goals"] = "#program check(t).\n" + "".join(f"#project goal{k}/1.\n" for k in range(1, len(path) - 1))

ctl = Control()
ctl.configuration.solve.models = 0
ctl.configuration.solve.parallel_mode = 1
BAN = {"lanes_ban": "plan_lane", "cells_ban": "plan_cell"}.get(METHOD)
if METHOD in PROJECTIONS:
    ctl.configuration.solve.project = "auto"
    ctl.add("check", ["t"], PROJECTIONS[METHOD].split("#program check(t).")[1])
elif BAN:
    # the same derived atoms, without #project, so the constraints below can name them
    rules = PROJECTIONS[METHOD.replace("_ban", "")].split("#program check(t).")[1]
    ctl.add("check", ["t"], "\n".join(l for l in rules.splitlines() if not l.startswith("#project")))
for f in BASE + [os.path.join(folder, "instance.lp")] + RULES:
    ctl.load(f)
ctl.add("check", ["t"], "#external query(t).")

step_every = 60 if METHOD == "step60" else 1
EXTRA = 2  # early stop, as in the planner: at most 2 horizons past the first plan
start, plans, count, first_horizon = time.time(), [], 0, None
for step in range(imax):
    if first_horizon is not None and step > first_horizon + EXTRA:
        break
    parts = [("check", [Number(step)])]
    if step > 0:
        ctl.release_external(Function("query", [Number(step - 1)]))
        parts.append(("step", [Number(step)]))
    else:
        parts.append(("base", []))
    ctl.ground(parts)
    ctl.assign_external(Function("query", [Number(step)]), True)
    if os.environ.get("DIVERSITY_TRACE"):
        print(f"step {step} grounded at {time.time() - start:.1f}s, {len(plans)} plans", file=sys.stderr, flush=True)
    banned_here = 0
    if METHOD == "random":
        tries = 0
        while len(plans) < N and tries < 3 * N:
            tries += 1
            ctl.configuration.solver.seed = str(tries + 1000 * step)
            ctl.configuration.solver.sign_def = "rnd"
            ctl.configuration.solver.rand_freq = "0.3"
            with ctl.solve(yield_=True, async_=True) as handle:
                handle.resume()
                if not handle.wait(BUDGET if first_horizon is not None else None):
                    handle.cancel()
                    break
                model = handle.model()
                if model is None:
                    break
                if first_horizon is None:
                    first_horizon = step
                candidate = MyModel(model)
                count += 1
                if all(candidate != p for p in plans):
                    plans.append(candidate)
        if first_horizon is None:
            continue
        if len(plans) >= N:
            break
        continue
    while len(plans) < N:
        found_one = False
        with ctl.solve(yield_=True, async_=True) as handle:
            while len(plans) < N:
                handle.resume()
                if not handle.wait(BUDGET if first_horizon is not None else None):
                    handle.cancel()  # no further plan within the budget, this horizon is done
                    break
                model = handle.model()
                if model is None:
                    break
                found_one = True
                if BAN:
                    # forbid this plan's lane sequence (or cells) from here on, then solve again
                    atoms = [str(a) for a in model.symbols(atoms=True) if a.name == BAN]
                    banned_here += 1
                    ctl.add(f"ban_{step}_{banned_here}", [], f":- {', '.join(atoms)}." if atoms else "")
                    pending_ban = f"ban_{step}_{banned_here}"
                else:
                    pending_ban = None
                if first_horizon is None:
                    first_horizon = step
                if count % step_every == 0:
                    plans.append(MyModel(model))
                    if os.environ.get("DIVERSITY_TRACE"):
                        print(f"  plan {len(plans)} at {time.time() - start:.1f}s", file=sys.stderr, flush=True)
                count += 1
                if BAN:
                    break  # the new constraint needs grounding before the next solve
        if not (BAN and found_one):
            break
        ctl.ground([(pending_ban, [])])
    if len(plans) >= N:
        break
seconds = round(time.time() - start, 1)

similarity = None
if len(plans) > 1:
    from commonroad_extensions.plan_execution.map_plan import compute_similarity_matrix
    with quiet():
        matrix = np.array(compute_similarity_matrix(plans, up_to_time=float("inf")))
    similarity = round(float(matrix[~np.eye(len(plans), dtype=bool)].mean()), 3)
print(json.dumps({"spec": SPEC.split("/")[-3] if "experiments_src" in SPEC else os.path.basename(SPEC),
                  "method": METHOD, "plans": len(plans), "models_seen": count, "seconds": seconds,
                  "mean_similarity": similarity,
                  "lengths": sorted({p.max_t for p in plans})}))
