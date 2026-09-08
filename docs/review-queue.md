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

## 2. Open, needs your answer eventually

- [ ] **DECIDE 3, phase scoping.** `docs/keep-spec.md` section 6. Genuinely open, no
      recommendation from me any more. The earlier draft argued for deferring on grounding cost
      and that argument was wrong: `goal/n` already grounds over every `T_i` tuple. Section 6
      lists three things to settle it, and the middle one is a measurement rather than an
      argument. Only blocks keep stage 4.
- [ ] **`road_distance_direction` members.** Deferred technicality, your call. Members look like
      `longitudinal` and `lateral` with positive meaning ahead-of, read off the `keep_space_gap`
      pseudocode in 8.8 rather than an enum declaration. Confirm against the domain model library
      ZIP before stage 2b treats it as settled. `tests/keep_relational_distance.osc` carries a
      placeholder and a TODO.

## 3. Code to read

Ordered by how much judgement went into it.

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
python tests/run_speed_tests.py          # 1 passed, 4 pending
python tests/run_keep_tests.py           # 14 pending
python tests/run_keep_tests.py --self-test   # the checkers, against a real plan
python tests/run_experiment_tests.py     # ~10 min, 12 passed 1 xfail 2 skipped
```

- [ ] **`speed_start_end.osc -v`.** The clearest single thing to eyeball. The chain is readable
      end to end: init rule carries `V2 = 5`, `goal1` carries `V1 = 10`, goal time is `T1 = 1`,
      segments advance 0, 5, 15 in step with those velocities.
- [ ] **`tests/explore.ipynb`.** Five cells: pick a spec, explain it, poke at the plans, run
      checkers by hand, compare two specs that should agree.
- [ ] **`--self-test`.** Worth one look because it is the answer to "do the tests actually test
      anything". Every keep case is PENDING, so the checkers would otherwise never execute. It
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

## 6. Known issues, no action needed

- [ ] **`docs/known-issues-exp-parallel.md`.** Two pre-existing bugs that keep `exp_parallel` from
      running: a grounding-loop error in `Planner.py` where `remaining.remove(a1)` runs
      unconditionally so the error reports an empty list, and a clingo syntax error in the
      generated instance for `spec_parallel.osc`. Tracked as xfail, so if it ever starts passing
      the suite reports XPASS and fails, and the note cannot rot.
- [ ] **`exp_004` and `exp_004_b` are skipped by default.** Their planning alone took 2731s and
      12140s in the recorded runs. Not a regression, inherent cost. `--include-slow` runs them.
