"""Plumbing for tests/demo.ipynb: run one specification through the whole pipeline and keep
everything it produces, so a single run can be read from specification to verdict.

Each experiment gets a folder under demo_output/ holding

    spec.osc        the input
    commands.sh     the exact commands that were run, with their settings
    instance.lp     the ASP program generated from the specification
    plan.txt        the plan the solver found, one table per actor
    plan.gif        an animation of that plan, as the solver sees it
    scenario.xml    the CommonRoad scenario handed to the simulator
    simulation.gif  an animation of the simulation
    trace/          what the simulation did per 0.1s: LANE.csv, LONGPOS.csv, CURRV.csv
    monitor.txt     the verdict of checking the trace against the specification

and the raw pipeline output stays under demo_output/_work/<name> for digging.
"""

import inspect
import os
import pickle
import shlex
import shutil
import subprocess
import sys
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "demo_output")

for path in (HERE, os.path.join(ROOT, "monitoring", "syma"), os.path.join(ROOT, "monitoring", "syma-arv")):
    if path not in sys.path:
        sys.path.insert(0, path)

from plan_checks import goal_witnesses, states  # noqa: E402


# The switches that change how a plan is executed. None of them changes the plans themselves.
PAPER = {"ROADLOGIC_GOAL_VELOCITY": "0", "ROADLOGIC_VELOCITY_PATCH": "0"}
RECOMMENDED = {"ROADLOGIC_GOAL_VELOCITY": "1", "ROADLOGIC_VELOCITY_PATCH": "0"}
PATCHED = {"ROADLOGIC_GOAL_VELOCITY": "1", "ROADLOGIC_VELOCITY_PATCH": "1"}
# The fix for the collision in section 8: speed windows from the plan's average speed over each
# stretch, and only for the cars whose speed the specification constrains.
FIX = dict(PATCHED, ROADLOGIC_GOAL_VELOCITY_SOURCE="segment", ROADLOGIC_GOAL_VELOCITY_SCOPE="constrained")


def _make_steps(exp, scenarios):
    out = f"{exp}/out"
    return [
        ("generate-osc-scenarios", [f"OSC_N={scenarios}", f"OSC_FILE={exp}/in/spec.osc",
                                    f"OUTPUT_FOLDER={out}/cr_simulations", f"SCENARIOS_FOLDER={out}",
                                    "STEP_LENGTH=60", f"RULE_INJECTION={exp}/in/rule_injection.lp"]),
        ("execute-all-scenarios", [f"SCENARIOS_FOLDER={out}/cr_scenarios",
                                   f"OUTPUT_FOLDER={out}/cr_simulations"]),
        ("compute-selected-metrics-for-all-scenarios",
         [f"SCENARIOS_FOLDER={out}/cr_scenarios", f"OUTPUT_FOLDER={out}/cr_simulations",
          "selected_metrics=LANE LONGPOS CURRV"]),
        ("animate-all-scenarios", [f"SCENARIOS_FOLDER={out}/cr_scenarios",
                                   f"OUTPUT_FOLDER={out}/cr_simulations"]),
    ]


