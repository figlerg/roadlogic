# The speed fix: how we got there

The record of how the speed handling in simulation was found and fixed, kept for the paper and for
reference. The demo notebook (`tests/demo.ipynb`, section 8) now only describes what was wrong and
the final version, which is the default since 2026-11-18.

The full section with all its figures is `tests/demo.ipynb` at commit 26efa2d:
`git show 26efa2d:tests/demo.ipynb > /tmp/demo_26efa2d.ipynb`. Its runs are cached in
`demo_output/` (`e7_*`, `e8_*`, `f1_*` to `f3_*`), each with the `commands.sh` that made it.

The versions and their settings:

| version | settings |
|---|---|
| no patch | `ROADLOGIC_VELOCITY_PATCH=0` |
| v1: wrong window | `ROADLOGIC_VELOCITY_PATCH=1 ROADLOGIC_GOAL_VELOCITY_SOURCE=departure ROADLOGIC_GOAL_VELOCITY_SCOPE=all` |
| try 1: no window | `ROADLOGIC_VELOCITY_PATCH=1 ROADLOGIC_VELOCITY_PATCH_MODE=average` |
| try 2: right window, every car | `ROADLOGIC_VELOCITY_PATCH=1 ROADLOGIC_GOAL_VELOCITY_SOURCE=segment ROADLOGIC_GOAL_VELOCITY_SCOPE=all` |
| final as first measured | `ROADLOGIC_VELOCITY_PATCH=1 ROADLOGIC_GOAL_VELOCITY_SOURCE=segment ROADLOGIC_GOAL_VELOCITY_SCOPE=constrained` |
| final, the default | `ROADLOGIC_VELOCITY_PATCH=1 ROADLOGIC_GOAL_VELOCITY_SOURCE=range ROADLOGIC_GOAL_VELOCITY_SCOPE=constrained` |

**Correction (2026-11-18).** The section below and section 7 said Frenetix reads only the first goal
state, so after the first waypoint a car had no speed target. That is not what happens in our pipeline:
MacroAgent hands each car its goals one at a time, and Frenetix aims at the current one. What Frenetix
ignores is the speed window of a goal. Evidence: with the patch on and no windows, traces are identical to
no patch (`e7_speed_without_patch` = `f1_ramp_average`, `e9_benchmark` = `f3_benchmark`,
`s8n_overtake` = `s8_overtake`). Everything the fix changes comes from the windows. The default window is
0.5 m/s wide on each side since 2026-11-18, the monitor's tolerance: with 1.0 a car asked to hold 6 m/s
settled at 6.6 and failed the monitor.

`segment` became `range` after section 11: while the plan accelerates towards a speed the spec asks
for, the average speed of the stretch lies below that speed, and a window around the average holds the
car back. The range from the lowest to the highest speed of the stretch includes it.

## The section as it was

**The story.** The plan says where each car is at every second. The simulator does not get the plan. It
gets a few waypoints: "be here between 4 and 5 s". With the patch from section 7, each waypoint also gets
a **speed window**, "drive between 0 and 2 m/s on the way here", and the simulated car keeps to it.

The first version of the patch was off by one step. It took the window from the speed the plan drives
*after* the waypoint, instead of the speed on the way there. When the plan brakes right after a
waypoint, the car is told to crawl the whole way there. In the overtake from section 1, car1 crawled and
the car behind it ran into it.

**Specs** [keep_scenario_scope.osc](../tests/keep_scenario_scope.osc), the overtake from section 1, and
[speed_rampup_then_hold.osc](../tests/speed_rampup_then_hold.osc), the speed hold from section 7.
**Runs** `demo_output/e8_*` and `f1_*` to `f3_*`, each with its `commands.sh`.

**The error in one picture.** car1's plan, each one-second leg labelled with its speed. car1 drives to its
t=4 waypoint at 8 m/s and brakes to 1 m/s right after it. v1 built the window from the 1.

```python
from demo_pipeline import (load_plan, plot_gap, plot_plan_legs, plot_simulated, plot_versions,
                           scenario_windows, NO_PATCH, V1, NO_WINDOW, ALL_CARS, FINAL)
overtake_plan = load_plan("e8_overtake_with_patch")
show_spec(spec("keep_scenario_scope.osc"), folded=True)
waypoints = [step for step, _, _ in scenario_windows("e8_overtake_with_patch")["car1"]]
plot_plan_legs(overtake_plan, "car1", waypoints)
plt.show()
```

### The versions

Each version decides which speed window a car gets on the way to a waypoint. The pictures show car1's
plan in the overtake (dashed) and the window each version gives it (shaded).

- **no patch.** Frenetix as shipped. It only reads the first waypoint's speed and ignores the rest.
- **v1: wrong window.** The patch as first committed, with the off-by-one error. On the way to t=4, car1
  has to stay below 2 m/s.
