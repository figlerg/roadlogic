# Planning several paths, and varied plans without restarting the solver

Experiments behind two planner changes for the journal version. Everything here runs from the
repository root with the venv active. Results are JSON lines, one per run, every run kept, failed runs
included.

## 1. Planning every path through the automaton

A `one_of` branches the translation graph, and a `parallel` gives one path per order in which its
branches end their phases. The planner used to plan only the first path. It now plans every path, in
one of three modes (`ROADLOGIC_PATH_MODE`, see `planning/Planner.py`).

| file | what |
|---|---|
| `modes.py`, `run_all.sh` | the four candidate modes (first, lazy, spread, live) on four specs |
| `results_2026-11-13.jsonl` | 64 runs: time to the first plan, total time, memory, paths covered, similarity |
| `compare_paper.py` | the paper's experiments planned by old code, paper mode and new defaults |
| `specs/par<k>.osc` | two cars driving k parallel phases each: 1, 3, 13, 63 paths |

Outcome: `live` (one open solver per path, at most 8, plans taken in turn) is the default. It gives
the first plan as fast as planning one path, and is the only mode that still delivers n plans when most
paths have none. `lazy` was dropped, it re-solves for every extra plan. Early stop (look for more plans
only up to 2 horizons past a path's first plan) removes the long fruitless searches. The paper's
experiments give identical plans under the old code, paper mode and the new defaults.

## 2. Varied plans from one open solver

### The question

The paper takes every 60th model (`diversity_step=60`) to get varied plans, and its variability
experiments (`experiments_src/exp_00*_b`) restart the engine for every plan with sampled parameters.
Is there a principled way to get varied plans fast, from one solver, without restarting it?

### How adding knowledge to a running solver works

clingo's multi-shot API lets a program part be added to a running `Control` and grounded into it
between two solve calls:

```python
ctl.add("ban_7", [], ":- ...")       # a new part
ctl.ground([("ban_7", [])])          # grounding it is what makes it count
# the next ctl.solve(...) sees it, the grounding and what the solver learned stay
```

Rules for added parts: none while a solve is open, they may not redefine an atom an earlier part can
derive (integrity constraints and fresh facts are always fine), and they only see atoms that exist when
they are grounded. The last one matters for the incremental horizon: a constraint grounded at horizon h
does not cover steps added later, so the footprint constraints are guarded by `query(H)` for their
horizon and added again when the horizon grows.

### The methods (all in `diverse.py`, one open solver each)

| method | after each plan, the next must... |
|---|---|
| `step<k>` | (no constraint) every k-th model as it comes. `step60` is the paper's |
| `basic` | differ in the combination of all cars' states at step 1. The BASIC heuristic of `create_scenarios/dynamic_feedback.py` |
| `strict` | differ in every car's state at step 1. The STRICT heuristic |
| `combo` | differ in its start configuration and driving parameters (with `controller_params.lp`) |
| `iou<θ>` | have footprint IoU at most θ with every earlier plan |
| `rise<θ>` | as `iou`, but θ goes up by 0.1 whenever no plan comes within the budget, up to a cap |

`restart_feedback.py` runs `basic` and `strict` as `dynamic_feedback.py` did, restarting the engine
for every plan, as a baseline.

**The footprint and the IoU constraint.** The paper measures similarity as the intersection over union
of the plans' footprints: the set of (position, lane) cells all cars cover over the whole plan, at 1 m,
interpolated between steps (`map_plan.get_covered_cell`). `diverse.py` derives the same cells in ASP,
`fp(X,L,t)`, and after each plan B_k adds its footprint as facts `b_k(X,L)` and the constraint
IoU(A, B_k) <= θ = p/q, rearranged into one linear sum:

```
q |A & B_k| <= p |A | B_k|   <=>   (q+p) |A & B_k| - p |A| <= p |B_k|

:- query(H), level(J), #sum{ q+p,X,L : fp(X,L,_), b_k(X,L) ; -p,X,L : fp(X,L,_) } > p*|B_k|.
```

So every pair of returned plans has similarity at most θ, a guarantee on the measure the paper reports,
with θ the only parameter. This is diverse solution enumeration by iterative solving with distance
constraints, a known ASP technique (Eiter, Erdem, Erdogan, Fink, *Finding similar/diverse solutions in
answer set programming*, TPLP 2013). `level(J)` guards each bound in `rise`, so loosening θ switches the
stricter constraints off.

**The parameter space.** `controller_params.lp` is `create_scenarios/controller.lp` with the two
constants the variability experiments sample (braking and acceleration while turning) turned into
choices over the same values. The start gap is already a choice in every instance. With it, one solver
covers the space the paper sampled.

### Measurement

Mean pairwise similarity with the paper's own matrix code (lower is more varied), plans found, and
time. Because methods differ in how many plans they find, the main comparison is the **variety of the
first k plans and the time until the k-th** (the `curve` field, k = 5..50). For the paper's restarts the
same curve comes from their rerun (`run_variability.sh`, `paper_curves.py`), in sampling order, with the
mean time per plan. Runs used 4 jobs at a time on a 12-core machine, single-threaded clingo each.
Budget per plan 10 s once there is a first plan (never before), early stop 2 horizons unless stated.

### Findings

All tables: `python paper_journal/path_modes/report_diversity.py`, from the result files listed below.

**1. Thinning out (step60) gives almost no variety.** On the overtake (exp_002) all 50 plans of
`diversity_step=60` cover 5 distinct footprints, on exp_005 one. The reason is structural: at the
shortest plan length exp_002 has 3540 plans in total but only 5 distinct footprints, they differ in
speeds that leave no trace in the cells (`count_footprints.py`, `footprints_*.txt`). Variety has to come
from other plan lengths, other start configurations, or other driving parameters.

**2. The paper's restarts get their variety from changing the model.** Each instance fixes a start gap
and two driving constants and is solved from scratch (rerun on the current code with
`run_variability.sh`, `paper_curves_2026-11-15.jsonl`): 0.52 to 0.83 mean similarity, 1.9 to 28 s per
plan. Their plans are as short as the vanilla ones, so the variety comes from the constants.

**3. Your earlier heuristics.** STRICT with restarts returns 50 identical footprints on four specs and
one plan on two. BASIC with restarts reaches 0.47 to 0.96 but takes up to 80 s per plan, and runs out of
time after 22 plans on exp_002 and exp_005 (`restart_2026-11-15.jsonl`). BASIC without restarts
(`diverse_2026-11-15.jsonl`) is 10 to 57 times faster per plan. Its plans are not the same as with
restarts, and neither version is consistently more varied: without restarts 0.70 vs 0.73 on exp_002
and 0.75 vs 0.86 on exp_003, but 0.53 vs 0.47 on exp_001 and 0.67 vs 0.49 on exp_006. Both stay limited
by what step-1 states can express (BASIC finds only 9 plans on exp_007 either way).

**4. The recommendation: `rise0.7` with a conflict budget of 10000.** Each plan must have footprint IoU
at most θ with all earlier ones, θ starts at 0.7 and is loosened by 0.1 when no plan comes within the
budget, up to 1 (no identical footprint). Early stop 2 horizons. Against the paper's restarts
(`conflicts_2026-11-15.jsonl`, `conflicts_extra_2026-11-15.jsonl`), mean similarity over 50 plans and
total time:

| spec | rise0.7, 10000 conflicts | paper's restarts | |
|---|---|---|---|
| exp_001 | **0.48**, 121 s | 0.52, 195 s | more varied, 1.6x faster |
| exp_002 | **0.67**, 559 s | 0.77, 1419 s | more varied, 2.5x faster |
| exp_003 | **0.71**, 209 s | 0.78, 1379 s | more varied, 6.6x faster |
| exp_004 | 0.74, 1330 s, 50 plans | 0.74, 12140 s, 12 plans (archive) | as varied, 4x the plans, 9x faster |
| exp_005 | 0.94, 410 s | **0.83**, 1140 s, 44 plans | less varied, 2.8x faster |
| exp_006 | **0.47**, 13 s | 0.72, 97 s | more varied, 7x faster |
| exp_007 | **0.51**, 20 s, 50 plans | 0.53, 724 s, 39 plans | more varied, 36x faster |

Times are wall-clock with 2 to 4 jobs at a time, so they are approximate. The similarities are exact:
repeated runs return identical plans. exp_004's restart numbers are the paper's archive (the rerun
would take 3.4 h), all others are reruns on the current code.

**5. Why a conflict budget and not seconds.** With a budget in seconds the results depended on machine
load: capped rise on exp_002 gave 20 plans run alone and 4 with three other jobs. clingo's
`solve_limit` counts solver conflicts instead, so reruns return identical plans
(`calibration_exp_002_2026-11-15.txt`). 2000 conflicts is faster but less varied (exp_002 0.83 in 62 s)
and too small for exp_003 (15 plans). 50000 brings no gain over 10000 on exp_002 (0.68).

**6. Measures the constraint does not target** (`independent_2026-11-15.jsonl`). rise0.7 returns 50
distinct footprints everywhere (by construction), more lane-change patterns than the restarts on three
specs (fewer on exp_005), more distinct goal timings on four. The restarts have more distinct start
configurations on four specs, since they sample the start gap by design (on exp_007 the obstacle's
position, where rise0.7 keeps one start).

**7. What did not work, kept for the record.** Projections (`#project` on lanes, cells, goal timings):
varied but slow and rarely reach n (`diversity_2026-11-14.jsonl`). Random restarts on one Control
(other seed, random signs): unreliable, 0.73 in one run and 0.98 in the next. A domain heuristic towards
unused cells: no gain. A fixed IoU bound below 1: few plans on the hard specs. Capping θ below 1 and
allowing longer horizons: very varied (0.46 on exp_002) but only about 20 plans. Turning the driving
constants into choices (`controller_params.lp`) and banning each parameter combination (`combo`): fast
but not more varied, and no gain on exp_005 either.

### Limits and open questions

- exp_005 is the one spec where the restarts stay more varied. Its shortest plans have only 6 distinct
  footprints, and the restarts reach others through the driving constants. Even with those constants as
  choices in one solver, rise0.7 does not find them: 0.93 with 50000 conflicts, with and without the
  parameter space (`conflicts_extra_2026-11-15.jsonl`).
- The IoU constraint optimises the measure the paper reports. Item 6 shows it also does well on others,
  except start configurations.
- The budget is a knob between time and variety. 10000 conflicts worked on all seven specs.
- Not yet in the planner: this is all in `diverse.py`. Moving it into `Planner.plans` (per path, in live
  mode) is a separate step.

### Files

| file | what |
|---|---|
| `diverse.py` | the runner for every method above, one open solver per run |
| `restart_feedback.py` | BASIC and STRICT with a restart per plan, as `dynamic_feedback.py` |
| `controller_params.lp` | the controller with the two sampled driving constants as choices |
| `run_variability.sh`, `paper_curves.py`, `paper_rerun/` | the paper's variability planning rerun, its matrices and times, first-k curves |
| `count_footprints.py`, `footprints_*.txt` | distinct footprints per horizon |
| `independent.py`, `independent_2026-11-15.jsonl` | the measures the constraint does not target |
| `report_diversity.py` | all tables from the result files |
| `run_diverse.sh` -> `diverse_2026-11-15.jsonl` | first grid: 9 methods x 6 specs x 2 horizon settings, 10 s budget |
| `run_final.sh` -> `final_2026-11-15.jsonl` | candidate grid with first-k curves, 10 s budget |
| `run_conflicts.sh` -> `conflicts_2026-11-15.jsonl` | rise0.7 with conflict budgets, 6 specs, 10000 twice |
| `conflicts_extra_2026-11-15.jsonl` | exp_004, and exp_005 with the parameter space and larger budgets |
| `calibration_exp_002_2026-11-15.txt` | budget calibration on exp_002, 2000 / 10000 / 50000, repeated |
| `restart_2026-11-15.jsonl` | BASIC and STRICT with restarts |
| `diversity.py`, `diversity_2026-11-14.jsonl` | first prototype: projections, random restarts, cell bans |
| `diverse_iou.py`, `iou_2026-11-15.jsonl` | first IoU prototype, fixed θ (superseded by `diverse.py`) |

Plans of the reruns go to `out/`, which is not committed (60 MB). Every result file keeps every run,
including those that failed or found few plans.
