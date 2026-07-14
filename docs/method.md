# Method

This is a working summary of the RoadLogic method, written from the paper source in `docs/paper/` (not tracked in this repo) and cross-checked against the implementation. It exists so that a future session can work on the ASP encoding, the symbolic-automaton translation, or the monitors without needing the paper. Where paper notation maps onto code identifiers, that mapping is given explicitly.

See `ARCHITECTURE.md` for the module map and end-to-end data flow; this document covers only the semantics.

## 1. Pipeline overview

RoadLogic turns an abstract OS2 scenario into a concrete, spec-checked simulation in five stages:

1. **Parse** an OS2 specification into a **symbolic automaton** encoding the behavioral, relational, spatial and timing constraints between actors.
2. **Encode** the automaton as an ASP planning problem, extended with general physics/dynamics constraints.
3. **Solve** with `clingo` to obtain a high-level discrete plan — a sequence of waypoints per actor.
4. **Execute** the plan: map it to a CommonRoad planning problem and refine it into a continuous, physically valid trajectory using the Frenetix motion planner.
5. **Monitor** the resulting trace against the original symbolic automaton (algebraic runtime verification) and reject/regenerate if it does not comply.

The ASP solver decides *what* must happen (maneuver ordering, relational constraints between actors); Frenetix decides *how* it happens in continuous space under vehicle dynamics and road geometry. Because multiple trajectories can satisfy the same high-level plan, RoadLogic controls concretization by enforcing the ASP-derived intermediate goals in sequence and rejecting executions that violate the automaton during monitoring.

## 2. The OS2 subset

Only a fragment of the full OpenSCENARIO 2.1 grammar is supported (`planning/parse/openscenario2.g4` is the complete upstream PMSF grammar; `planning/parse/TranslationGraphVisitor.py` implements visitor methods for a subset of its rules — everything else in the grammar is unhandled).

Actors, positions and lanes: given a set of actors `A = {a_1, ..., a_n}` and a road `road(m)` with `m` lanes (0 = leftmost), each actor `a_i` has a position `pos(a_i)`, velocity `vel(a_i)`, and lane `lane(a_i)`. A state is the tuple of every actor's `(pos, vel, lane)` plus a timestamp `t`. A trace is a (discretized) sequence of states.

Syntax of the supported fragment:

```
scenario := behavior
behavior := atomic | behavior1 . behavior2      (serial)
          | behavior1 || behavior2               (parallel)
          | behavior1 ∪ behavior2                (one_of / choice)
atomic   := drive(actor) | drive(actor): constraint
constraint := (relation(state), at) | constraint1 ∧ constraint2
at       := begin | end
```

`relation` is an n-ary predicate over actor states; `at ∈ {begin, end}` anchors the constraint to the start or end of the segment. In the code, this maps onto `planning/intermediate_structure/Constraint.py`:
- `Modifier.LANE` ('l') / `Modifier.POSITION` ('p') — which physical quantity a constraint refers to.
- `Relation` (`==`, `<=`, `>=`, `<`, `>`, `!=`) — the comparison operator.
- `AbsoluteConstraint(actor, modifier, relation, value)` — actor vs. a constant (e.g. `lane(ego) == 1`).
- `RelativeConstraint(actor_1, actor_2, modifier, relation, c)` — actor vs. actor + offset (e.g. `pos(a) >= pos(b) + c`), corresponding to OS2's `same_as`/`left_of`/`right_of`/`behind`/`ahead_of` modifiers.

Trace semantics (informal): parallel composition (`||`) requires both sub-behaviors to hold over the same interval; serial composition (`.`) splits the interval into two consecutive sub-intervals, one per operand; the choice operator (`∪`) requires at least one operand to hold. `drive(a): γ` requires actor `a` to make continuous forward progress (`pos` strictly increasing at every step) while the constraints `γ` hold at their anchored time (`begin` evaluates at the start of the interval, `end` at its end).

Worked example (`tests/overtake.osc`, three sequential `drive` segments for `ego` relative to `car1`): ego starts behind car1 in the same lane, moves left of car1, gets ahead of car1 longitudinally, then returns to car1's lane in front of it. This is the running example used throughout this document and in the paper.

## 3. Symbolic automaton translation

A symbolic finite automaton (SFA) is a state machine whose transitions are labeled with predicates over (possibly infinite) sets of inputs rather than alphabet letters. Formally, an SFA is `(𝔸, Q, q_0, F, Δ)` where `𝔸` is an effective Boolean algebra over a domain `D` of states, `Q` is a finite set of locations, `q_0` the initial location, `F ⊆ Q` the final locations, and `Δ ⊆ Q × Predicates × Q` the transition relation. A word (a trace) is accepted if there is a chain of predicate-satisfying transitions from `q_0` to some location in `F`.

The translation function `T(·)` from an OS2 behavior to an SFA is defined inductively:

