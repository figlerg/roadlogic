# Review queue

Things to look at when you have the attention for it. Nothing here is blocking: work continues
without it. Ordered by how much it would hurt to get wrong.

Tick items off as you go. If something is fine, delete the entry.

---

## 0. Start here: the logic worth reading, in order

Everything else in this file is background. This section is the code itself, about 1600 lines
across 9 files. For a live walkthrough of what it does, run `python tests/demo.py`.

### The planner

- [ ] **`planning/Planner.py:224`, `_invocation_keep_rules`.** The heart of the keep feature. A
      keep inside an invocation cannot be a standalone constraint, because a phase has no fixed
      boundaries, so it goes into the goal rule and a split only counts if the keep held over its
      window. Check the window arithmetic: phase k covers `T(k-1)` to `Tk - 1`, and only the last
      phase keeps its closed end. Check the empty-window rule `keep_held(i,t,t-1) :- time(t)`,
      which is what makes a zero-length phase legal.
- [ ] **`planning/Planner.py:172` and `:191`, `_phase_indices` and `_phase_window`.** The mapping
      from a behavior label to phases of the chosen path, including the tuple nodes that parallel
      composition produces. Durations use the closed window, keeps the half-open one. If this
      mapping is wrong, every keep and every duration is wrong.
- [ ] **`planning/Planner.py:203`, `_duration_literals`.** A duration covering phases k1..k2
      becomes `low <= T(k2) - T(k1-1) <= high`. Also returns the horizon cap, which is what makes
      an unsatisfiable duration terminate instead of searching to imax.
- [ ] **`planning/Planner.py:267` onwards, the initial state.** Which actors get a free initial
      velocity, and why a speed constraint must not count towards groundability. This is the part
      most likely to have a case I did not think of.

### Representation and parsing

- [ ] **`planning/intermediate_structure/Constraint.py:797` and `:952`, `Invariant` and
      `StabilityInvariant`.** `asp_violation_bodies` writes each keep as its own negation, which
      is the whole trick for turning an invariant into ASP. `StabilityInvariant` is the one that
      compares two consecutive steps, for `keep_lane()` and a keep against a free parameter.
- [ ] **`planning/parse/TranslationGraphVisitor.py:416`, `_build_keep_invariants`.** What a keep
      body may contain and what it is rejected with. The neighbouring `_build_relational_invariants`
      at `:351` handles `space_gap`.
- [ ] **`planning/parse/TranslationGraphVisitor.py:510`, `visitModifier_application`.** An `at:`
      that is missing now means the invariant form rather than an error, which is where the
      modifier sugar meets the keep machinery. `STABILITY_MODIFIERS` at `:563` is the `keep_lane()`
      and `keep_speed()` desugaring.

### The monitor

- [ ] **`monitoring/Monitor.py:470`, `populate_syma_aut`.** The assembly: guards from the edge
      constraints, keeps folded in, shortcut transitions, self loops. Read it with `:213`
      `guards_for_transition` next to it, which is the rule we agreed on, a keep goes on the edges
      entering its locations and on their self loops, never on the one leaving, with the edge into
      the final location as the exception.
- [ ] **`monitoring/Monitor.py:192`, `skipped_chains`.** Why a step may cross several phases, and
      the cost of it. `MAX_SKIPPED_PHASES` is 2, which is a guess, not a derived number.
- [ ] **`monitoring/Monitor.py:150`, `duration_regions`.** Your current_t idea, plus the check
      that refuses a duration which does not start with the scenario. That refusal is the thing to
      decide about, since it is what the clock work would replace.
- [ ] **`monitoring/Monitor.py:41`, `TolerantBooleanEvaluator`.** The verdict algebra. Boolean
      with a 1e-3 slack on continuous comparisons. Agrees with your MinMax on 5 of 5 benchmark
      traces, where strict boolean flipped 3 of them to negative.
