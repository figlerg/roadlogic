"""Where the time goes per horizon when planning: grounding versus search, and how both grow.

    python paper_journal/profiling/profile_horizons.py <spec> [rule_injection] [--imax 14] [--dynamics f.lp]
        [--budget conflicts]

--budget gives each horizon at most that many solver conflicts. A horizon that uses them up without an
answer is skipped as unknown, so the first plan is no longer guaranteed to be the shortest one.

Plans the shortest path's first plan incrementally, as generate_plans does, and prints per horizon: the
time to ground, the time to solve, the size of the ground program (atoms, rules) and the search
(choices, conflicts), from clingo's statistics. Run from the repository root with the venv active.
"""
import contextlib, io, json, os, sys, tempfile, time, warnings
sys.path.insert(0, "tests")
warnings.simplefilter("ignore")
import networkx as nx
from clingo import Control, Function, Number
from plan_checks import CONTROLLER_LP, Planner

args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and not sys.argv[i - 1].startswith("--")]
SPEC = args[0]
RULES = [CONTROLLER_LP] + args[1:2]
IMAX = int(sys.argv[sys.argv.index("--imax") + 1]) if "--imax" in sys.argv else 14
BUDGET = int(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else 0
DYNAMICS = sys.argv[sys.argv.index("--dynamics") + 1] if "--dynamics" in sys.argv \
    else os.path.join("planning", "asp", "encoding", "dynamics.lp")
with contextlib.redirect_stdout(io.StringIO()):
    planner = Planner(SPEC, out_path=tempfile.mkdtemp())
G = planner.translation_graph
path = sorted(nx.all_simple_paths(G.graph, G.initial, G.final), key=len)[0]
folder = tempfile.mkdtemp()
with contextlib.redirect_stdout(io.StringIO()):
    planner.create_asp_instance([a.id for a in G.actors], path, folder)

ctl = Control(["--stats"])
ctl.configuration.solve.models = 1
if BUDGET:
    ctl.configuration.solve.solve_limit = f"{BUDGET},umax"
for f in [os.path.join("planning", "asp", "encoding", x) for x in ("constants.lp", "facts.lp")] + [DYNAMICS] \
        + [os.path.join(folder, "instance.lp")] + RULES:
    ctl.load(f)
ctl.add("check", ["t"], "#external query(t).")
start = time.time()
print(f"{'h':>3}{'ground s':>10}{'solve s':>10}{'atoms':>10}{'rules':>10}{'choices':>10}{'conflicts':>11}  result")
for step in range(IMAX):
    parts = [("check", [Number(step)])] + ([("step", [Number(step)])] if step else [("base", [])])
    if step:
        ctl.release_external(Function("query", [Number(step - 1)]))
    t0 = time.time()
    ctl.ground(parts)
    t1 = time.time()
    ctl.assign_external(Function("query", [Number(step)]), True)
    result = ctl.solve()
    outcome = "SAT" if result.satisfiable else "UNSAT" if result.unsatisfiable else "skipped (budget)"
    t2 = time.time()
    s = ctl.statistics
    lp, solving = s["problem"]["lp"], s["solving"]["solvers"]
    print(f"{step:>3}{t1 - t0:>10.2f}{t2 - t1:>10.2f}{int(lp['atoms']):>10}{int(lp['rules']):>10}"
          f"{int(solving['choices']):>10}{int(solving['conflicts']):>11}  {outcome}", flush=True)
    if result.satisfiable:
        break
print(f"total {time.time() - start:.1f} s")
