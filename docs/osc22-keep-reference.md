# `keep` in ASAM OpenSCENARIO DSL 2.2.0

Reference notes for the RoadLogic invariant support. All section numbers refer to
ASAM OpenSCENARIO DSL 2.2.0, Dynamic scenario description, 2026-03-19.

## Canonical links

Use the version-pinned `/v2.2.0/` path. The `/latest/` path is a moving alias and
will point at 2.3.0 once that is released. The pages themselves declare the
`/v2.2.0/` form as their canonical URL.

- [Standard root](https://publications.pages.asam.net/standards/ASAM_OpenSCENARIO/ASAM_OpenSCENARIO_DSL/v2.2.0/index.html)
- [7.2.2.4.3 Constraint grammar](https://publications.pages.asam.net/standards/ASAM_OpenSCENARIO/ASAM_OpenSCENARIO_DSL/v2.2.0/language-reference/language_syntax.html#sec-lc-syntax-constraints)
- [7.3.11 Constraints](https://publications.pages.asam.net/standards/ASAM_OpenSCENARIO/ASAM_OpenSCENARIO_DSL/v2.2.0/language-reference/types.html#sec-lc-constraints)
- [7.3.12 Modifiers](https://publications.pages.asam.net/standards/ASAM_OpenSCENARIO/ASAM_OpenSCENARIO_DSL/v2.2.0/language-reference/types.html#sec-lc-modifiers)
- [7.6.1 Semantic foundations](https://publications.pages.asam.net/standards/ASAM_OpenSCENARIO/ASAM_OpenSCENARIO_DSL/v2.2.0/language-reference/Semantics.html#sec-lc-semantics-semantic-foundations)
- [7.6.2.3 Scenario constraints](https://publications.pages.asam.net/standards/ASAM_OpenSCENARIO/ASAM_OpenSCENARIO_DSL/v2.2.0/language-reference/Semantics.html#sec-lc-semantics-scenario-constraints)
- [Consolidated EBNF (download)](https://publications.pages.asam.net/standards/ASAM_OpenSCENARIO/ASAM_OpenSCENARIO_DSL/v2.2.0/language-reference/_attachments/grammar.ebnf)

For papers, cite the standard and its date plus the section number, not the URL.
ASAM does not guarantee the hosting path across releases.

## Grammar

```ebnf
constraint-declaration       ::= keep-constraint-declaration | remove-default-declaration
keep-constraint-declaration  ::= 'keep' '(' [constraint-qualifier] constraint-expression ')' NEWLINE
constraint-qualifier         ::= 'default' | 'hard'
constraint-expression        ::= expression
remove-default-declaration   ::= 'remove_default' '(' parameter-reference ')' NEWLINE
parameter-reference          ::= field-name | field-access
```

The body must be a Boolean expression. `keep(lane(0))` is invalid because
`lane(0)` is a modifier application. `keep(speed: [0..10])` is invalid because
that is named-argument syntax, not an expression.

## Placement and scope (7.3.11.1, 7.3.11.2)

Legal positions:

- as a member of a `struct`, `scenario`, `action`, `actor` or `modifier`
- in a `with` clause on a field declaration (equivalent to a direct member)
- in a `with` clause on a behavior invocation inside a `do` directive

Constraints apply for the lifetime of the instance in which they are declared.
This is the invariant mechanism: a `keep` as a scenario member holds for the whole
scenario, a `keep` inside a behavior invocation holds only for that invocation.

The standard also states that a constraint should affect at least one parameter.

## Canonical examples

### Member constraints with implication (7.3.6, Code 26)

```osc
struct driving_speed:
    area: area_kind
    speed: speed
    keep(area == city => speed < 50kph)
    keep(area == highway => speed < 100kph)
    keep(area == school => speed < 30kph)
```

### `it` in a field `with` block (7.3.6 Code 27, 7.3.6.2.1 Code 29)

```osc
struct positive_vector_3d:
    x, y, z: speed = 0kph with:
        keep(it >= 0kph)

actor my_car inherits vehicle (vehicle_category == car):
    var current_speed: speed
    max_speed: speed with:
        keep(default it == 120kmph)
```

### Path expressions into a nested struct (7.3.6.2.2, Code 30)

```osc
scenario env.snowstorm:
    storm_data: storm_data with:
        keep(it.storm == snow_storm)
        keep(default it.wind_velocity >= 30kmph)
```

### Physical literals and unit arithmetic (7.3.4, Code 22)

Units are a mandatory part of any physical type literal.

```osc
my_dist: length
keep(my_dist == 15|foot/s| * 3s + 10m)

my_speed: speed
keep(my_speed == 5m / 2s)
```

### List element constraints (7.3.5.2.1)

These implicitly constrain list size. The list below has size at least 5.

```osc
struct data:
    coords: list of point with:
        keep(it[4].x == 1.5)
        keep(it[4].y == 2.5)
```

### Parameters only, never variables (7.3.6.2.3, Code 31)

```osc
actor car:
    var current_position: position
    keep(current_position.x < 100)   # error: current_position is a variable
```

Variables cannot be constrained. Parameters can be constrained against variable
values by sampling during constraint resolution.

### Scope and lifetime (7.3.11.2, Code 43)

```osc
scenario car.lose_constraint:
    do serial():
        actor.assign_speed() with:
            keep(it.speed <= 30kph)
        actor.drive()        # constraint no longer applies
```

### Constraints in a scenario invocation (7.3.11.4, Codes 47 and 48)

```osc
scenario car.follow:
    other: car
    distance: length
    keep(distance < 50m)

scenario main:
    dut: car
    c: car
    do c.follow() with:
        keep(it.other == dut)
        keep(it.distance == 20m)

# equivalent short form
    do c.follow(other: dut, distance: 20m)
```

### Global parameter reference (7.3.14, Code 63)

```osc
keep(newfield <= environment.weather.air.relative_humidity)
```

## Modifier desugaring (7.3.12.4.1, 7.3.12.3 Code 53)

Three distinct rules for argument passing:

```osc
speed(speed: 10kph)                  ==>  keep(speed == 10kph)
speed(speed: [10kph..25kph])         ==>  keep(speed in [10kph..25kph])
speed(speed_range: [10kph..25kph])   ==>  keep(speed_range == [10kph..25kph])
```

The domain model's `keep_lane()` is itself defined in terms of `keep`:

```osc
modifier vehicle.keep_lane():
   lane = actor.lane
   keep(actor.lane == lane)
```

Design consequence: implement the modifier surface syntax as a desugaring pass
into `keep`, so only one internal representation reaches the ASP encoding and the
monitors. Both surface forms are standard-conformant.

### Range types caveat

In 2.2.0 `range of <T>` is a proper aggregate type.

```osc
r3: range of speed  = [50kph .. 80mph]
r4: range of length = range(5m, 10m)
r5: range of int    = 5                 # promoted to [5..5]
```

So `[10kph..25kph]` desugars to an `in` constraint against a scalar parameter but
to an equality constraint against a range-typed parameter. Check whether the
2.1-targeted parser distinguishes these.

## Constraint strength (7.3.11.3)

- No prefix means hard. Hard constraints must be satisfied and cannot be overridden.
- `default` constraints must be satisfied unless overridden by a later `default`
  or `hard` constraint, in textual order.
- A field default value is exactly equivalent to a `default` equality constraint.

Direct contradiction, an error:

```osc
keep(x < 3)
keep(x == 2)
keep(x == 5)   # error
```

Override rules, useful as negative test cases (Code 45). A `default` can only be
implicitly overridden by an equality or range constraint with the parameter alone
on the left-hand side.

```osc
keep(default x == 2)
keep(x > 100)          # error: not an equality or range constraint
keep(x + 5 == 1)       # error: parameter not alone on the left
keep(true => x == 6)   # error: not an equality or range constraint
keep(7 == x)           # error: parameter must be on the left
keep(x == 5)           # valid implicit override
```

Explicit route:

```osc
keep(default y == 2 and z == 1)
remove_default(y)
keep(y > 100)
```

## Inconsistency, for the paper

7.6.1: a model is inconsistent if the set of traces it accepts is empty, which can
arise from contradictions in constraints. The standard's own example is a car
required to drive both faster and slower than 50 km/h.

7.6.2.3 enumerates the trace rejection cases:

1. Direct contradiction, given as `keep(speed>10kph)` with `keep(speed<10kph)`
   inside the same vehicle actor. The standard notes that such constraints can
   also conflict when placed on the same actor instance from different scenarios
   active in parallel, and that such cases may be less obvious.
2. Non-local unsatisfiability through interplay. The example is a vehicle
   constrained to a minimum distance from a preceding vehicle that is itself
   constrained to accelerate, forcing the follower past its maximum speed.
3. Conflicts between scenario constraints and constraints implied by the atomic
   actions invoked from that scenario, and conflicts with specific behavior
   models such as driver models.

The standard names all three and supplies no mechanism to detect them. The ASP
encoding decides cases 1 and 2: an unsatisfiable program is exactly an
inconsistent specification. Case 3 is only partially covered, depending on how
much of the action semantics is encoded.

Cite 7.6.1 and 7.6.2.3.
