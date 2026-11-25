# What changed since the HSCC paper, and what each change did to the results

Every change between the HSCC artifact (branch `artifact-hscc26`, runs from February 2026 in
`experiments_src`) and the current code, with the reason for it and its effect on the benchmark. Numbers
are from `results.md` (benchmark rerun of 2026-11-19, summaries corrected on 2026-11-20) unless a
section names another file. "a/b" is a positive traces out of b simulated, "d" counts positives in which
a car skipped a waypoint it could not reach.

## Summary

| change | kind | effect on the paper's experiments |
|---|---|---|
| 1. strict monitor verdicts | fix | exp_001 0/10 instead of 10/10, exp_001_b 13/50 instead of 50/50. The HSCC numbers were wrong |
| 2. plans end at the last goal | design | planning 2 to 8 times faster. With the paper's simulation settings exp_004 and exp_007 fail (0/10) |
| 3. durations honoured | feature | longer minimum plans where a spec has a duration |
| 4. every path planned | feature | none (each paper spec has one path), identical plans |
| 5. pure OpenSCENARIO specs | design | same plan lengths, exp_007 identical plans, exp_004 faster |
| 6. the speed fix in simulation | fix | none on the paper's experiments (no speeds in their specs) |
| 7. cars keep driving until the simulation ends | design | recovers exp_004 (9/10) and exp_007 (7/10) |
| 8. the summary reads the right column | fix | none on the HSCC results, 29 and 40 wrong verdicts in the reruns, corrected |
| 9. exp_001 spec fix | spec | exp_001 8/10 instead of 0/10, ego now drives the manoeuvre |

## 1. Strict monitor verdicts

**Before.** `Monitor.from_osc2_file` ignored its ring argument and always built the MinMax monitor.
MinMax scores how far a trace is from a guard, and the summary counted a final cost below 0.001 as
positive. For a strict comparison such as `l(ego) < l(car1)` ("ego left of car1") with both cars in one
lane, the distance is 0, so the guard counted as met.

**Now.** A plain satisfied or violated verdict (`TolerantBooleanMonitor`), strict for `<` and `>`, with a
tolerance of 1e-3 for floats and 0.5 for `=` on a position or speed (`EQUALITY_TOLERANCE`, a simulated
speed crosses 6.000 without landing on it).

**Effect.** Only exp_001 flips. On the paper's own traces the current monitor agrees with the paper on
exp_002 to exp_007 and on every variability experiment except exp_001_b (13/50 instead of 50/50).

**Why exp_001 was wrong in the paper.** In all 10 paper runs ego never changes lane: at its last goal
Frenetix finds no kinematically feasible trajectory ("No Kinematic Feasible and Optimal Trajectory") and
removes the car. The plan asks for a lane change within 1 s at 12 m/s. The HSCC monitor accepted every
run at t = 0.2 s, before anything happened, because all guards held with both cars still in one lane.
Checked by running the HSCC monitor code (exported read-only from `artifact-hscc26`) on the same traces.

## 2. Plans end at the last goal

**Before.** Every plan ran two steps past the step at which all goals were met (`PAD_AFTER_GOALS=True`).

**Now.** A plan ends at that step (`PAD_AFTER_GOALS=False`, `planning/Planner.py`, commit 068b972).

**Why.** Planning is 2 to 8 times faster, and the padding had no meaning in the specification.

**Effect.** With the paper's simulation settings, a car that reaches its last waypoint leaves the
simulation, and the monitor cuts the trace at the first moment a car is missing. In exp_007 the plan now
ends at t=4 instead of t=6, the static obstacle leaves at 4 s, before ego has passed it: 0/10 with the
paper's settings. exp_004 likewise (ego leaves at 5.8 s): 0/10. Change 7 removes the cause.

## 3. Durations honoured

`parallel(duration: [3s..20s])` and durations on invocations are encoded in the plan
(`HONOUR_DURATION=True`) and checked by the monitor, with a clock per run for a segment that starts
partway. The HSCC planner ignored them. Effect: a minimum plan length where a spec asks for one.

