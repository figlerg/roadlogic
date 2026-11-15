"""The paper's variability experiment without restarts: the same sampled instances, solved in one open
clingo Control under assumptions.

    python paper_journal/path_modes/sample_assume.py <exp> [conflicts]

<exp> is a variability experiment, e.g. exp_002_b. Its 50 sampled instances are read from the partition
files of the rerun (out/<exp>/partitions, made by run_variability.sh with the paper's seeds). Each fixes
a start (an init(...) fact) and two driving constants. Here the constants are choices
(controller_params.lp) and the injected start is a choice as well, and each instance is a set of
assumptions: its start and constants true, the other starts false. Assumptions need no grounding, so
one Control serves all instances.

At each horizon every instance not yet planned is solved under its assumptions with a budget of
<conflicts> (default 10000). A plan there is taken, so each instance gets its shortest plan, as in the
paper. No plan, or the budget used up, means it is tried again at the next horizon.

SAMPLE_FORGET=varScores,signs makes the solver forget its variable scores and saved signs on every step
(clasp --forget-on-step), keeping the grounding and the learned nogoods. SAMPLE_RANDOM=1 uses random
decision signs with a fresh seed per instance. Both counter the bias of an open solver towards its
previous plan. Prints one JSON line
like diverse.py, with the plans in the order found. Run from the repository root with the venv active.
"""
import contextlib, glob, io, json, os, re, sys, tempfile, time, warnings

sys.path.insert(0, "tests")
warnings.simplefilter("ignore")
import networkx as nx
import numpy as np
from clingo import Control, Function, Number
from clingo.symbol import parse_term
from plan_checks import Planner
from planning.asp.MyModel import MyModel
from commonroad_extensions.plan_execution.map_plan import compute_similarity_matrix

EXP = sys.argv[1]
CONFLICTS = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
SRC = os.path.join("experiments_src", EXP[:-2], "in")
HERE = os.path.dirname(os.path.abspath(__file__))
IMAX, TOTAL = 25, 3600
BASE = [os.path.join("planning", "asp", "encoding", f) for f in ("constants.lp", "facts.lp", "dynamics.lp")]

# the sampled instances: (start atom, brake, accel), from the paper's partition files
instances = []
for f in sorted(glob.glob(os.path.join(HERE, "out", EXP, "partitions", "*.lp"))):
    text = open(f).read()
    const = dict(re.findall(r"#const (\w+) = (-?\d+)\.", text))
    start = re.search(r"^(init\(state\(.*\)\)\))\.", text, re.M).group(1).replace("init_distance", const["init_distance"])
    instances.append((start.replace(" ", ""), int(const["max_braking_speed_while_turning"]),
                      int(const["max_acceleration_while_turning"])))
starts = sorted({s for s, _, _ in instances})

quiet = lambda: contextlib.redirect_stdout(io.StringIO())
with quiet():
    planner = Planner(os.path.join(SRC, "spec.osc"), out_path=tempfile.mkdtemp())
G = planner.translation_graph
path = sorted(nx.all_simple_paths(G.graph, G.initial, G.final), key=len)[0]
folder = tempfile.mkdtemp()
with quiet():
    planner.create_asp_instance([a.id for a in G.actors], path, folder)

ctl = Control()
ctl.configuration.solve.models = 1
ctl.configuration.solve.parallel_mode = 1
FORGET = os.environ.get("SAMPLE_FORGET", "")
RANDOM = os.environ.get("SAMPLE_RANDOM", "0") == "1"
if FORGET:
    ctl.configuration.solver.forget_on_step = FORGET
for f in BASE + [os.path.join(folder, "instance.lp"), os.path.join(HERE, "controller_params.lp"),
                 os.path.join(SRC, "rule_injection.lp")]:
    ctl.load(f)
# the injected starts may be chosen, the assumptions pick exactly one
ctl.add("base", [], "".join(f"{{ {s} }}." for s in starts))
ctl.add("check", ["t"], "#external query(t).")

start_time, plans, found_at, remaining = time.time(), [], [], list(range(len(instances)))
for step in range(IMAX):
    if not remaining or time.time() - start_time > TOTAL:
        break
    ground = [("check", [Number(step)])]
    if step > 0:
        ctl.release_external(Function("query", [Number(step - 1)]))
        ground.append(("step", [Number(step)]))
    else:
        ground.append(("base", []))
    ctl.ground(ground)
    ctl.assign_external(Function("query", [Number(step)]), True)
    ctl.configuration.solve.solve_limit = f"{CONFLICTS},umax"
    for i in list(remaining):
        start, brake, accel = instances[i]
        assumptions = [(parse_term(s), s == start) for s in starts]
        assumptions += [(Function("brake_turn", [Number(brake)]), True),
                        (Function("accel_turn", [Number(accel)]), True)]
        model = None
        if RANDOM:
            ctl.configuration.solver.seed = str(1 + i + 100 * step)
            ctl.configuration.solver.sign_def = "rnd"
        with ctl.solve(assumptions=assumptions, yield_=True) as handle:
            for m in handle:
                model = MyModel(m)
                break
        if model is not None:
            plans.append(model)
            found_at.append(time.time() - start_time)
            remaining.remove(i)
seconds = round(time.time() - start_time, 1)

mean = worst = None
curve = {}
if len(plans) > 1:
    with quiet():
        matrix = np.array(compute_similarity_matrix(plans, up_to_time=float("inf")))
    off = matrix[~np.eye(len(plans), dtype=bool)]
    mean, worst = round(float(off.mean()), 3), round(float(off.max()), 3)
    for k in (5, 10, 20, 30, 40, 50):
        if len(plans) >= k:
            sub = matrix[:k, :k]
            curve[k] = [round(float(sub[~np.eye(k, dtype=bool)].mean()), 3), round(found_at[k - 1], 1)]
print(json.dumps({"spec": EXP[:-2], "method": "sampled_assumptions", "conflicts": CONFLICTS,
                  "forget": FORGET, "random": RANDOM,
                  "instances": len(instances), "plans": len(plans), "seconds": seconds,
                  "seconds_per_plan": round(seconds / max(len(plans), 1), 2),
                  "mean_similarity": mean, "max_similarity": worst,
                  "lengths": sorted({p.max_t for p in plans}), "curve": curve}))
