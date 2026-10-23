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