- [ ] **`TimedBooleanMonitor` in `monitoring/Monitor.py`, the clocks.** Used only for a duration
      that does not start with the scenario, which the monitor used to refuse. It tracks
      (location, entry time per open region) instead of one value per location, enters a region's
      clock on the transition into it, and checks `low <= now - start <= high` on the transition out.
      `_clocks_after` is the whole mapping, about twenty lines. Boolean rings only.
      `ROADLOGIC_TIMED_MONITOR=0` restores the refusal. Worth a careful read, since it replaces the
      syma ring's update loop for those specs.
- [ ] **Speed windows, `ROADLOGIC_GOAL_VELOCITY_SOURCE=range` in `map_plan.py`.** For a car whose
      speed the spec constrains, the window spans the lowest to highest speed the plan uses on the
      stretch to the waypoint. `segment` (the average) pinned an accelerating car to half its target
      speed. Recommended default together with `SCOPE=constrained`, see the notebook, sections 8 and 11.
- [ ] **`EQUALITY_TOLERANCE` in `monitoring/Monitor.py`, 0.5, may need tuning.** A required equality
      on a position or a speed now holds within half a unit (0.5 m, 0.5 mps), since a sampled trace
      never lands exactly on a value. Lanes stay exact. Override with
      `ROADLOGIC_EQUALITY_TOLERANCE`. Checked on every simulated run in `demo_output/`: no keep run or
      benchmark trace changes its verdict. Known weak spot: a speed keep on a later segment can pass
      a run that only touched the value once, because its window can shrink to that moment. Only
      clocks fix that, see `tests/demo.ipynb` section 10.
- [ ] **`monitoring/Monitor.py:912`, `add_self_loops`.** One line of real consequence: the initial
      location gets no self loop, so a scenario starts with the trace.

### Execution

- [ ] **`commonroad_extensions/scenario_execution/velocity_patch.py:59`,
      `calculate_desired_velocity`.** The Frenetix replacement. Picks the waypoint the car is
      heading for and clamps to its speed window. This one changes every simulation, so it
      deserves a careful read even though it is short. **Known bad:** in a two-car overtake it
      makes ego rear-end car1 after 2.1s, because the plan's per-step speeds are jerky and the
      patch hands them to Frenetix as hard targets. Without the patch the same run is fine. It
      should be off by default until fixed, see `tests/demo.ipynb` section 8. **Update 2026-10-23:**
      the cause is that the window used the speed a car leaves a waypoint with. A fix behind two
      switches in `map_plan.py` passes the overtake, the speed hold and the benchmark. The default
      as committed crashes the paper benchmark too, so the default needs your decision.
- [ ] **`commonroad_extensions/plan_execution/map_plan.py:250`.** The plan's speed becomes a
      velocity window on each goal state. Measured effect on its own: almost none. It matters
      because the patch above reads it.

## 1. Decisions I made that you have not read back

These are already baked into code and tests. If any is wrong, the cost of finding out later grows.

- [ ] **`docs/keep-spec.md` section 2, keep is temporal.** The reconciliation of 7.3.6.2.3
      (constraints apply to parameters) with 7.6.1 and 7.6.2.3 (consistency over traces). I read
      the parameter restriction as a type-system rule about what may appear on the left of a
      constraint, not about one-shot versus continuous evaluation. This is the load-bearing
      decision for the whole feature.
- [ ] **Section 3, two surfaces for relational invariants.** Canonical is the domain model's
      `space_gap` method, sugar is the `position` modifier with `at: all`. The standard defines
      its own `keep_space_gap` as `position(target, ahead_of: reference, at: all)`, which is why
      the sugar form is not an invention.
- [ ] **Section 7, units.** Your call, recorded: only `m`, `s`, `mps`, no conversion. Worth
      confirming that `mps` rather than `m/s` is acceptable to you. `PHYSICAL_LITERAL` is
      `(FLOAT|INTEGER) IDENTIFIER`, so the unit has to be one identifier token, and `10m/s`
      tokenizes as a division of `10m` by an identifier `s`.
