"""How many ground rules each part of the program contributes, per horizon.

    python paper_journal/profiling/count_rules.py <spec> [rule_injection] [--imax 8]

Grounds the instance incrementally up to imax (without solving) three times: as it is, without the goal
rule and its assertions, and without the controller rules, and prints the rule counts. The differences
show which part dominates the growth.
"""
import contextlib, io, os, re, sys, tempfile, warnings
sys.path.insert(0, "tests")
warnings.simplefilter("ignore")
import networkx as nx
from clingo import Control, Function, Number
from plan_checks import CONTROLLER_LP, Planner

args = [a for a in sys.argv[1:] if not a.startswith("--")]
SPEC, INJ = args[0], args[1:2]
IMAX = int(sys.argv[sys.argv.index("--imax") + 1]) if "--imax" in sys.argv else 8
with contextlib.redirect_stdout(io.StringIO()):
    planner = Planner(SPEC, out_path=tempfile.mkdtemp())
G = planner.translation_graph
path = sorted(nx.all_simple_paths(G.graph, G.initial, G.final), key=len)[0]
folder = tempfile.mkdtemp()
with contextlib.redirect_stdout(io.StringIO()):
    planner.create_asp_instance([a.id for a in G.actors], path, folder)
instance = open(os.path.join(folder, "instance.lp")).read()
no_goal = re.sub(r"^(goal\(T.*|:- query\(t\).*)$", "", instance, flags=re.M)
ENC = [os.path.join("planning", "asp", "encoding", x) for x in ("constants.lp", "facts.lp", "dynamics.lp")]


def counts(program, rules):
    ctl = Control(["--stats"])
    for f in ENC + rules:
        ctl.load(f)
    ctl.add("base", [], "")
    path_ = os.path.join(tempfile.mkdtemp(), "i.lp")
    open(path_, "w").write(program)
    ctl.load(path_)
    ctl.add("check", ["t"], "#external query(t).")
    out = []
    for step in range(IMAX):
        parts = [("check", [Number(step)])] + ([("step", [Number(step)])] if step else [("base", [])])
        ctl.ground(parts)
        ctl.solve(assumptions=[(Function("query", [Number(step)]), False)])  # only to fill the statistics
        out.append(int(ctl.statistics["problem"]["lp"]["rules"]))
    return out


full = counts(instance, [CONTROLLER_LP] + INJ)
nog = counts(no_goal, [CONTROLLER_LP] + INJ)
noc = counts(instance, INJ)
print(f"{'h':>3}{'all rules':>12}{'goal rule':>12}{'controller':>12}{'the rest':>12}")
for h in range(IMAX):
    print(f"{h:>3}{full[h]:>12}{full[h] - nog[h]:>12}{full[h] - noc[h]:>12}{full[h] - (full[h] - nog[h]) - (full[h] - noc[h]):>12}")
