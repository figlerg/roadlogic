"""The time to prove there is no plan at a given horizon, under clasp's configurations and threads.

    python paper_journal/profiling/solver_configs.py <spec> <rule_injection> <horizon> <config> [threads]

Grounds incrementally up to <horizon> without solving the earlier horizons, then solves once at
<horizon>. <config> is a clasp configuration (auto, frumpy, jumpy, tweety, handy, crafty, trendy, many),
[threads] e.g. 4 for a parallel portfolio. Prints one JSON line with the time and the result.
"""
import contextlib, io, json, os, sys, tempfile, time, warnings
sys.path.insert(0, "tests")
warnings.simplefilter("ignore")
import networkx as nx
from clingo import Control, Function, Number
from plan_checks import CONTROLLER_LP, Planner

SPEC, INJ, H, CONFIG = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
THREADS = sys.argv[5] if len(sys.argv) > 5 else "1"
with contextlib.redirect_stdout(io.StringIO()):
    planner = Planner(SPEC, out_path=tempfile.mkdtemp())
G = planner.translation_graph
path = sorted(nx.all_simple_paths(G.graph, G.initial, G.final), key=len)[0]
folder = tempfile.mkdtemp()
with contextlib.redirect_stdout(io.StringIO()):
    planner.create_asp_instance([a.id for a in G.actors], path, folder)
ctl = Control([f"--configuration={CONFIG}", f"--parallel-mode={THREADS}"])
ctl.configuration.solve.models = 1
for f in [os.path.join("planning", "asp", "encoding", x) for x in ("constants.lp", "facts.lp", "dynamics.lp")] \
        + [os.path.join(folder, "instance.lp"), CONTROLLER_LP] + ([INJ] if INJ != "-" else []):
    ctl.load(f)
ctl.add("check", ["t"], "#external query(t).")
for step in range(H + 1):
    parts = [("check", [Number(step)])] + ([("step", [Number(step)])] if step else [("base", [])])
    if step:
        ctl.release_external(Function("query", [Number(step - 1)]))
    ctl.ground(parts)
ctl.assign_external(Function("query", [Number(H)]), True)
t0 = time.time()
result = ctl.solve()
print(json.dumps({"spec": SPEC, "horizon": H, "config": CONFIG, "threads": THREADS,
                  "seconds": round(time.time() - t0, 1), "result": "SAT" if result.satisfiable else "UNSAT"}))