- [ ] **Section 7, `actor.speed` is `Vel_lon`.** The standard's signed-magnitude formula does not
      carry over because `Vel_lat` is lanes per step, a lane-change flag rather than a velocity.

## 1b. Planner settings

- [x] ~~`PAD_AFTER_GOALS`~~ Now False by default: plans end when the goals are met. Checked in the
      full simulation on exp_003, 5 padded and 5 unpadded plans: every agent completed all goals,
      no collision, all 10 runs satisfy the spec. Padded plans end on a collision course just as
      often, padding only moved that two steps later. True reproduces the paper.
- [ ] **`HONOUR_DURATION`**, True. Durations never change which plans are accepted, but they change
      which plans come out first in 3 of the 6 vanilla benchmarks, so rerun experiments will differ
      from the paper. False reproduces the paper instances exactly.

## 2. Open, needs your answer eventually

- [x] ~~DECIDE 3, phase scoping.~~ Settled with your idea: a keep inside an invocation is added
      to the old goal rule, so a split into phases only counts if the keep held while that
      invocation ran. `docs/keep-spec.md` section 6.
- [x] ~~`road_distance_direction` members.~~ Settled: always `longitudinal`, since this tool has
      no lateral distance. `lateral` is rejected saying so.

## 3. Code to read

Ordered by how much judgement went into it.

- [ ] **Keep windows tile the plan.** Your call, and a fix to what I had shipped: a keep on phase
      k covers T(k-1) up to but excluding Tk, and only the last phase keeps its closed end. Before,
      neighbouring phases shared their boundary step, so `keep(lane == 1)` followed by
      `keep(lane == 2)` came out as an inconsistent specification. New test
      `keep_adjacent_phases.osc`. Worth a look since it changes the meaning of every phase-scoped
      keep, though no other test changed its verdict.
- [ ] **`keep_lane()` and `keep_speed()`.** Both become the same "never changes" invariant as
      `keep(car1.lane == car1_lane)`, limited to the invocation they are written in. Written with
      an argument they are rejected. Worth a look: whether `keep_speed_modifier.osc` says what you
      mean by "for the current period".
- [ ] **Top-level serial fix.** A scenario whose top level is a `serial` of labeled invocations
      could not be planned, because the planner looked up the start and end nodes by the names
      `init` and `fin`. It now asks the graph for them. Same one-line change in four places,
      including the verbose mode and `tests/compare_settings.py`.
- [ ] **`04ffd42` feat: honour the duration of compositions and invocations.** A duration covering
      phases k1..k2 becomes `low <= T(k2) - T(k1-1) <= high` in the goal rule, using the same phase
      mapping as the invocation keeps. `HONOUR_DURATION` switches it off and gives the original
      instances back. Worth a look: without padding the top-level maximum also bounds the search.
- [ ] **`603976a` feat: encode keeps inside a behavior invocation in the goal rule.** The keep is a
      literal `keep_held(i,From,To)` in the goal rule, built from `keep_broken(i,t)` by a forward
      chain. `Planner._invocation_keep_rules` has it all. Also widens the final gap in your
      `tests/keep.osc` from 5m..10m to 13m..25m, same reason as keep_scenario_scope.
- [ ] **`2401630` refactor: drop the boundary goal encoding, keep the padding switch.** Together
      with `1e12b90` and the revert `e6dd919` this is an approach that was built, measured and
      dropped. Only the padding switch and `tests/compare_settings.py` survive. Not worth reading
      in detail.
- [ ] **`6774c89` feat: support absolute speed constraints.** The one with real design in it.
      Three changes in `Planner.create_asp_instance`, all because velocity was never a variable
      anywhere in the generated program. Two of them were not in the plan: the legacy `ego`
      anchor also hardcodes `dyn(1,0)` and had to become a choice rule, and `has_absolute` had to
      ignore speed or a speed-only spec drops the anchor without replacing it and fails to
      ground. The commit message spells all of it out.