def run_experiment(name, spec, settings, scenarios=1, force=False):
    """Plan, simulate, animate and monitor one specification. Returns the experiment folder.

    A finished experiment is reused, so re-running the notebook is quick. force=True redoes it.
    """
    folder = os.path.join(OUT, name)
    if os.path.exists(os.path.join(folder, "done")) and not force:
        return folder
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(os.path.join(folder, "trace"))

    exp = os.path.join(OUT, "_work", name)
    shutil.rmtree(exp, ignore_errors=True)
    os.makedirs(os.path.join(exp, "in"))
    shutil.copy(spec, os.path.join(exp, "in", "spec.osc"))
    shutil.copy(spec, os.path.join(folder, "spec.osc"))
    open(os.path.join(exp, "in", "rule_injection.lp"), "w").close()

    env = dict(os.environ, **settings)
    prefix = " ".join(f"{k}={v}" for k, v in settings.items())
    commands = ["# run from the repository root, with the venv active", ""]
    for target, extra in _make_steps(exp, scenarios):
        commands.append(f"{prefix} make {target} \\\n    " + " \\\n    ".join(shlex.quote(a) for a in extra))
        done = subprocess.run(["make", target] + extra, cwd=ROOT, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if done.returncode:
            raise RuntimeError(f"{name}: make {target} failed\n" + done.stdout[-1500:])
    with open(os.path.join(folder, "commands.sh"), "w") as f:
        f.write("\n\n".join(commands) + "\n")

    out = os.path.join(exp, "out")
    sim = os.path.join(out, "cr_simulations", "scenario_0001")
    for source, target in [
        (f"{out}/asp/instance.lp", "instance.lp"),
        (f"{out}/animations/anim_0001.gif", "plan.gif"),
        (f"{out}/cr_scenarios/scenario_0001.xml", "scenario.xml"),
        (f"{sim}/simulation_00001/simulation.gif", "simulation.gif"),
    ]:
        if os.path.exists(source):
            shutil.copy(source, os.path.join(folder, target))
    for metric in ("LANE.csv", "LONGPOS.csv", "CURRV.csv"):
        if os.path.exists(os.path.join(sim, metric)):
            shutil.copy(os.path.join(sim, metric), os.path.join(folder, "trace", metric))

    with open(f"{out}/serialized_models/0001.pkl", "rb") as f:
        with open(os.path.join(folder, "plan.txt"), "w") as g:
            g.write(plan_text(pickle.load(f)))

    with open(os.path.join(folder, "monitor.txt"), "w") as f:
        f.write(monitor_report(spec, sim))
    open(os.path.join(folder, "done"), "w").close()
    return folder


def simulation_folder(name, scenario="scenario_0001"):
    return os.path.join(OUT, "_work", name, "out", "cr_simulations", scenario)


def plan_text(model):
    """The plan as a table per actor, with the goal times and keep windows above it."""
    lines = [f"last step: {model.max_t}",
             f"goal times, one tuple per valid split: {goal_witnesses(model)}"]
    windows = sorted({tuple(p.arguments[:3]) for p in model if p.name == "keep_window"})
    if windows:
        lines.append(f"keep windows (keep, from, to): {windows}")
    lines.append("")
    rows = {}
    for actor, t, segment, lane, v_lon, _v_lat in states(model):
        rows.setdefault(actor, {})[t] = (segment, lane, v_lon)
    for actor in sorted(rows):
        steps = sorted(rows[actor])
        lines += [actor,
                  "  t [s]       " + " ".join(f"{t:>4}" for t in steps),
                  "  position    " + " ".join(f"{rows[actor][t][0]:>4}" for t in steps),
                  "  lane        " + " ".join(f"{rows[actor][t][1]:>4}" for t in steps),
                  "  speed [mps] " + " ".join(f"{rows[actor][t][2]:>4}" for t in steps), ""]
    return "\n".join(lines)


def monitor_verdict(spec, sim_folder, ring=None):
    """'POSITIVE', 'negative', or why the monitor could not decide."""
    from monitoring.Monitor import Monitor
    try:
        mon = Monitor.from_osc2_file(spec) if ring is None else Monitor.from_osc2_file(spec, ring=ring)
        mon.eval_trace(sim_folder, log_name_override="demo_monitor")
    except Exception as exc:
        return f"not checkable: {type(exc).__name__}: {str(exc)[:120]}"
    final = [loc for loc in mon.syma_aut.locations if loc.final][0]
    return "POSITIVE" if not mon.state[final] else "negative"


def monitor_report(spec, sim_folder):
    verdict = monitor_verdict(spec, sim_folder)
    return f"{verdict}\n\nchecked {sim_folder}\nagainst {spec}\n"


def simulation_length(sim_folder):
    """Seconds simulated, read from the lane log."""
    import pandas as pd
    frame = pd.read_csv(os.path.join(sim_folder, "LANE.csv"))
    return float(frame["time"].max())


def show_code(obj, max_lines=40):
    """The source of a function, with its file and line, for showing what changed."""
    lines, start = inspect.getsourcelines(obj)
    path = os.path.relpath(inspect.getsourcefile(obj), ROOT)
    shown = lines[:max_lines]
    body = "".join(f"{start + i:>5}  {line}" for i, line in enumerate(shown))
    more = f"\n       ... {len(lines) - max_lines} more lines" if len(lines) > max_lines else ""
    print(f"{path}:{start}\n\n{body.rstrip()}{more}")


def show_lines(path, keep):
    for line in open(path).read().splitlines():
        if any(k in line for k in keep):
            print(line.strip())


def draw_automaton(spec, title=None):
    """The monitor's view of a spec along its chosen path, left to right.

    Every guard sits on a transition, as in any symbolic automaton. Black is the guard from the
    specification's goals, purple is a keep folded into it. A keep goes on the transition entering
    its location and on that location's self loop, never on the transition leaving it, except that
    the transition into the final location carries the last segment's keep. The initial location has
    no self loop, so a run starts with the trace.
    """
    import matplotlib.pyplot as plt
    import networkx as nx
    from planning.Planner import Planner
    from planning.intermediate_structure.TranslationGraph import flatten_node
    import tempfile

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        graph = Planner(spec, out_path=tempfile.mkdtemp()).translation_graph
    path = next(nx.all_simple_paths(graph.graph, graph.initial, graph.final))

    def keeps_at(node):
        return [str(inv.constraint) if inv.constraint is not None
                else f"{inv.modifier}({inv.actor}) unchanged"
                for inv in sorted(graph.invariants, key=str)
                if inv.scope is not None and inv.scope in flatten_node(node)]

    fig, ax = plt.subplots(figsize=(2.9 * len(path), 3.6))
    for i, node in enumerate(path):
        color = "#2e7d32" if node == graph.initial else "#c62828" if node == graph.final else "#1565c0"
        ax.add_patch(plt.Circle((i, 0), 0.13, color=color, zorder=3))
        label = " | ".join(sorted(flatten_node(node))) if isinstance(node, tuple) else str(node)
        ax.text(i, -0.3, label, ha="center", va="top", fontsize=8)
        if node == graph.initial:
            continue
        # the self loop, drawn above the location, with its guard
        ax.annotate("", xy=(i + 0.07, 0.12), xytext=(i - 0.07, 0.12),
                    arrowprops=dict(arrowstyle="->", lw=1, connectionstyle="arc3,rad=-2.4"))
        loop = keeps_at(node) if node != graph.final else []
        ax.text(i, 0.62, "\n".join(loop) if loop else "true", ha="center", va="bottom", fontsize=7.5,
                color="#6a1b9a" if loop else "black")
    for i, (u, v) in enumerate(zip(path, path[1:])):
        ax.annotate("", xy=(i + 0.87, 0), xytext=(i + 0.13, 0), arrowprops=dict(arrowstyle="->", lw=1.2))
        guard = sorted(str(c) for c in graph[u, v])
        ax.text(i + 0.5, 0.05, "\n".join(guard) if guard else "true", ha="center", va="bottom", fontsize=7.5)
        folded = keeps_at(u) if v == graph.final else keeps_at(v)
        if folded:
            ax.text(i + 0.5, -0.05, "\n".join("and " + k for k in folded), ha="center", va="top",
                    fontsize=7.5, color="#6a1b9a")
    scenario_keeps = [str(inv.constraint) for inv in graph.invariants if inv.scope is None]
    if scenario_keeps:
        ax.text(-0.2, -0.85, "on every transition: " + ", ".join(scenario_keeps), fontsize=8, color="#6a1b9a")
    ax.set_xlim(-0.5, len(path) - 0.5)
    ax.set_ylim(-0.95, 0.95)
    ax.axis("off")
    ax.set_title(title or os.path.basename(spec), fontsize=10)
    fig.tight_layout()
    return fig


def show_images(items, width=430):
    """Show GIFs or PNGs side by side, embedded so the notebook keeps them. items: (title, path)."""
    import base64
    from IPython.display import HTML, display
    cells = []
    for title, path in items:
        if not os.path.exists(path):
            cells.append(f"<td style='vertical-align:top'><b>{title}</b><br>not produced: {path}</td>")
            continue
        kind = "gif" if path.endswith(".gif") else "png"
        data = base64.b64encode(open(path, "rb").read()).decode()
        cells.append(f"<td style='vertical-align:top;text-align:left'><b>{title}</b><br>"
                     f"<img src='data:image/{kind};base64,{data}' width='{width}'></td>")
    display(HTML("<table><tr>" + "".join(cells) + "</tr></table>"))


def draw_monitor_automaton(spec, title=None):
    """The monitor's automaton for a spec, drawn as a timed automaton with every guard written out.

    Each transition is labelled with its guard and, after a slash, its clock resets. t is the current
    time, a clock that is never reset. Every duration that starts later than the scenario gets its own
    clock x, reset to 0 on the transition into its region and checked on the one leaving it, which is
    what the code does with x = current_t - start. Colours tell the sources apart: goals in black,
    keeps in purple, guards on t in teal, clocks in orange.

    Locations are laid out in columns by their distance from the start, alternatives of a one_of one
    above the other. Shortcut transitions are drawn dashed below a graph that is a single path. On a
    branching graph they would bury the picture, so they are returned instead, as fig.shortcuts, a list
    of (from, to, guard) for printing.
    """
    import matplotlib.pyplot as plt
    import networkx as nx
    from matplotlib.patches import FancyArrowPatch
    from monitoring.Monitor import Monitor, covered_locations, duration_regions, skipped_chains

    T = Monitor.from_osc2_file(spec)._translation_graph
    G = T.graph
    keeps = [(covered_locations(inv, G.nodes), inv) for inv in T.invariants]
    anchored, timed = duration_regions(T)
    clock = {k: f"x{k + 1}" for k in range(len(timed))}
    GOAL, KEEP, TIME, CLOCK, GREY = "#1c2228", "#6a1b9a", "#00796b", "#c25e00", "#5a6570"

    def owner(d):
        if d.source.startswith("the invocation "):
            return d.source[len("the invocation "):].replace(".drive", "")
        return d.source.split(":")[0] if ":" in d.source else "scenario"

    def name(node):
        return " | ".join(map(str, node)) if isinstance(node, tuple) else str(node)

    def nice(text):
        import re
        text = re.sub(r"\b([lpv])_(\w+)", r"\1(\2)", text)   # relational constraints print l_car2
        for a, b in ((" == ", " = "), (" <= ", " ≤ "), (" >= ", " ≥ "), (".0 ", " "), (".0)", ")")):
            text = text.replace(a, b)
        return text[:-2] if text.endswith(".0") else text

    def label(source, target, crossed, goals):
        """Lines of (text, colour) for one transition, guard first and resets last."""
        lines = [(nice(g), GOAL) for g in goals]
        last = crossed[-1]
        lines += [(nice(str(inv.constraint)) if inv.constraint is not None
                   else f"{inv.modifier}({inv.actor}) unchanged", KEEP)
                  for covered, inv in keeps if target in covered or (target == T.final and last in covered)]
        lines += [(f"{d.low} ≤ t ≤ {d.high} ({owner(d)})", TIME) for covered, d in anchored
                  if target not in covered and any(n in covered for n in crossed)]
        resets = []
        for k, (covered, d) in enumerate(timed):
            inside = any(n in covered for n in crossed[1:])
            if target in covered and source not in covered:
                resets.append(f"{clock[k]} := 0")
            elif source in covered and target not in covered:
                lines.append((f"{d.low} ≤ {clock[k]} ≤ {d.high}", CLOCK))
            elif inside and target not in covered:
                never = "" if d.low <= 0 <= d.high else ", never true"
                lines.append((f"{d.low} ≤ 0 ≤ {d.high} ({owner(d)} crossed in one sample{never})", CLOCK))
        if not lines:
            lines = [("true", GOAL)]
        if resets:
            lines.append(("/ " + ", ".join(resets), CLOCK))
        return lines

    # layout: a column per distance from the start, branches spread vertically, merges in between
    order = list(nx.topological_sort(G))
    depth, y = {}, {}
    for v in order:
        preds = list(G.predecessors(v))
        depth[v] = 1 + max((depth[p] for p in preds), default=-1)
        if not preds:
            y[v] = 0.0
        elif len(preds) > 1:
            y[v] = sum(y[p] for p in preds) / len(preds)
        else:
            siblings = list(G.successors(preds[0]))
            y[v] = y[preds[0]] + (siblings.index(v) - (len(siblings) - 1) / 2) * 2.5
    x = {v: 3.6 * depth[v] for v in G.nodes}
    linear = all(G.out_degree(v) <= 1 for v in G.nodes)

    chains = list(skipped_chains(G))
    shortcuts = []
    for source, target, chain in chains:
        goals = sorted({str(c) for edge in chain for c in T[edge]})
        lines = label(source, target, [e[0] for e in chain], goals)
        guard = "  ∧  ".join(t for t, _ in lines if not t.startswith("/"))
        reset = " ".join(t for t, _ in lines if t.startswith("/"))
        shortcuts.append((name(source), name(target), (guard + ("  " + reset if reset else "")).strip()))

    low_y, high_y = min(y.values()), max(y.values())
    bottom = low_y - (0.95 + 0.5 * len(chains) if linear else 0.9)
    top = high_y + 2.4
    fig, ax = plt.subplots(figsize=(3.6 * (max(depth.values()) + 1) + 0.6, 1.25 * (top - bottom)))

    def stack(cx, cy, lines, upward=True, size=8.5, box=False):
        for k, (text, colour) in enumerate(lines):
            offset = (len(lines) - 1 - k) * 0.17 if upward else -k * 0.17
            ax.text(cx, cy + offset, text, ha="center", va="bottom" if upward else "top", fontsize=size,
                    color=colour, zorder=5,
                    bbox=dict(facecolor="white", edgecolor="none", pad=0.6) if box else None)

    for v in G.nodes:
        colour = "#2e7d32" if v == T.initial else "#c62828" if v == T.final else "#1565c0"
        ax.add_patch(plt.Circle((x[v], y[v]), 0.22, color=colour, zorder=3))
        ax.text(x[v], y[v] - 0.32, name(v), ha="center", va="top", fontsize=9, fontweight="bold", zorder=5,
                bbox=dict(facecolor="white", edgecolor="none", pad=0.8))
        if v != T.initial:
            ax.add_patch(FancyArrowPatch((x[v] - 0.12, y[v] + 0.18), (x[v] + 0.12, y[v] + 0.18),
                                         connectionstyle="arc3,rad=-2.6", arrowstyle="-|>",
                                         mutation_scale=10, lw=1, color=GREY))
            stack(x[v], y[v] + 0.78, label(v, v, [v], []))
    for u, v in G.edges:
        dx, dy = x[v] - x[u], y[v] - y[u]
        length = (dx ** 2 + dy ** 2) ** 0.5
        ux, uy = dx / length, dy / length
        ax.add_patch(FancyArrowPatch((x[u] + 0.24 * ux, y[u] + 0.24 * uy), (x[v] - 0.24 * ux, y[v] - 0.24 * uy),
                                     arrowstyle="-|>", mutation_scale=12, lw=1.4, color=GOAL))
        stack((x[u] + x[v]) / 2, (y[u] + y[v]) / 2 + 0.08, label(u, v, [u], sorted(str(c) for c in T[u, v])),
              box=not linear)

    if linear:
        for k, (source, target, chain) in enumerate(sorted(chains, key=lambda c: (x[c[0]], x[c[1]]))):
            shift = 0.09 * (k - (len(chains) - 1) / 2)
            x0, x1 = x[source] + shift, x[target] + shift
            level = low_y - (0.75 + 0.5 * k)
            ax.plot([x0, x0, x1, x1], [low_y - 0.22, level, level, low_y - 0.22], ls="--", lw=1, color="#8a959f")
            ax.annotate("", xy=(x1, low_y - 0.22), xytext=(x1, level),
                        arrowprops=dict(arrowstyle="-|>", lw=1, ls="--", color="#8a959f"))
            guard = next(g for s_, t_, g in shortcuts if s_ == name(source) and t_ == name(target))
            ax.text((x0 + x1) / 2, level - 0.05, "shortcut: " + guard, ha="center", va="top", fontsize=7.5,
                    color=GREY, zorder=4, bbox=dict(facecolor="white", edgecolor="none", pad=1.5))

    left = min(x.values()) - 0.4
    legend = [("goal", GOAL), ("keep", KEEP), ("duration from the start, on t", TIME),
              ("later duration, on its own clock", CLOCK)]
    for k, (text, colour) in enumerate(legend):
        ax.text(left + 2.6 * k, top - 0.15, "■ " + text, color=colour, fontsize=8.5, ha="left")
    notes = "= on a position or speed allows ±0.5 · t is the current time · guard / reset"
    if timed:
        notes += " · " + ", ".join(f"{clock[k]} times {owner(d)} ({d.low}..{d.high}s)"
                                    for k, (_, d) in enumerate(timed))
    ax.text(left, top - 0.36, notes, fontsize=8, color=GREY, ha="left")
    if not linear and shortcuts:
        ax.text(left, bottom + 0.15, f"{len(shortcuts)} shortcut transitions not drawn, listed below the figure",
                fontsize=8, color=GREY, ha="left")
    ax.set_xlim(min(x.values()) - 0.8, max(x.values()) + 0.8)
    ax.set_ylim(bottom, top)
    ax.axis("off")
    ax.set_title(title or os.path.basename(spec), fontsize=11)
    fig.tight_layout()
    fig.shortcuts = shortcuts
    return fig


# ---------------------------------------------------------------- section 8: plan speed versus simulation

# one colour per run setting, the same in every section 8 figure
RUN_COLOURS = {"no patch": "#8a959f", "patch as committed": "#c62828", "average": "#c25e00",
               "segment": "#1565c0", "fix": "#00796b"}
PLAN_COLOUR = "#1c2228"


def load_plan(name):
    """The plan a stored run was made from."""
    path = os.path.join(OUT, "_work", name, "out", "serialized_models", "0001.pkl")
    with open(path, "rb") as f:
        return pickle.load(f)


def plan_rows(model, actor):
    """{t: (position, lane, speed)} for one actor of a plan."""
    return {t: (s, lane, v) for a, t, s, lane, v, _ in states(model) if a == actor}


def stored_trace(name, metric):
    """One metric of a stored run (LANE, LONGPOS or CURRV) as a time by car table."""
    import pandas as pd
    from commonroad_extensions.plan_execution.id_hash import decode

    path = os.path.join(OUT, name, "trace", f"{metric}.csv")
    if not os.path.exists(path):
        path = os.path.join(simulation_folder(name), f"{metric}.csv")
    table = pd.read_csv(path).pivot(index="time", columns="agent_id", values=pd.read_csv(path).columns[-1])
    return table.rename(columns=decode)


def scenario_windows(name):
    """{car: [(step, low, high)]}, the waypoints and speed windows a run handed to the simulator.

    `step` is the plan step of the waypoint, low and high are None when it carries no window.
    """
    import xml.etree.ElementTree as ET
    from commonroad_extensions.plan_execution.id_hash import decode

    windows = {}
    for problem in ET.parse(os.path.join(OUT, name, "scenario.xml")).getroot().iter("planningProblem"):
        rows = []
        for goal in problem.iter("goalState"):
            step = int(goal.find("time").find("intervalStart").text) // 10
            velocity = goal.find("velocity")
            low, high = ((float(velocity.find("intervalStart").text), float(velocity.find("intervalEnd").text))
                         if velocity is not None else (None, None))
            rows.append((step, low, high))
        windows[decode(int(problem.get("id")))] = rows
    return windows


def speed_window(model, actor, step, previous, source, tolerance=1.0):
    """The speed window map_plan.py puts on a waypoint, for one GOAL_VELOCITY_SOURCE.

    Mirrors map_plan.py so the sources can be compared on one plan. departure is the speed stored
    at the waypoint, segment the average speed from the previous waypoint, range the lowest to
    highest speed used on that stretch.
    """
    rows = plan_rows(model, actor)
    if source == "departure":
        low = high = rows[step][2]
    elif source == "segment":
        low = high = (rows[step][0] - rows[previous][0]) / (step - previous)
    else:
        used = [rows[k][2] for k in range(previous, step)]
        low, high = min(used), max(used)
    return max(0.0, low - tolerance), max(0.0, high) + tolerance


def plot_plan_legs(model, actor, waypoints, title=None):
    """Position over time of one actor's plan, each one-second leg labelled with the speed driving it.

    In dynamics.lp the position at t is the position at t-1 plus the speed at t-1, so the leg from
    t to t+1 is driven at the speed stored at t. The waypoints handed to the simulator are marked.
    """
    import matplotlib.pyplot as plt

    rows = plan_rows(model, actor)
    steps = sorted(rows)
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    ax.plot(steps, [rows[t][0] for t in steps], "-o", color=PLAN_COLOUR, lw=2, ms=6, zorder=3)
    for t in steps[:-1]:
        mid = ((t + t + 1) / 2, (rows[t][0] + rows[t + 1][0]) / 2)
        ax.annotate(f"{rows[t][2]} m/s", mid, xytext=(-6, 8), textcoords="offset points",
                    ha="right", fontsize=8.5, color="#5a6570")
    for step in waypoints:
        ax.axvline(step, color="#00796b", ls="--", lw=1)
        arrive = rows[step - 1][2]
        ax.annotate(f"waypoint t={step}\narrives at {arrive} m/s\nstored speed {rows[step][2]} m/s",
                    (step, rows[step][0]), xytext=(10, -48), textcoords="offset points", fontsize=8.5,
                    color="#00796b", bbox=dict(facecolor="white", edgecolor="#00796b", pad=3))
    ax.set_xlabel("plan step t [s]")
    ax.set_ylabel("position along the road [m]")
    ax.set_xticks(steps)
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(title or f"{actor}'s plan: each leg is driven at the speed stored where it starts", fontsize=11)
    fig.tight_layout()
    return fig


def plot_speed_windows(model, actors, waypoints, sources=("departure", "segment", "range")):
    """Per car and waypoint, the window each source gives, next to the speeds the plan really uses
    on the stretch leading to that waypoint (grey dots)."""
    import matplotlib.pyplot as plt

    colours = {"departure": RUN_COLOURS["patch as committed"], "segment": RUN_COLOURS["segment"],
               "range": RUN_COLOURS["fix"]}
    panels = [(actor, step, previous) for actor in actors
              for previous, step in zip([0] + list(waypoints[:-1]), waypoints)]
    fig, axes = plt.subplots(1, len(panels), figsize=(2.6 * len(panels) + 0.6, 3.4), sharey=True)
    for ax, (actor, step, previous) in zip(axes, panels):
        rows = plan_rows(model, actor)
        used = [rows[k][2] for k in range(previous, step)]
        ax.scatter([-0.9] * len(used), used, color="#8a959f", s=36, zorder=3)
        for k, source in enumerate(sources):
            low, high = speed_window(model, actor, step, previous, source)
            ax.plot([k, k], [low, high], color=colours[source], lw=7, solid_capstyle="round")
        ax.set_xticks([-0.9] + list(range(len(sources))))
        ax.set_xticklabels(["used"] + list(sources), rotation=35, ha="right", fontsize=8.5)
        ax.set_xlim(-1.5, len(sources) - 0.4)
        ax.set_title(f"{actor}, stretch t={previous}..{step}", fontsize=9.5)
        ax.grid(axis="y", alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("speed [m/s]")
    fig.suptitle("Speed window per waypoint (bars) against the speeds driven on the way there (dots)",
                 fontsize=11)
    fig.tight_layout()
    return fig


def plot_simulated(runs, actors, metric="CURRV", model=None, windows_from=None, ylabel="speed [m/s]",
                   title=None):
    """One panel per car, one line per stored run, with the plan's leg speeds as a dashed staircase
    and the speed windows of `windows_from` as shaded bands. A run that ends early ends in an x."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(actors), figsize=(5.2 * len(actors) + 0.4, 3.5), squeeze=False)
    tables = {label: stored_trace(name, metric) for label, name in runs.items()}
    longest = max(t.index.max() for t in tables.values())
    for ax, actor in zip(axes[0], actors):
        if windows_from:
            previous = 0
            for step, low, high in scenario_windows(windows_from)[actor]:
                if low is not None:
                    ax.fill_between([previous, step + 0.5], low, high, color=RUN_COLOURS["patch as committed"],
                                    alpha=0.12, lw=0)
                    ax.text(previous + 0.1, high + 0.15, f"window {low:g}..{high:g}", fontsize=7.5,
                            color=RUN_COLOURS["patch as committed"])
                previous = step + 0.5
        if model is not None:
            rows = plan_rows(model, actor)
            steps = sorted(rows)
            ax.step(steps, [rows[t][2] for t in steps], where="post", color=PLAN_COLOUR, ls="--", lw=1.3,
                    label="plan (speed of each leg)")
        for k, (label, table) in enumerate(tables.items()):
            if actor not in table:
                continue
            series = table[actor].dropna()
            # earlier runs wider, so a run lying exactly on top of another stays visible
            ax.plot(series.index, series.values, color=RUN_COLOURS.get(label, "#5a6570"),
                    lw=2 + 2.5 * (len(tables) - 1 - k), label=label)
            if series.index.max() < longest - 1:
                ax.plot(series.index[-1], series.values[-1], "x", color=RUN_COLOURS.get(label), ms=11, mew=2.5)
        ax.set_title(actor, fontsize=10)
        ax.set_xlabel("simulated time [s]")
        ax.grid(alpha=0.25)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0][0].set_ylabel(ylabel)
    axes[0][-1].legend(fontsize=8.5, loc="upper left", bbox_to_anchor=(1.01, 1))
    if title:
        fig.suptitle(title, fontsize=11)
    fig.tight_layout()
    return fig


def plot_gap(runs, front, back, car_length=4.5):
    """Distance from `back` to `front` along the road, one line per stored run. Below one car length
    the two bodies overlap, which is a collision while they share a lane."""
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.5, 3.4))
    for label, name in runs.items():
        table = stored_trace(name, "LONGPOS")
        lanes = stored_trace(name, "LANE")
        gap = (table[front] - table[back]).dropna()
        same = (lanes[front] == lanes[back]).reindex(gap.index).fillna(False)
        colour = RUN_COLOURS.get(label, "#5a6570")
        ax.plot(gap.index, gap.values, color=colour, lw=2 + 2.5 * (len(runs) - 1 - list(runs).index(label)),
                label=label)
        ax.plot(gap.index[same], gap.values[same], ".", color=colour, ms=4)
        if gap.index.max() < 4:
            ax.plot(gap.index[-1], gap.values[-1], "x", color=colour, ms=12, mew=2.5)
            ax.annotate(f"collision at {gap.index[-1]:.1f}s", (gap.index[-1], gap.values[-1]), xytext=(12, -4),
                        textcoords="offset points", color=colour, fontsize=9)
    ax.axhspan(-car_length, car_length, color=RUN_COLOURS["patch as committed"], alpha=0.08, lw=0)
    ax.text(0.05, car_length - 0.6, "closer than one car length", fontsize=8, color="#5a6570", va="top")
    ax.axhline(0, color="#5a6570", lw=0.8)
    ax.set_xlabel("simulated time [s]")
    ax.set_ylabel(f"{front} ahead of {back} [m]")
    ax.grid(alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(fontsize=8.5, title="dots: same lane", title_fontsize=8)
    ax.set_title(f"How far {front} is ahead of {back}", fontsize=11)
    fig.tight_layout()
    return fig
