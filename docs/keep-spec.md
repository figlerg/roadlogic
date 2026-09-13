# Specification: the `keep` feature

Branch `feature/keep`. See `docs/osc22-keep-reference.md` for the standard, `docs/method.md` for
the existing encoding, `.claude/PLAN.md` for task state.

**DECIDE** means it blocks a stage and needs your answer. **RESOLVED** is settled.

## 1. Goal

Parse `keep(...)`, carry it through the translation graph, enforce it in the ASP encoding, and
detect unsatisfiable invariant sets. The negative cases matter as much as the positive ones.

## 1b. Prerequisite: the `speed` modifier

**Planned as its own commit on `feature/keep`, before the keep work.** Not part of `keep`, but
`keep` needs `Modifier.SPEED` to exist, and speed is worth having on its own. Doing it first keeps
the two diffs separable.

Standard syntax (8.9):

```
speed(speed: speed | speed_range: range of speed
      [, faster_than: physical_object | slower_than: physical_object | same_as: physical_object]
      [, direction: lon_lat] [, <standard-movement-parameters>] [, factor: float])
keep_speed()
```

Initial subset: `speed` and `speed_range` as absolute constraints, and
`faster_than` / `slower_than` / `same_as` as relative ones, mirroring how `lane` already handles
`same_as` / `left_of` / `right_of`. Defer `direction`, `factor`, `acceleration()` and
`change_speed()`. Defer `keep_speed()` to the keep work, since it is the same free-parameter
machinery as `keep_lane()`.

Three concrete blockers in `Planner.py`, all found by reading the emission code:

1. **No velocity variable is bound in goal rules.** `Planner.py:304` emits
   `holds(state(A, loc(S1,L1), dyn(_,_)), t)` with anonymous wildcards, so a speed atom would
   reference an unbound variable. Bind `dyn(V{j+1},_)` **only on edges that actually carry a speed
   constraint**, so every existing `instance.lp` stays byte-identical and the benchmark suite
   cannot regress.
2. **Initial velocity is hardcoded.** `Planner.py:175`, `:227` and `:262` all emit
   `dyn(1,0)` in the `init(...)` rules. `speed(..., at: start)` needs that literal to become a
   variable, constrained by `velocity_lon/1`.
3. **Groundability checks are modifier-string tests.** `Planner.py:217` and `:249` test
   `"l" in mods and "p" in mods` to decide whether an actor can be grounded. `Modifier.SPEED`
   must not count toward that, or an actor with only lane and speed constraints would be treated
   as groundable and produce an underconstrained instance.

Units: settled, section 7. Only m, s and mps, no conversion.

Acceptance: new specs under `tests/` covering absolute value, absolute range, and each of the
three relative forms, checked with the existing `speeds_of` helper. `run_experiment_tests.py`
must still report its baseline board, which blocker 1 is designed to guarantee.

## 2. Semantics: temporal

**RESOLVED 2026-09-07.** A `keep` is an invariant over the trace, holding at every step inside
its window.