- [ ] **`aba90f2` fix: physical literals.** The only behaviour change in the whole branch. Specs
      written in `kph` are now rejected where they used to be silently accepted with the unit
      dropped. Also fixes a real bug: `float(''.join(filter(str.isdigit, text)))` turned `1.5m`
      into `15.0`. No `experiments_src` spec used a fractional literal, so the benchmarks were
      never wrong.
- [ ] **`e3ea58b` and `847b9f2`.** Small guard commits. `keep(...)` used to be parsed and
      silently dropped, so a test written against the feature would have passed while testing
      nothing.
- [ ] **`ac24813` feat: encode scenario-scoped keep constraints.** The emission itself is small,
      an invariant becomes an integrity constraint so each relation is written as its negation.
      The parts worth reading are why a scenario-scoped speed keep needs the initial velocity
      freed, and the two test specifications that had to be corrected because they were failing
      for reasons unrelated to keep.
- [ ] **`2f99b73` fix: goal rules and grounding errors.** Two pre-existing bugs. The first made
      clingo reject a whole instance whenever a phase constrained only its start, and it is the
      clingo half of the exp_parallel known issue.
- [ ] **`68e5fd3` test: benchmark regression suite.** Mostly mechanical. The part worth a look is
      that the variability (`_b`) experiments need their partition instances generated first,
      because those carry the `init` facts, and that per-partition UNSAT is a recorded outcome
      rather than a failure.

## 4. Run these yourself

```sh
source venv/bin/activate

# walk one spec through the whole pipeline: source, graph, instance.lp, traces
python tests/run_speed_tests.py speed_start_end.osc -v

# the same thing interactively, plus running checkers by hand and comparing two specs
jupyter lab tests/explore.ipynb

# the boards
python tests/run_speed_tests.py          # 5 passed
python tests/run_keep_tests.py           # 13 passed, 1 pending (slow: proving UNSAT)
python tests/run_duration_tests.py       # 9 passed
python tests/compare_settings.py         # paper vs durations vs no padding, several minutes
python tests/run_keep_tests.py --self-test   # the checkers, against a real plan
python tests/run_experiment_tests.py     # ~10 min, 12 passed 1 xfail 2 skipped
```

- [ ] **`speed_start_end.osc -v`.** The clearest single thing to eyeball. The chain is readable
      end to end: init rule carries `V2 = 5`, `goal1` carries `V1 = 10`, goal time is `T1 = 1`,
      segments advance 0, 5, 15 in step with those velocities.
- [ ] **`tests/explore.ipynb`.** Five cells: pick a spec, explain it, poke at the plans, run
      checkers by hand, compare two specs that should agree.
- [ ] **`--self-test`.** Worth one look because it is the answer to "do the tests actually test
      anything". It was written when every keep case was pending and the checkers would otherwise
      never have executed. It
      runs all of them against a real plan where the verdicts are known from the trace, and
      reports that car1 changes lane in the unconstrained baseline, which is what makes the lane
      cases non-trivial.

## 5. Test intent, do the specs say what you meant

Nineteen specs. The ones where I made a judgement call:

- [ ] **`keep.osc`.** Its keep sits on `c0: car1.drive()`, whose component spans every path edge,
      so its window coincides with the whole scenario even under correct phase semantics. It
      therefore cannot discriminate the two scoping rules. Not a bug, but it means
      `keep_phase_scope.osc` is the one that matters for stage 4.
- [ ] **`keep_inconsistent_nonlocal.osc`.** My construction of 7.6.2.3 case 2, not the standard's
      wording. Minimum gap on one car, the other required to move fast, the follower capped below
      the speed it would need. Check the numbers make it genuinely unsatisfiable for the reason
      intended rather than by accident.