## 4. Every path planned

A `one_of` gives one path through the automaton per alternative, a `parallel` one path per order in which
its branches end. The HSCC planner planned the first path only, so a spec whose first alternative is
impossible was reported as inconsistent. Now every path is planned (`ROADLOGIC_PATH_MODE=live`). The
paper's experiments have one path each and give identical plans. New examples: `one_of_first_impossible`
(only planning every path finds a plan) 8/10, `one_of_nested` (both sides planned) 8/10. Details:
`paper_journal/path_modes/README.md`.

## 5. Pure OpenSCENARIO specs

exp_004 kept a car in its lane, exp_005 and exp_007 placed a static obstacle, all with hand-written ASP.
Now `keep(car1.lane == 2)`, and for the obstacle `lane(2, at: start)`, `position(30m, at: start)` (20 m in
exp_007) and `keep(obstacle.speed == 0mps)`, in `specs_paper/`. Ego's start is written out (the planner
used to set it silently). The planner takes an obstacle's start from the spec when the spec gives one.
`check_specs_paper.py`: same plan lengths, exp_007 identical plans, exp_004 645 s instead of 899 s for 10
plans. Planning exp_004 in the benchmark: 2731 s in the paper, 304 s now (changes 2 and 5 together).

## 6. The speed fix in simulation

**Before.** A goal could carry a speed window, but Frenetix's velocity planner never reads it: it aims
at the speed that reaches the current goal on time. A simulated car starts from rest, runs late and
speeds up past the speed a spec asks for (10.2 m/s for a requested 6).

**Now.** For cars whose speed the spec constrains, each goal carries a window from the lowest to the
highest planned speed on the way to it, plus or minus 0.5 m/s, and a patched velocity planner clamps its
target into it. Cars the spec says nothing about drive exactly as before (identical traces). Details and
the intermediate versions: `docs/speed-patch-history.md`, demo section 8.

**Effect.** None on the paper's experiments. On the new examples it is part of the difference between
the two columns of `results.md` (together with change 7), for example `keep_lane_modifier` 1/10 to 10/10.

## 7. Cars keep driving until the simulation ends

**Before (HSCC).** A car left the simulation at its last waypoint, or when it passed a waypoint it had
missed. Either cut the monitored trace.

**2026-11-05 to 2026-11-19.** A missed waypoint is skipped and logged (`missed_waypoints.csv`, counted as
"deviated"), and every car kept driving until 2 s after the plan's end.

**Now.** Every car keeps driving until every car is past its last waypoint, at most 10 s after the plan
(`ROADLOGIC_FINAL_SLACK=end`). No car vanishes, and there is no arbitrary extra time.

**Effect.** exp_004 0/10 to 9/10 (all 9 deviated) and exp_007 0/10 to 7/10, exp_007_b 0/39 to 26/39, as
in the paper. Against the fixed 2 s, on the new examples: `one_of_first_impossible` and `one_of_nested`
10/10 to 8/10, `speed_rampup_then_hold` 4/10 to 0/10, the timed hold 1/10 to 0/10, the paper's
experiments unchanged (exp_002_b 38 to 37, exp_003_b 37 to 36). The speed holds lost the extra seconds
in which a car that started from rest caught up with a plan that starts at 6 m/s. See "Open" below.

## 8. The summary reads the right column

**Bug.** `aggregate_monitoring_results.py` took the last column of `monitoring_results.csv` as the final
location. The monitor wrote the locations in set order, which changes with Python's string hashing.

**Fix** (2026-11-20). The monitor writes the locations in a fixed order (initial first, final last), the
summary picks the column labelled final.

**Effect.** The HSCC results: none (0 of 357 traces had the final location elsewhere). The reruns: 29 and
40 wrong verdicts, in the specs with more locations (speed holds, `one_of`, durations), in both
directions. This was the apparent nondeterminism between two runs. After the fix two runs agree on
every positive trace in all 28 experiments: the simulation and the monitor are deterministic.

## 9. exp_001 spec fix

