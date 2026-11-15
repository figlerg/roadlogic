"""How many distinct footprints (the paper's similarity cells) a spec has at its first horizons.

    python paper_journal/path_modes/count_footprints.py <spec> <models per horizon> [rule_injection]

Enumerates up to that many models per horizon, from the first horizon with a plan to 2 beyond it,
and counts the distinct footprints, and the distinct start configurations (states at step 0).
"""
import contextlib, io, os, sys, tempfile, time, warnings
sys.path.insert(0, "tests")
warnings.simplefilter("ignore")
import networkx as nx
from clingo import Control, Function, Number
from plan_checks import CONTROLLER_LP, Planner
from planning.asp.MyModel import MyModel
from commonroad_extensions.plan_execution.map_plan import get_covered_cell

SPEC, LIMIT = sys.argv[1], int(sys.argv[2])
RULES = [CONTROLLER_LP] + sys.argv[3:4]
quiet = lambda: contextlib.redirect_stdout(io.StringIO())
with quiet():
    planner = Planner(SPEC, out_path=tempfile.mkdtemp())
G = planner.translation_graph
path = sorted(nx.all_simple_paths(G.graph, G.initial, G.final), key=len)[0]
folder = tempfile.mkdtemp()
with quiet():
    planner.create_asp_instance([a.id for a in G.actors], path, folder)
ctl = Control()
ctl.configuration.solve.models = 0
for f in [os.path.join("planning", "asp", "encoding", x) for x in ("constants.lp", "facts.lp", "dynamics.lp")] + [os.path.join(folder, "instance.lp")] + RULES:
    ctl.load(f)
ctl.add("check", ["t"], "#external query(t).")
first = None
for step in range(25):
    if first is not None and step > first + 2:
        break
    parts = [("check", [Number(step)])] + ([("step", [Number(step)])] if step else [("base", [])])
    if step:
        ctl.release_external(Function("query", [Number(step - 1)]))
    ctl.ground(parts)
    ctl.assign_external(Function("query", [Number(step)]), True)
    footprints, starts, models, t0 = set(), set(), 0, time.time()
    with ctl.solve(yield_=True) as handle:
        for m in handle:
            plan = MyModel(m)
            footprints.add(frozenset(get_covered_cell(plan, float("inf"))))
            starts.add(tuple(sorted(str(h) for h in plan.holds if h[-1] == 0)))
            models += 1
            if models >= LIMIT:
                break
    if models:
        first = step if first is None else first
        print(f"horizon {step}: {models} models{' (limit)' if models >= LIMIT else ' (all)'}, "
              f"{len(footprints)} distinct footprints, {len(starts)} distinct starts, {time.time() - t0:.1f} s", flush=True)
