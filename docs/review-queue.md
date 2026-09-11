# Review queue

Things to look at when you have the attention for it. Nothing here is blocking: work continues
without it. Ordered by how much it would hurt to get wrong.

Tick items off as you go. If something is fine, delete the entry.

---

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

## 1b. Padding switch, needs your decision

- [ ] **`PAD_AFTER_GOALS`** in `planning/Planner.py`, still True. Turning it off is 2 to 8 times
      faster (`tests/compare_settings.py`). Padding was also doing two jobs by accident. The
      minimum plan length is now done properly by the spec's own `duration`, and
      `keep_inconsistent_nonlocal` passes without padding. What remains is a two-step safety
      lookahead: 1 of 30 benchmark plans ended one step before an unavoidable safety violation.
      Harmless if nothing runs after the last goal. Details in `.claude/PLAN.md`.

## 2. Open, needs your answer eventually

- [x] ~~DECIDE 3, phase scoping.~~ Settled with your idea: a keep inside an invocation is added
      to the old goal rule, so a split into phases only counts if the keep held while that
      invocation ran. `docs/keep-spec.md` section 6.
- [x] ~~`road_distance_direction` members.~~ Settled: always `longitudinal`, since this tool has
      no lateral distance. `lateral` is rejected saying so.

## 3. Code to read

Ordered by how much judgement went into it.

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