- [ ] **`keep_inconsistent_parallel.osc`.** Two parallel drives on the same actor, which is an
      odd shape. It is the faithful rendering of "conflicts placed on the same actor from
      different scenarios active in parallel", but say if you would write it differently.
- [ ] **Lane 2 is load-bearing** in the lane specs. Lanes are `1..3` and `left_of` maps to `<`, so
      pinning car1 to lane 1 would make the overtake unsatisfiable for a reason unrelated to
      keep. There is a comment saying so.
- [ ] **`ego` in the test specs.** New docs and examples use car1/car2 as you asked, but the specs
      still say `ego` because `Planner.py:175` hardcodes it: a relative-only spec whose actors are
      named anything else cannot ground at all. Renaming is blocked on removing that anchor.

## 6. Finding about the benchmark, not about keep

- [ ] **The canonical overtake is satisfiable partly by accident.** exp_002_b's final phase asks
      for a 5m..10m gap ahead of car1. Merging back into car1's lane is forbidden by the
      right-change rule in `dynamics.lp` unless car1 is more than `safety_distance_back = 7`
      behind ego's previous segment, and a lane change needs `Vel_lon >= min_change_speed = 6`,
      so the post-merge gap is at least 13. exp_002_b only plans because car1 is free to change
      lane and does, baseline trace `[2,2,2,2,2,1,1,1]`, so ego never merges in front of it.
      Holding car1's lane makes the specified maneuver impossible.
      `keep_scenario_scope.osc` uses 13m..25m and is the first spec in the corpus that exercises
      a genuine merge-back. Worth deciding whether the benchmark should too.

## 6b. Monitoring, new and worth your eyes

- [ ] **Simulated speed does not follow the plan.** Measured on `speed_rampup_then_hold.osc`: the
      spec asks for 6mps held, the simulation reaches 9.87mps, and the distance covered per second
      goes 1.77, 5.33, 7.13. Passing the plan's velocity to the motion planner changed almost
      nothing in an A/B run. Every car also starts from a standstill, so a keep on the first
      segment can never hold. Speed keeps are a planning-level guarantee for now.
      `tests/check_speed_fluctuation.py` reports this on any simulated folder.
- [ ] **The default ring is now a boolean one with a tolerance.** Strict boolean called a normal
      overtake trace negative over a 1e-4 miss, where MinMax plus the summary's 1e-3 tolerance had
      always called it positive. `TolerantBooleanMonitor` keeps the plain verdict and the old
      slack. Worth checking you agree with 1e-3.
- [ ] **Durations are monitored, if they start with the scenario.** Your idea: the current time is
      a variable in the valuation, and the bound becomes a guard on the step that ends the region.
      That works for a duration on the top-level composition, which is what every benchmark spec
      uses. A duration on a later phase needs the time its region was entered, which differs
      between the runs the monitor follows at once, so it raises instead of passing quietly.
      Checked on five simulated benchmark traces: still positive, so the bound is not spuriously
      tripping.

## 7. Known issues, no action needed

- [ ] **`docs/known-issues-exp-parallel.md`.** Two pre-existing bugs that keep `exp_parallel` from
      running: a grounding-loop error in `Planner.py` where `remaining.remove(a1)` runs
      unconditionally so the error reports an empty list, and a clingo syntax error in the
      generated instance for `spec_parallel.osc`. The clingo half is now **fixed**: the goal rule
      was emitting `goal2(t) :- time(t), .` for an edge with no constraints, which made clingo
      reject the whole instance. The grounding half remains, and is now precisely diagnosed: an
      actor with an absolute lane but no absolute position cannot be grounded, and nothing can
      anchor to it. Still xfail, so if it ever starts passing the suite reports XPASS and fails.
- [ ] **`exp_004` and `exp_004_b` are skipped by default.** Their planning alone took 2731s and
      12140s in the recorded runs. Not a regression, inherent cost. `--include-slow` runs them.
