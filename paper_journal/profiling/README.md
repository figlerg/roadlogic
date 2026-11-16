# Where planning time goes on long horizons

Run from the repository root with the venv active.

| file | what |
|---|---|
| `profile_horizons.py` | per horizon: grounding time, solving time, ground program size, choices and conflicts. `--budget N` caps each horizon at N conflicts, `--dynamics f.lp` swaps the dynamics encoding |
| `count_rules.py` | ground rules per horizon, split into the goal rule, the controller and the rest |
| `solver_configs.py` | the time to prove there is no plan at one horizon, under a clasp configuration and thread count |
| `dynamics_projected.lp` | `dynamics.lp` with the distance and pass-through constraints over a position-only projection (negative result, see below) |
| `profile_exp_004_2026-11-15.txt` | the profile of exp_004, the slowest paper spec |
| `profile_exp_004_budget_2026-11-16.txt` | the same with 20000 and 5000 conflicts per horizon |
| `solver_configs_2026-11-16.jsonl` | the configuration comparison |

## Findings

**The time goes into proving that no shorter plan exists, not into grounding.** exp_004's shortest
plan has 10 steps. Planning its first plan took 335 s on an idle machine: about 8 s grounding in total,
and 295 s searching at horizons 8 and 9, which have no plan (83 s and 212 s). Finding the plan at
horizon 10 took 20 s.

| horizon | ground s | solve s | rules | conflicts | result |
|---|---|---|---|---|---|
| 7 | 0.9 | 9.9 | 1.0 M | 4751 | no plan |
| 8 | 1.4 | 83.1 | 1.6 M | 32618 | no plan |
| 9 | 2.1 | 211.8 | 2.3 M | 74664 | no plan |
| 10 | 2.4 | 20.0 | 3.3 M | 3705 | plan |

**The ground program grows about cubically, almost entirely from the state expansion.**
`count_rules.py` on exp_002: 0.7 M rules at horizon 5, 2.4 M at 7. The goal rule contributes almost
nothing (goal_k(T) holds at few steps), the controller makes the program smaller (its constraints
prune). The rest is `dynamics.lp`: every reachable state at t-1 combined with every action (17
accelerations by 3 lateral speeds), over a reachable state space that grows each step. That is inherent
to the explicit-state encoding.

**Negative: projecting the states onto positions does not help.** The distance and pass-through
constraints join two or three `holds/2` atoms but only use position and lane. Rewriting them over
`at(V,S,L,t) :- holds(state(V,loc(S,L),_),t)` (`dynamics_projected.lp`) shrinks exp_002 at horizon 5
only from 732k to 720k rules, since reachable states have mostly one speed per position, and it made the
search 25 times slower there (15.3 s vs 0.6 s), because a different program sends the search elsewhere.

**Mixed: skipping expensive horizons.** The plans at any horizon are valid plans. Giving each horizon a
conflict budget, and skipping a horizon that uses it up, gives up the guarantee that the first plan is
the shortest one. On exp_004 with 20000 conflicts per horizon, horizons 8 and 9 are skipped and the plan
at 10 is found with about half the conflicts in total (54k vs 111k). But the plan at 10 itself became
harder to find (13.6k conflicts vs 3.7k), because the full proofs at 8 and 9 had taught the solver
clauses that help at 10. With 5000 conflicts even horizon 10 runs out, everything up to 13 is skipped
and no plan is found. So it depends on a well-chosen budget. The inconsistency verdict ("no plan") would
always need the skipped horizons proved in full. The wall-clock times of these runs are not comparable
with the idle profile above, the machine was busy with other jobs.

**Promising: the clasp configuration.** The time to prove that horizon 9 of exp_004 has no plan, in one
go without the earlier horizons. Two runs at a time on a busy machine, so the times are only a rough
ranking (auto alone took 497 s in an earlier run, 872 s here).

| configuration | threads | seconds |
|---|---|---|
| auto (default) | 1 | 872 |
| frumpy | 1 | over 1500 |
| crafty | 1 | 1169 |
| jumpy | 1 | 830 |
| tweety | 1 | 740 |
| handy | 1 | 450 |
| trendy | 1 | 372 |
| many | 4, compete | 357 |
| auto | 4, compete | 269 |

trendy on one thread is about twice as fast as the default here, and four competing threads about three
times. This is a one-line change (`--configuration=trendy` or `-t 4`), but it is one horizon of one spec
measured under load. Before changing the default, rerun trendy, handy and auto with 1 and 4 threads on an
idle machine over all paper specs, including the satisfiable horizons.