- **try 1: no window.** Drop the windows, and only aim to reach each waypoint on time.
- **try 2: right window, every car.** Fix the error: the window comes from the speeds the plan drives
  on the way to the waypoint. Every car gets one.
- **final: right window, where the spec asks.** The same, but only for cars whose speed the spec
  constrains. In the overtake nobody's speed is constrained, so nobody gets a window.

```python
plot_versions(overtake_plan, "car1", [(NO_PATCH, None), (V1, "e8_overtake_with_patch"), (NO_WINDOW, None),
                                      (ALL_CARS, "f2_overtake_segment"), (FINAL, "f3_overtake")])
plt.show()
```

The same five versions on the speed hold from section 7, where the spec says car1 holds 6 m/s. Here the
final version does give a window, because the spec constrains car1's speed.

```python
show_spec(spec("speed_rampup_then_hold.osc"), folded=True)
plot_versions(load_plan("e7_speed_with_patch"), "car1", [(NO_PATCH, None), (V1, "e7_speed_with_patch"), (NO_WINDOW, None),
                                                          (ALL_CARS, "f2_ramp_segment"), (FINAL, "f3_ramp")])
plt.show()
```

### What happened in the simulator

```python
versions = {NO_PATCH: ("e1_keep_one_lane", "e9_benchmark", "e7_speed_without_patch"),
            V1: ("e8_overtake_with_patch", "e8_benchmark_with_patch", "e7_speed_with_patch"),
            NO_WINDOW: ("f1_overtake_average", "f1_benchmark_average", "f1_ramp_average"),
            ALL_CARS: ("f2_overtake_segment", "f2_benchmark_segment", "f2_ramp_segment"),
            FINAL: ("f3_overtake", "f3_benchmark", "f3_ramp")}
bench = os.path.join("experiments_src", "exp_002", "in", "spec.osc")
rows = []
for label, (overtake, benchmark, hold) in versions.items():
    f = simulation_folder(overtake)
    passed = sum(monitor_verdict(bench, simulation_folder(benchmark, s)) == "POSITIVE" for s in ("scenario_0001", "scenario_0002"))
    v = pd.read_csv(os.path.join(simulation_folder(hold), "CURRV.csv")).velocity
    rows.append({"version": label,
                 "overtake (section 1)": "ok" if monitor_verdict(spec("keep_scenario_scope.osc"), f) == "POSITIVE"
                                         else f"fails, crash at {simulation_length(f):.1f} s",
                 "paper's benchmark exp_002": f"{passed} of 2 ok",
                 "hold 6 m/s (section 7)": f"{'ok' if v.max() < 7 else 'too fast'}, peak {v.max():.1f} m/s"})
display(pd.DataFrame(rows).set_index("version"))
```

### Why the final version

Each try fixes one failure and causes another.

- **No window** lets a car race past the speed the spec asks for: 9.9 m/s instead of 6.
- **A window on a car the spec says nothing about** holds it back. Simulated cars start from standstill,
  so they are always a little behind the plan and need to speed up to catch up. A window forbids that,
  which is why try 2 fails the paper's benchmark.

The final version is the only one that passes all three: a window where the spec asks for a speed, and
none anywhere else. I propose making it the default (`ROADLOGIC_VELOCITY_PATCH=1`,
`ROADLOGIC_GOAL_VELOCITY_SOURCE=range`, `ROADLOGIC_GOAL_VELOCITY_SCOPE=constrained`). Right now the patch
is off by default. One detail: these runs took the window from the average speed on the way to the
waypoint. The proposed setting takes the lowest to highest speed instead (`range`), which works better
while a car accelerates (section 11).

### The crash, in pictures

The simulated speed of both cars in three versions. The shaded bands are v1's windows, the same as in
the pictures above. In v1, car1 stays under 2 m/s and ego speeds up as usual.

```python
crash_runs = {NO_PATCH: "e1_keep_one_lane", V1: "e8_overtake_with_patch", FINAL: "f3_overtake"}
plot_simulated(crash_runs, ["car1", "ego"], model=overtake_plan, windows_from="e8_overtake_with_patch",
               title="Simulated speed, the overtake")
plt.show()
```

The distance between the cars. In v1 it shrinks below a car length while they share a lane: the crash
at 2.1 s. In the other versions ego changes lane in time.

```python
plot_gap(crash_runs, "car1", "ego")
plt.show()
show_images([("v1: the collision", f"{OUT}/e8_overtake_with_patch/simulation.gif"),
             ("final", f"{OUT}/f3_overtake/simulation.gif")])
```

**Side note.** [speed_overtake_keep.osc](../tests/speed_overtake_keep.osc) collides with any version at about
7.5 s. Its last goal merges ego back only 5 to 10 m ahead of car1, too close for the motion planner. That
is a problem with the spec. [keep.osc](../tests/keep.osc) had it too, before its gap became 13 to 25 m.