- **Atomic** `drive(γ_1, γ_2)` → a three-location automaton `i → s → f`, with the `i→s` transition guarded by the start constraint `γ_1` and `s→f` guarded by the end constraint `γ_2`.
- **Serial** `φ_1 . φ_2`: given `T(φ_1) = (Q_1, i_1, f_1, Δ_1)` and `T(φ_2) = (Q_2, i_2, f_2, Δ_2)`, merge `f_1` and `i_2` into one location; the result is `(Q_1 ∪ Q_2 \ {f_1, i_2}, i_1, f_2, Δ)`.
- **Parallel** `φ_1 || φ_2`: Cartesian product of the two automata, `(Q_1 × Q_2, (i_1,i_2), (f_1,f_2), Δ_∥)`, with transitions lifted component-wise.
- **One-of** `φ_1 ∪ φ_2`: union of the two automata with shared fresh initial/final locations `i`, `f`.

Worked example: the overtake scenario above translates to a 5-location chain `init → A → B → C → fin` (see `docs/paper/4.2_translation_automaton.tex`, Figure "translation-graph"):
- `init → A`: `p_ego ≤ p_car - 10 ∧ p_ego ≥ p_car - 20 ∧ l_ego = l_car` (ego 10-20m behind car1, same lane)
- `A → B`: `l_ego < l_car` (ego moves to a lower-numbered / left lane)
- `B → C`: `p_car ≤ p_ego - 1 ∧ p_car ≥ p_ego - 10` (ego pulls 1-10m ahead of car1)
- `C → fin`: `l_ego = l_car ∧ p_car ≤ p_ego - 5 ∧ p_car ≥ p_ego - 10` (ego returns to car1's lane, 5-10m ahead)

In code, this automaton is *not* materialized as a separate first-class object during planning — `planning/intermediate_structure/TranslationGraph.py` builds the equivalent structure directly as a `networkx.DiGraph` (nodes = locations, edge data = the set of `Constraint` objects = the transition guard), constructed by `TranslationGraphVisitor` while walking the parse tree. The *same* automaton concept is rebuilt as an actual `syma.SymbolicAutomaton` object (`monitoring/syma/syma/automaton/automaton.py`) by `monitoring/Monitor.py`'s `populate_syma_aut` for the monitoring stage. Both are derived from the same OS2 source and are structurally equivalent, but they are two independent implementations (`TranslationGraph` for planning, `SymbolicAutomaton` for monitoring) rather than one shared object — see `Monitor.from_translation_graph` vs. `Monitor.from_osc2_file` in `monitoring/Monitor.py`.

The automaton serves two purposes: (1) it drives the ASP encoding of the planning problem (§4), and (2) it is the specification the executed trace is checked against (§5).

## 4. ASP encoding

The planning problem is expressed in ASP following standard action-language conventions: fluents (state), actions (with preconditions/effects), and transition rules connecting successive time steps. Each answer set of the grounded program is one feasible high-level plan.

### Incremental (multi-shot) solving

The program is split into three subprograms, solved with `clingo`'s multi-shot API rather than re-grounding from scratch at each horizon:
- `#program base` — static domain facts and constants (`planning/asp/encoding/constants.lp`, `facts.lp`).
- `#program step(t)` — per-timestep dynamics (`planning/asp/encoding/dynamics.lp`).
- `#program check(t)` — goal satisfaction, generated per scenario from the automaton (see below).

`planning/asp/generate_plans.py:generate_plans()` drives this loop directly: it builds a `clingo.control.Control`, grounds `base` once, then repeatedly grounds `step(t)`/`check(t)` for increasing `t` until enough answer sets are found or a max horizon (`imax`) is reached.

### Discretization

Time is integer steps `t = 0, 1, 2, ...` (each representing a fixed real-time unit). The road is a 2D grid: the longitudinal x-axis is distance in meters (**segments**), the lateral y-axis is lane index. Lateral velocity is restricted to `{-1, 0, 1}` lanes/step; longitudinal velocity is non-negative. The ego vehicle starts at `(0,0)` at `t=0`.

### State and action fluents

State: `holds(state(V, loc(S,L), dyn(Vel_lon, Vel_lat)), T)` — vehicle `V` is at segment `S`, lane `L`, with longitudinal/lateral velocity `Vel_lon`/`Vel_lat` at time `T`.

Action: `change_dynamics(V, Delta_Vel_lon, Vel_lat)` — updates longitudinal velocity by an acceleration `Delta_Vel_lon` and sets a new lateral velocity. Exactly one such action occurs per vehicle per step, via the choice rule in `dynamics.lp`:

```
{ occurs(change_dynamics(V, Delta_Vel_lon, Vel_lat), t) :
    acceleration_lon(Delta_Vel_lon), velocity_lat(Vel_lat) } = 1 :- vehicle(V).
```

State transition (also `dynamics.lp`): the new state is derived deterministically from the previous state and the chosen action —

```
holds(state(V, loc(S,L), dyn(Vel_lon,Vel_lat)), t) :-
    holds(state(V, loc(S_prev,L_prev), dyn(Vel_lon_prev,Vel_lat_prev)), t-1),
    occurs(change_dynamics(V, Delta_Vel_lon, Vel_lat), t),
    L = L_prev + Vel_lat_prev,
    S = S_prev + Vel_lon_prev,
    Vel_lon = Vel_lon_prev + Delta_Vel_lon,
    velocity_lon(Vel_lon).
```

### Domain constraints

Enforced as integrity constraints in `dynamics.lp`, independent of the OS2 spec:
1. vehicles must keep moving after initialization (`Vel_lon != 0` for `t != 0`, except a designated `obstacle`);
2. longitudinal/lateral velocities stay within declared bounds (`velocity_lon`, `velocity_lat`);
3. vehicles stay on the road (segment and lane bounds via `segment(S+Vel_lon)`, `lane(L+Vel_lat)`);
4. no lane change within `change_dur` steps of a previous one (`block_duration`/`stay` predicates);
5. collisions/unsafe following distance are forbidden — vehicles on the same lane must keep `|S1-S2|-1 >= safety_distance`; a third check forbids any vehicle occupying a segment strictly between another vehicle's positions at consecutive steps in the same lane.

### From automaton to goal rules

Each automaton edge `(s_{i-1}, γ_i, s_i)` becomes a goal rule enforcing satisfaction of `γ_i` at some time `T_i ≤ t`:

```
goal_i(t) :- query(t), T <= t, gamma_i(T).
```

and the overall scenario goal requires the edges to be satisfied *in order*:

```
goal(T1, ..., Tn, t) :- goal_1(T1), ..., goal_n(Tn), 0 <= T1 <= ... <= Tn <= t.
```

placed in `check(t)` so the multi-shot loop only stops once the full chain is satisfied. In code, this is generated per-scenario (not statically in `encoding/`): `planning/Planner.py:create_asp_instance()` walks the edges of the `TranslationGraph` and calls each `Constraint.asp_goal_format(indices)` (`planning/intermediate_structure/Constraint.py`) to render the concrete literals, writing the result to `instance.lp`. For the overtake example the three goals are: (i) `ego` left of `car1` (`L1 < L2`), (ii) `ego` 1-10m ahead of `car1` (`1 <= S1-S2 <= 10`), (iii) `ego` back in `car1`'s lane, 5-10m ahead (`L1=L2, 5<=S1-S2<=10`) — exactly the `A→B`, `B→C`, `C→fin` edges of §3's automaton.

### From an answer set to a concrete scenario

Each answer set is a set of `holds(state(V, loc(S,L), dyn(Vel_lon,Vel_lat)), T)` facts — read off by `MyModel` (`planning/asp/MyModel.py`) as the sequence of waypoints per vehicle. All vehicles are forced to start from a standstill in the generated CommonRoad planning problem (consistent with common driving-simulator conventions), and the waypoint sequence becomes a chain of intermediate/goal states (`commonroad_extensions/plan_execution/map_plan.py:map_plan`) that Frenetix must visit in order (§5).

## 5. Execution and monitoring

**Execution.** RoadLogic scenarios have *multiple* intermediate goals per actor, which neither the underlying multi-agent CommonRoad simulation platform nor the stock Frenetix motion planner natively support (both assume a single goal, and the platform removes an agent from the simulation once it reaches that goal). RoadLogic's vendored copies of both (`Frenetix-Motion-Planner/`, driven via `commonroad_extensions/scenario_execution/stitched_execution.py`) are extended to: keep an agent in the simulation until its *final* goal is reached, and let an agent recompute its reference path after reaching each intermediate goal. This is how the ASP high-level plan gets refined into a physically-feasible, continuous trajectory that respects vehicle dynamics, road geometry, and the original scenario structure.

**Monitoring.** After execution, the trace (`LANE.csv`/`LONGPOS.csv` per agent) is checked against the *same* symbolic automaton derived from the OS2 spec (§3), using algebraic runtime verification. In code this is `monitoring/Monitor.py`, backed by `monitoring/syma-arv`'s ring implementations:
- `BooleanMonitor` — binary satisfied/violated verdict.
- `MinMaxMonitor` — quantitative min/max robustness-style semantics (the default used by `Monitor.from_osc2_file`).
- `TropicalMonitor` — tropical-semiring semantics.

`Monitor.eval_trace`/`log_monitoring_results` write per-trace verdicts to `monitoring_results.csv`. Separately, `Monitor.invariant_from_plan` checks a plan-level (not trace-level) invariant — did the vehicles actually reach their intended initial/final states per the ASP plan — via a small hand-built 3-location automaton (`init → actor_initial_state_check → actor_final_state_check`), written to `invariant_monitoring_results.csv`. Both are aggregated across a batch of runs by `monitoring/aggregate_monitoring_results.py` into `summary_log.json` (counts of positive traces, timeouts, and cost statistics).

Executions that fail either check are rejected; the pipeline can then be re-run (a new plan/scenario generated) rather than accepting a non-compliant simulation.

## 6. Variation / diversity ("refined strategy")

The ASP solver's incremental (multi-shot, depth-first) search order tends to construct new plans by varying only the *last* time steps of a previously found plan, which biases the set of generated plans toward structurally similar solutions (little diversity in the prefix of the plan). RoadLogic addresses this with a "refined" generation strategy (`create_scenarios/create_variability_instances.py`, `variability_experiments.py`): scenario/model constants (e.g. initial distances, safety margins, blocking durations) are sampled from their valid ranges, and each sample is encoded as a *separate* ASP planning problem (a distinct `instance.lp`/constants override) rather than relying on solver iteration order alone to produce variety. This trades off a lower guaranteed success rate and higher runtime (some parameter samples are infeasible or time out) for substantially higher plan diversity, especially for under-constrained scenarios. Plan diversity itself is measured by an occupancy-grid IoU similarity metric (`commonroad_extensions/plan_execution/map_plan.py:compute_pairwise_similarity`/`compute_progressive_similarity_matrix`).

In the experiment harness (`experiments_src/`), this distinction is encoded directly in directory naming: `exp_00N` runs the baseline/vanilla strategy (`run_vanilla_experiment`), `exp_00N_b` runs the refined/variability strategy (`run_variability_experiment`). See `ARCHITECTURE.md`'s "Fragile" section for caveats about this naming scheme.

## 7. Notation-to-code cross-reference

| Paper notation | Meaning | Code |
|---|---|---|
| `A = {a_1,...,a_n}` | set of actors | `planning/intermediate_structure/Actor.py`, `vehicle(V)` facts |
| `pos(a)`, `vel(a)`, `lane(a)` | actor state components | `loc(S,L)`, `dyn(Vel_lon,Vel_lat)` in `holds/2` facts |
| `road(m)` | road with `m` lanes | `lane(L)` facts, `constants.lp` |
| `drive(a): γ` | atomic behavior with constraint | `Behavior_invocation`/`with` clause, `planning/parse/TranslationGraphVisitor.py` |
| `γ = (P(S), at)` | anchored predicate | `Constraint` subclasses, `Modifier`, `Relation` |
| `φ_1 · φ_2`, `φ_1 ‖ φ_2`, `φ_1 ∪ φ_2` | serial / parallel / one-of composition | `serial`/`parallel`/`one_of` in `visitComposition` |
| `T(φ) = (Q, i, f, Δ)` | symbolic automaton | `TranslationGraph` (planning side); `syma.SymbolicAutomaton` (monitoring side) |
| ASP `holds(state(V,loc(S,L),dyn(Vlon,Vlat)),T)` | discrete state fluent | same literal, `planning/asp/encoding/dynamics.lp`, read via `MyModel.holds` |
| ASP `occurs(change_dynamics(...),t)` | action occurrence | same literal, `dynamics.lp` |
| `goal_i(t)`, `goal(T1,...,Tn,t)` | per-edge / overall goal | generated into `instance.lp` by `Planner.create_asp_instance` + `Constraint.asp_goal_format` |
| `Π_dyn` (dynamics program) | background theory | `planning/asp/encoding/dynamics.lp` |
| `Π_inst` (instance program) | scenario-specific instance | `instance.lp` (generated), `planning/generated/instance.lp` |
| algebraic runtime verification / `M_A(σ)` | trace verdict | `monitoring/Monitor.py` + `monitoring/syma-arv` (`BooleanMonitor`/`MinMaxMonitor`/`TropicalMonitor`) |

## Open questions / not fully resolved

- The paper's goal-assertion example includes an extra `t > T3 + 1` clause beyond what the OS2 spec strictly requires (a leftover from early code to make animations run a bit longer past goal satisfaction). It is unclear from reading the code alone whether this is still present in the current `Planner.create_asp_instance()` output or was removed for spec-compliance — check `planning/Planner.py:create_asp_instance` directly before relying on exact goal-timing behavior.
- Whether `z3` (declared as a dependency, referenced in a commented-out import in `Constraint.py`) is used anywhere live in the constraint/automaton code was not confirmed — see `ARCHITECTURE.md`.
- The precise relationship between the three `controller.lp` files (`planning/controller.lp`, `planning/asp/encoding/controller.lp`, `create_scenarios/controller.lp`) and which is loaded by which entry point was not fully traced — see `ARCHITECTURE.md`.