The standard is not self-consistent. 7.3.6.2.3 restricts constraints to parameters and rejects
`keep(current_position.x < 100)` on a `var`
([types.html](https://publications.pages.asam.net/standards/ASAM_OpenSCENARIO/ASAM_OpenSCENARIO_DSL/v2.2.0/language-reference/types.html)).
But 7.6.1 defines consistency over **traces**, 7.6.2.3's `keep(speed>10kph)` with
`keep(speed<10kph)` constrains what would be a variable, its non-local example is trivially
satisfiable at any single instant, and the domain model's `keep_lane()` only means anything if
`actor.lane` is read across the trace.

We read 7.3.6.2.3 as a type-system rule about what may appear on the left of a constraint, not
about one-shot versus continuous evaluation.

## 3. Surface syntax

`keep(<bool-expr>)` and `keep(hard <bool-expr>)`. No grammar change needed:
`openscenario2.g4:153` already matches the 2.2.0 EBNF.

| Form | Example | Spec |
|---|---|---|
| lane, literal | `keep(car1.lane == 2)` | `keep.osc`, `keep_scenario_scope.osc` |
| lane, free parameter | `keep(car1.lane == car1_lane)` | `keep_lane_free.osc` |
| speed range | `keep(car1.speed in [5mps..10mps])` | `keep_speed_range.osc` |
| speed comparison | `keep(car1.speed > 3mps)` | `keep_speed_comparison.osc` |
| modifier sugar | `keep_lane()` | `keep_lane_modifier.osc` |
| modifier sugar, speed | `keep_speed()` | `keep_speed_modifier.osc` |
| relational distance | `keep(car2.space_gap(car1, <dir>) in [5m..100m])` | `keep_relational_distance.osc` |
| relational, modifier sugar | `position([5m..100m], behind: car1)` | `keep_relational_modifier.osc` |

Must error clearly, not silently: `keep(lane(0))` (modifier application, not an expression),
`keep(speed: [0..10])` (named-argument form), `keep_lane(2)` (the shorthands take no arguments), `[5..10]` (physical literals need units),
`10kph` (unsupported unit, section 7),
`keep(default ...)` and `remove_default(...)` (deferred, section 9).

**Relational invariants are in scope** (RESOLVED 2026-09-07), in two equivalent surfaces.

The canonical form uses the domain model's own distance methods. `physical_object` (8.7) declares:

```
def space_gap(reference: physical_object, direction: road_distance_direction) -> length
def time_gap(reference: physical_object, direction: road_distance_direction) -> time
def space_headway(reference: physical_object) -> length
def time_headway(reference: physical_object) -> time
def object_distance(reference: physical_object, direction: distance_direction,
                    mode: distance_mode = reference_points) -> length
def road_distance(reference: physical_object, direction: road_distance_direction,
                  mode: distance_mode = reference_points,
                  route_type: on_route_type = on_road) -> length
def time_to_collision(reference: physical_object) -> time
```

All of these parse with our current grammar, positional and named-argument alike, via
`function_application_pe` at `openscenario2.g4:246`. Initial subset: `space_gap` only, since it
is the one that maps onto our segment model without extra machinery. The others should be
rejected with a message naming them as unimplemented rather than unknown.

**Deferred technicality, not needed until stage 2b.** The `direction` argument of `space_gap`
is a `road_distance_direction`. The members are `longitudinal` and `lateral`, and the sign
convention is positive means ahead of the reference, negative means behind. Both are visible in
the standard's semantic clarification for `keep_space_gap` (8.8):

```
if (direction == longitudinal) and (target >= 0):
    position(target, ahead_of: reference, at: all)
else if (direction == longitudinal) and (target < 0):
    position(target, behind: reference, at: all)
```

This is read off the pseudocode rather than from an enum declaration, which is not on the
coordinate-systems or standard-library pages and would come from the domain model library ZIP.
Good enough to proceed on when stage 2b arrives, worth confirming against the ZIP before the
direction argument is treated as settled. `keep_relational_distance.osc` still carries a
placeholder and a TODO.

Worth noting for its own sake: that same pseudocode defines `keep_space_gap` **as**
`position(target, ahead_of: reference, at: all)`. So the sugar form below is not merely
standard-conformant, it is how the standard itself specifies its gap actions. There is also a
`vehicle.keep_space_gap(reference, direction)` action we could support later.

The sugar form is the `position` modifier with `at: all`, which desugars to the same `Invariant`.
This is not a convention we invented: the standard-movement-parameters shared by all modifiers
define `at` as **`all` (default), `start`, or `end`**, and `all` means the constraint applies
throughout. So an `at:`-less modifier already means "over the whole window" per the standard, and
today's mandatory-`at:` assert is the thing that deviates.

```osc
position([10m..20m], behind: car1, at: start)   # point, unchanged
position([5m..100m], behind: car1, at: all)     # invariant, explicit
position([5m..100m], behind: car1)              # invariant, at: all is the default
```

Both surfaces must produce the same `Invariant`, which is what `keep_relational_distance.osc` and
`keep_relational_modifier.osc` check.

Implementation is short because the payload already exists. `RelativeConstraint` with
`Modifier.POSITION` emits exactly the segment-difference atoms a gap constraint needs
(`Constraint.py:200-215`). Only the emission site changes, from inside `goal_i(t)` to a
standalone integrity constraint.

`visitModifier_application` currently asserts `"at" in arg_list` for every modifier. That assert
becomes the point-versus-invariant switch, defaulting to `all` rather than erroring.

## 4. Scoping is the window

Per 7.3.11.2 a constraint lives as long as its declaring instance.

| Placement | Window | Spec |
|---|---|---|
| scenario member | whole trace | `keep_scenario_scope.osc` |
| behavior invocation `with:` | that phase | `keep.osc`, `keep_phase_scope.osc` |
| parallel branch `with:` | that branch, concurrent with siblings | `keep_inconsistent_parallel.osc` |

The third row is the interesting one to implement: two branches can put conflicting invariants on
the same actor, and neither is visible from the other's scope.

## 5. Internal representation

`Constraint.py` has `AbsoluteConstraint` and `RelativeConstraint`. Both are **point** constraints:
`create_asp_instance` folds them into a single `goal_i(t)` rule, true at one solver-chosen step.
Wrong shape for an invariant.

Add a third kind:

```python
class Invariant:
    constraint: BaseConstraint  # Absolute or Relative, reusing the existing payload
    strength: str = "hard"
    scope: Scope                # SCENARIO or a graph edge
```

Wrapping an existing constraint rather than redeclaring actor, modifier, relation and value means
the relational case comes almost free: the wrapped `RelativeConstraint` already knows how to emit
its atoms. `Invariant` supplies the window and the emission site.

Separate class, not a flag, because: emission differs (integrity constraints in
`#program check(t)`, not atoms in `goal_i(t)`), the free-parameter form relates two time steps,
and `create_asp_instance` branches on `isinstance` so a new type keeps those branches honest.

Gotcha: `Modifier` is `LANE = 'l'`, `POSITION = 'p'`. Adding `SPEED` must not disturb
`Planner.py:217` and `:249`, which test `modifier.value` against the literals `"l"` and `"p"` to
decide whether an actor can be grounded.

Desugaring: `keep_lane()` must produce the same `Invariant` as `keep(car1.lane == car1_lane)`,
done in the visitor so one representation reaches the encoding.

## 6. ASP encoding

State is `holds(state(V, loc(S,L), dyn(Vel_lon, Vel_lat)), T)`. Emit into `#program check(t)`,
same place as `create_scenarios/controller.lp`. All examples below are proposals for review.

### For contrast: what a point constraint compiles to today

`lane(same_as: car1, at: start)` with `position([10m..20m], behind: car1, at: start)` on car2
already produces one rule, true at a single solver-chosen step:

```prolog
goal1(t) :- time(t),
   holds(state(car1, loc(S1,L1), dyn(_,_)), t),
   holds(state(car2, loc(S2,L2), dyn(_,_)), t),
   L2 = L1, S1 - S2 >= 10, S1 - S2 <= 20.
```

An invariant is the same atoms in an integrity constraint instead, negated, with no `goal` head.

### Lane, literal value

```prolog
% keep(car1.lane == 2)
:- holds(state(car1, loc(_,L), dyn(_,_)), t), L != 2.
```

### Lane, constant but value free

`car1_lane` is **not** a keyword and nothing in ASP is named after it. It is an ordinary
parameter the author declares in the scenario:

```osc
scenario overtake:
    car1: car
    car2: car
    car1_lane: int          # just a name, could be anything
    keep(car1.lane == car1_lane)
```

Because a parameter holds one value for the lifetime of its instance, "lane equals this
parameter" says the lane never changes, without saying which lane. That is the whole trick, and
it is how the domain model defines `keep_lane()`: `lane = actor.lane` then
`keep(actor.lane == lane)`.

The parameter never reaches ASP. We compile the meaning directly, as step-to-step stability:

```prolog
% keep(car1.lane == car1_lane), and equally keep_lane() on car1
:- holds(state(car1, loc(_,L1), dyn(_,_)), t),
   holds(state(car1, loc(_,L2), dyn(_,_)), t-1), time(t-1), L1 != L2.
```

The same shape gives `keep_speed()`:

```prolog
:- holds(state(car1, loc(_,_), dyn(V1,_)), t),
   holds(state(car1, loc(_,_), dyn(V2,_)), t-1), time(t-1), V1 != V2.
```

### Speed, comparison

With mps mapping one to one onto `Vel_lon`, the literal is the constant. Only the strictness
needs care:

```prolog
% keep(car1.speed > 10mps), allowed is Vel_lon > 10, so forbid Vel_lon <= 10
:- holds(state(car1, loc(_,_), dyn(Vel_lon,_)), t), Vel_lon <= 10.
```

### Speed, range

An `in` constraint becomes two rules:

```prolog
% keep(car1.speed in [5mps..10mps])
:- holds(state(car1, loc(_,_), dyn(V,_)), t), V < 5.
:- holds(state(car1, loc(_,_), dyn(V,_)), t), V > 10.
```

### Relational distance

car2 stays between 5m and 100m behind car1. Both surfaces compile to the same pair:

```prolog
% keep(car2.space_gap(car1, <dir>) in [5m..100m])
% position([5m..100m], behind: car1, at: all) on car2
:- holds(state(car1, loc(S1,_), dyn(_,_)), t),
   holds(state(car2, loc(S2,_), dyn(_,_)), t), S1 - S2 < 5.
:- holds(state(car1, loc(S1,_), dyn(_,_)), t),
   holds(state(car2, loc(S2,_), dyn(_,_)), t), S1 - S2 > 100.
```

These are the atoms `RelativeConstraint.asp_goal_format` already produces for `Modifier.POSITION`.
Only the surrounding rule changes.

### Relative speed

From the speed modifier work, section 1b:

```prolog
% speed(faster_than: car2, at: all) on car1
:- holds(state(car1, loc(_,_), dyn(V1,_)), t),
   holds(state(car2, loc(_,_), dyn(V2,_)), t), V1 <= V2.
```

### An inconsistent pair

Nothing special is emitted for detection. Two invariants that cannot both hold simply produce two
integrity constraints with no model, because `dynamics.lp` gives car1 exactly one state per step:

```prolog
% keep(car1.lane == 2) and keep(car1.lane == 1) together
:- holds(state(car1, loc(_,L), dyn(_,_)), t), L != 2.
:- holds(state(car1, loc(_,L), dyn(_,_)), t), L != 1.
```

**RESOLVED 2026-09-11, phase scoping: the keep goes into the goal rule.**

A phase has no fixed boundaries: `goal_i(t)` can hold at many steps, and `goal(T1,...,Tn,t)` only
asks that some ordered split exists. So a keep inside an invocation cannot be a standalone
constraint. It is added to the goal rule instead, and a split only counts if every such keep held
over its invocation's steps:

```prolog
goal(T1,T2,t) :- goal1(T1), goal2(T2), 0 <= T1<=T2 <= t, t > T2 + 1, keep_held(1,T1,T2).

keep_broken(1,t) :- holds(state(car1, loc(_,X), dyn(_,_)), t), X != 2.
keep_held(1,t,t) :- time(t), not keep_broken(1,t).
#program step(t).
keep_held(I,Ta,t) :- keep_held(I,Ta,t-1), not keep_broken(I,t).
```

Phase k is the k-th node of the chosen path, from `T(k-1)` to `Tk` with `T0 = 0`. After parallel
composition a node is a tuple of component states, so an invocation covers the consecutive
phases whose node contains it. `keep_window(i,From,To,t)` records the steps a keep covered, for
tests and the verbose mode. It carries the horizon t like `goal/n`, since incremental solving does
not allow the same atom to be defined at two horizons.

Specs without such keeps get exactly the original instance. An alternative with an explicit
phase choice was built and dropped: it accepted the same plans but was slower and changed the plan
order.

Limitation: with padding on, the two steps after the last goal lie outside every invocation, so a
keep inside an invocation does not cover them. A keep for the whole scenario does.

### Blocker: `ego` is currently a hardcoded actor name

`Planner.py:175` seeds `grounded = {'ego'}` and emits `init(state(ego, loc(0,2), dyn(1,0)))`
whenever an edge carries no absolute constraint. A relative-only spec whose actors are named
anything else cannot ground at all: everything waits to attach to an `ego` that does not exist,
the loop makes no progress, and it dies with the same
`Could not ground all actors` error as exp_parallel. Verified on a two-actor car1/car2 spec.

This is why the test specs still use `ego` even though new examples should not. Removing the
hardcoded anchor is its own piece of work, already flagged by the `RuntimeWarning` at
`Planner.py:162`, and it is a prerequisite for naming actors freely. Worth doing alongside
section 1b, since blocker 2 there touches the same `dyn(1,0)` literals.

## 7. Units

**RESOLVED 2026-09-07. No conversion. Only `m`, `s` and `mps` are accepted.**

The encoding is integer valued and already has complexity problems, so introducing conversion
would mean rounding, and rounding would mean a satisfiable spec could be reported unsatisfiable
at a boundary. Forcing the units that match the model one to one removes the problem instead of
managing it: a segment is a metre, a step is a second, longitudinal velocity is metres per second.
A literal in a spec is the number that reaches ASP.

Any other unit is refused with a message naming the accepted ones. Fractional literals are
refused too, since the model cannot represent them exactly.
`TranslationGraphVisitor.SUPPORTED_UNITS` holds the list.

Note `mps` rather than `m/s`: `PHYSICAL_LITERAL` is `(FLOAT|INTEGER) IDENTIFIER`
(`openscenario2.g4:292`), so the unit has to be a single identifier token. `10m/s` does tokenize,
but as a division of `10m` by an identifier `s`, which is not what it looks like.

**Bug found while implementing this.** The old `visitPhysical_literal` was

```python
nr = float(''.join(filter(str.isdigit, nr)))
```

which discarded the unit entirely, so `10m`, `10kph` and `10mph` all became `10.0` silently, and
which also stripped decimal points, so `1.5m` became `15.0` and `10.8kph` became `108.0`. No
existing spec under `experiments_src/` uses a fractional literal, so nothing was silently wrong in
the benchmarks, but any spec that had used one would have been off by a factor of ten with no
warning. Now fixed.

**RESOLVED 2026-09-07: `actor.speed` is `Vel_lon`.** The standard defines
`movable_object.speed` as the signed magnitude `sqrt(vx^2 + vy^2) * sign(vx)`, but that formula
does not carry over. Our two components are different kinds of quantity: `Vel_lon` is `0..12`
segments per step, so metres per second, while `Vel_lat` is `velocity_lat(-1..1)` in **lanes**
per step (`facts.lp:6`, `constants.lp:16`), a discrete lane-change flag rather than a velocity.
Combining them would add metres squared to lanes squared, and would be a rounding artefact even
if it were meaningful: `sqrt(10^2 + 1^2) = 10.05`.

## 8. Coverage

7.6.2.3 lists the ways a constraint set can reject every trace.

| 7.6.2.3 case | Covered | Spec |
|---|---|---|
| 1. direct contradiction on one actor | yes | `keep_inconsistent_direct.osc`, `keep_inconsistent_speed.osc` |
| 1b. same actor, parallel scenarios | yes | `keep_inconsistent_parallel.osc` |
| 2. non-local through interplay | yes | `keep_inconsistent_nonlocal.osc` |
| 3. conflict with action or behavior semantics | partial, only what the encoding models | none |

An unsatisfiable ASP program is an inconsistent specification, so detection is exact for what we
encode rather than heuristic.

Limitation: `generate_plans` searches `imin..imax` and reports no model once it exhausts that
range, so what we decide is unsatisfiability up to the horizon. A spec that only becomes
satisfiable at a longer horizon is reported inconsistent.

## 9. Deferred

`keep(default ...)` and `remove_default(...)` (override rules in 7.3.11.3 are fiddly, reject with
a clear message for now). `range of T` as an aggregate type
(our grammar has `range_constructor` as an expression only, and the subset does not need it).
Updating the grammar to 2.2.0 (the constraint grammar is already identical).

## 10. Stages

Each stage is done when the named specs reach the named status under `tests/run_keep_tests.py`,
**and** `tests/run_experiment_tests.py` still reports 12 passed, 0 failed, 1 xfail, 2 skipped.

1. **Parse and represent.** `Invariant` class, `Modifier.SPEED`, visit
   `keep_constraint_declaration`, attach with scope, reject the invalid forms.
   Done when: all keep specs parse and fail at emission rather than parsing.
2. **Scenario-scoped emission.** Done when `keep_scenario_scope.osc`, `keep_hard_qualifier.osc`,
   `keep_speed_range.osc`, `keep_speed_comparison.osc`, `keep_lane_free.osc` PASS, and
   `keep_inconsistent_direct.osc`, `keep_inconsistent_speed.osc` PASS by being unsatisfiable.
2b. **Relational invariants.** Support `space_gap` in a keep body, make `at:` optional in
   `visitModifier_application`, and have both wrap a `RelativeConstraint` in an `Invariant`.
   Done when `keep_relational_distance.osc` and `keep_relational_modifier.osc` PASS with the same
   plan, and `keep_inconsistent_nonlocal.osc` PASSes by being unsatisfiable.
3. **Modifier desugaring.** Done. `keep_lane_modifier.osc` PASSes with the same first three
   plans as `keep_lane_free.osc`, and `keep_speed()` works the same way
   (`keep_speed_modifier.osc`). Standard 8.9.6 and 8.9.16.
4. **Phase scoping.** Done, see section 6. `keep_phase_scope.osc` and
   `keep_inconsistent_parallel.osc` pass, and invocation-scoped cases are checked inside their
   keep windows.
5. **Monitors.** An invariant is an always-operator over its window, failing at the first
   violating step rather than at a phase boundary. Detail after stage 2, once the representation
   has settled. I have not traced the monitor code yet.

## 11. Open

- Stage 5, monitors.
