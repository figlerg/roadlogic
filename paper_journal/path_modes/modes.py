"""Prototype of four ways to plan the paths through a translation graph, measured in one process.

    python paper_journal/path_modes/modes.py <spec> <mode> <n> [early]

mode is first | lazy | spread | live, early is 0 (search every horizon up to IMAX, default) or 1
(once a path has a plan at horizon h, search no further than h + EXTRA). Run from the repository
root with the venv active. specs/par<k>.osc are two cars, each driving k phases in parallel, with 1,
3, 13 and 63 paths for k = 1..4.

Every mode draws plans from the same per-path generator, so they differ only in how they use it:
  first   the first path only, as the HSCC paper
  lazy    paths in turn, one plan each, until n, then a second round. A path asked again is solved
          again from scratch, as a fresh Control would be
  spread  every path solved up front for its share ceil(n / paths), then interleaved
  live    up to MAX_OPEN generators open at once, round-robin, a path closed once it gave its share or
          ran out, the next path opened in its place

Prints one JSON line: time to the first plan, total time, peak memory, paths covered, the mean
pairwise IoU similarity of the plans (the paper's measure, lower is more varied), ASP problems solved.
Paths are tried shortest first.
"""
import contextlib, io, json, os, resource, sys, tempfile, time, warnings

sys.path.insert(0, "tests")
warnings.simplefilter("ignore")
import networkx as nx
import numpy as np
from clingo import Control, Function, Number
from plan_checks import CONTROLLER_LP, Planner
from planning.asp.MyModel import MyModel

SPEC, MODE, N = sys.argv[1], sys.argv[2], int(sys.argv[3])
EARLY = len(sys.argv) > 4 and sys.argv[4] == "1"
IMAX, EXTRA, MAX_OPEN = 12, 2, 8
ENC = os.path.join("planning", "asp", "encoding")
BASE = [os.path.join(ENC, f) for f in ("constants.lp", "facts.lp", "dynamics.lp")]

quiet = lambda: contextlib.redirect_stdout(io.StringIO())
with quiet():
    planner = Planner(SPEC, out_path=tempfile.mkdtemp())
G = planner.translation_graph
paths = sorted(nx.all_simple_paths(G.graph, G.initial, G.final), key=len)
actors = [a.id for a in G.actors]
solved = 0


def plans_on(k):
    """A generator over path k's plans, horizon by horizon, from one Control."""
    global solved
    solved += 1
    folder = tempfile.mkdtemp()
    with quiet():
        planner.create_asp_instance(actors, paths[k], folder)
    imax = IMAX if planner._horizon_cap is None else min(IMAX, planner._horizon_cap + 1)
    ctl = Control()
    ctl.configuration.solve.models = 0
    ctl.configuration.solve.parallel_mode = 1
    for f in BASE + [os.path.join(folder, "instance.lp"), CONTROLLER_LP]:
        ctl.load(f)
    ctl.add("check", ["t"], "#external query(t).")
    first_horizon = None
    for step in range(imax):
        if EARLY and first_horizon is not None and step > first_horizon + EXTRA:
            return
        parts = [("check", [Number(step)])]
        if step > 0:
            ctl.release_external(Function("query", [Number(step - 1)]))
            parts.append(("step", [Number(step)]))
        else:
            parts.append(("base", []))
        ctl.ground(parts)
        ctl.assign_external(Function("query", [Number(step)]), True)
        with ctl.solve(yield_=True) as handle:
            for model in handle:
                if first_horizon is None:
                    first_horizon = step
                m = MyModel(model)
                m.path_k = k
                yield m


def solve(k, quota):
    """Up to quota plans of path k from a fresh generator, which is then dropped."""
    out = []
    for m in plans_on(k):
        out.append(m)
        if len(out) == quota:
            break
    return out


start, first_at = time.time(), None
plans, seen = [], set()


def take(m):
    global first_at
    key = str(sorted(m.holds, key=str))
    if key in seen:
        return
    seen.add(key)
    plans.append(m)
    if first_at is None:
        first_at = time.time() - start


if MODE == "first":
    for m in solve(0, N):
        take(m)
elif MODE == "spread":
    found = [solve(k, -(-N // len(paths))) for k in range(len(paths))]
    while len(plans) < N and any(found):
        for queue in found:
            if queue and len(plans) < N:
                take(queue.pop(0))
elif MODE == "lazy":
    rounds = 1
    while len(plans) < N:
        before = len(plans)
        for k in range(len(paths)):
            got = solve(k, rounds)
            if len(got) >= rounds:
                take(got[rounds - 1])
            if len(plans) >= N:
                break
        if len(plans) == before:
            break
        rounds += 1
elif MODE == "live":
    share = -(-N // len(paths))
    waiting = list(range(len(paths)))
    open_ = {}  # path -> [generator, plans given]
    while len(plans) < N and (open_ or waiting):
        while waiting and len(open_) < MAX_OPEN:
            k = waiting.pop(0)
            open_[k] = [plans_on(k), 0]
        for k in list(open_):
            gen, given = open_[k]
            try:
                before = len(plans)
                take(next(gen))
                open_[k][1] += len(plans) - before
            except StopIteration:
                del open_[k]
                continue
            if open_[k][1] >= share and waiting:
                del open_[k]  # gave its share, make room for a path still waiting
            if len(plans) >= N:
                break
        if not waiting and not open_:
            break

total = round(time.time() - start, 1)
similarity = None
if len(plans) > 1:
    from commonroad_extensions.plan_execution.map_plan import compute_similarity_matrix
    with quiet():
        matrix = np.array(compute_similarity_matrix(plans, up_to_time=float("inf")))
    similarity = round(float(matrix[~np.eye(len(plans), dtype=bool)].mean()), 3)

print(json.dumps({"spec": os.path.basename(SPEC), "mode": MODE, "early": EARLY, "n": N, "paths": len(paths),
                  "plans": len(plans), "first_s": None if first_at is None else round(first_at, 1),
                  "total_s": total,
                  "peak_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024),
                  "paths_covered": len({m.path_k for m in plans}), "mean_similarity": similarity,
                  "asp_problems": solved}))