The spec allowed a plan with a lane change within 1 s at 12 m/s, which Frenetix cannot drive.
`specs_variants/exp_001_duration.osc` adds `duration: [2s..5s]` to ego's last phase
(`exp001_variants_2026-11-19.jsonl`, 10 scenarios each):

| variant | positive | ego changes lane |
|---|---|---|
| journal spec | 0/10 | 0/10 |
| with the duration | 8/10 | 10/10 |
| with the duration, speed windows for every car | 8/10 | 10/10 |

Not yet in `specs_paper/`.

## Reproducibility

Planning, simulation and monitoring are deterministic: the same scenario simulated 4 times in a row and
6 times in parallel gives byte-identical traces, and two benchmark runs agree on every verdict. One
source of variation remains: the variability experiments plan each instance with a 100 s wall-clock
limit, as in the paper, so how many instances finish depends on the machine's load (exp_004_b: 6 one
night, 7 the next).

## Open

- **Plans accelerate harder than the simulated cars.** The planner allows a speed change of 8 m/s per
  second (`max_velocity_change_lon` in `planning/asp/encoding/constants.lp`), the simulated cars gain at
  most about 4 m/s in a second (median 3.9, 90th percentile 4.7 over 1044 cars of the rerun). And a plan
  may start at any speed, while every simulated car starts from rest. Starting the simulated cars at the
  plan's speed (`ROADLOGIC_INITIAL_SPEED=plan`, `initial_speed_2026-11-20.jsonl`) helps a little: the speed
  holds 0/10 to 2/10 and 1/10, `keep_speed_modifier` 0/10 to 3/10, `keep_phase_scope` 9/10 to 6/10.
- **Limiting the plans to 4 m/s per second** (`ROADLOGIC_CLASP_ARGS="-c max_velocity_change_lon=4"`,
  `acceleration_2026-11-24.jsonl`, 10 scenarios each, rest and plan as above for comparison):

  | spec | rest | plan | limit 4, rest | limit 4, plan |
  |---|---|---|---|---|
  | duration_nested | 10 (d5) | 10 (d8) | 10 | 10 |
  | exp_001_duration | 8 | 9 | 10 | 10 |
  | exp_002 | 10 | 10 (d2) | 0 | 0 |
  | exp_004 | 9 (d9) | 9 | 7 | 9 |
  | exp_007 | 7 | 7 | 7 | 7 |
  | keep_lane_modifier | 10 | 10 | 10 | 10 |
  | keep_phase_scope | 9 (d7) | 6 | 10 (d2) | 8 |
  | keep_speed_modifier | 0 | 3 | 0 | 1 |
  | one_of_first_impossible | 8 | 8 | 10 | 10 |
  | one_of_nested | 8 | 8 (d1) | 10 | 10 |
  | speed_rampup_then_hold | 0 | 2 | 0 | 3 |
  | speed_rampup_then_hold_timed | 0 | 1 | 0 | 3 |
  | speed_reach_target | 4 | 3 | 5 | 4 |

  The limit removes almost every skipped waypoint and helps most examples, but exp_002 goes from 10/10
  to 0/10, all 10 runs a collision. In every exp_002 plan, with or without the limit, car1 makes the
  last lane change into ego's lane, behind ego. The spec allows that: its last phase only says that ego
  ends in car1's lane. With the limit the plan is two steps longer and ego gets past car1 later. In
  simulation ego runs about 3 m behind its plan, Frenetix starts car1's lane change about a second early,
  and car1 hits ego, which is still beside it. Without the limit ego is 7 m ahead when car1 changes lane.
  So the limit is not a drop-in default. exp_002 shows a gap in the spec (who changes lane at the end)
  and in the simulation (the cars keep the plan's order of goals, not its timing relative to each other).
- **Variability planning got slower** on exp_007_b (92 s in the paper, 1031 s now) and exp_002_b (830 s
  to 1001 s), with the same numbers of plans. Not investigated.
- `keep_speed_modifier` (at most 3/10) and `speed_reach_target` (at most 5/10) fail mostly with every
  setting tried so far, as do the speed holds (at most 3/10).
