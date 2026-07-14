# CLAUDE.md

## Project

RoadLogic: scenario-based testing for autonomous driving systems. Scenarios in an OpenSCENARIO 2.1 subset are compiled to ASP for concretization and variation. Then the ASP plans are transformed into planning problems for Frenetix and refined for actual simulation traces. Before working on the ASP encoding, the symbaut encoding, monitors, or semantics, read docs/method.md.

## Environment

- WSL Ubuntu, Python venv at venv. Activate it before running anything: `source venv/bin/activate`
- Install in editable mode if needed: `pip install -e .`

## Workflow rules

- Plan before acting for any change touching more than one file. Present the plan and wait for approval.
- Work in small increments, one logical step at a time. No large multi-file rewrites in one go.
- Never commit without asking. Propose a commit message, wait for explicit confirmation.
- Never push, force-push, hard-reset or rewrite history. Propose the exact command and let me run it. This is also enforced via permission deny rules.
- Maintain .claude/PLAN.md as persistent state: current task, decisions made, open questions, triage status of commits. Update it at the end of every work block so a fresh session can resume from it.

## Verification

- There is no test suite. Verification means: run the relevant example script(s) and confirm they complete without errors and the output is plausible.
- When implementing new functionality, add a minimal runnable example or a small pytest test alongside it. Prefer growing a real test suite over time.
- Definition of done for any change: examples run, figures inspected (see below), .claude/PLAN.md updated.

## Figures

- Plotting is strictly separated from data generation. Plot functions consume cached or saved data and must never trigger regeneration. Preserve this separation in all new code.
- After any change to plotting code, render the affected figure(s) to PNG and visually inspect the image before reporting done. Check: no clipped or overlapping text, no missing legends or labels, font sizes readable at paper column width (395.8225pt for the TCPS journal version), style consistent with existing figures.

## Paper experiments

The HSCC paper figures are created in branch artifact-hscc26 in the folder paper. The actual experiment files for the benchmarks are in experiments_src. The new experiments for the journal version will be in paper_journal. Make sure that the paper_journal experiments are somewhat self contained, so we can rerun them in a new artifact for TCPS.

## Code style

- Short, reusable functions. Extend existing utilities instead of writing one-off variants.
- No em dashes and no semicolons in any prose output: README, docs, comments, commit messages.

## Git state

- artifact-hscc26 is FROZEN. It is the HSCC 2026 artifact and the paper links to it. Never commit to it, never modify it, never push it. Before any git operation, run `git branch --show-current`. If it is artifact-hscc26, stop and tell me instead of acting.
- artifact-iccps26 is an older artifact branch. Leave it alone.
- main is stale and diverged from artifact-hscc26 (merge-base b305458, 9 main-only commits). It is being reset to the artifact state.
- Before the reset, the current main tip is bookmarked as main-stale. That bookmark preserves the old history. There is no branch called main-legacy, ignore any reference to one.
- Cherry-pick or port forward from main-stale only after explicit per-commit approval. Triage table is in .claude/PLAN.md.
- All future work branches off main.
- artifact-tcps will be created later for the TCPS journal version, once main is stable, the keep feature works, and the new experiments run. It should contain the artifact-hscc26 content plus the new journal experiments, rerunnable in the same form as the HSCC artifact.
- Never push. Propose the exact command, I run it.

## The "keep" feature

Goal: support invariants in OSC 2.1 specs, parse them, and enforce them in the ASP encoding and the monitors. Stay inside the standard, do not invent syntax.

### Semantics

keep is the OSC DSL constraint keyword. Full syntax: keep([hard|default] <boolean-expression>).
The body must be a Boolean expression, not a modifier call. keep(lane(0)) is invalid.
Named-argument form such as keep(speed: [0..10]) is also invalid.

Scoping defines the invariant window. A keep declared as a scenario member holds for the whole
lifetime of that scenario. A keep declared inside a behavior invocation holds only for the
lifetime of that invocation. This is the mechanism by which invariants attach to phases.

Constraint strength: hard (default if no prefix, must be satisfied, cannot be overridden) and
default (overridable by a later default or hard constraint, or via remove_default).
Start with hard only. Add default later if needed.

Physical literals require units. [0..10] is invalid, [0kph..10kph] is valid.

### Supported invariant forms (initial subset)

- keep(actor.lane == 0)
- keep(actor.speed in [60kph..100kph])
- keep(actor.speed > 10kph) and other comparisons on speed

Open question, decide before implementing: whether to support relational invariants such as
distance to another vehicle. The domain model exposes these through modifiers like
position(distance: [5m..100m], behind: v1), and the underlying quantities are variables, which
per the standard cannot be constrained directly. Do not guess at a syntax for this. Ask me.

There is no scalar position or s-coordinate field in the OSC domain model. Do not add one.

### Modifier syntax is sugar over keep

The standard defines modifier arguments as desugaring to constraints. drive() with:
speed(speed: [10kph..25kph]) is equivalent to keep(speed in [10kph..25kph]) inside the modifier.
The domain model's keep_lane() modifier is itself defined as lane = actor.lane plus
keep(actor.lane == lane).

Therefore: implement the modifier surface syntax as a desugaring pass into the keep form, so that
only one internal representation reaches the ASP encoding and the monitors. Both surface syntaxes
are standard-conformant.

### Inconsistency detection (paper contribution)

The standard defines a model as inconsistent if the set of traces it accepts is empty, which can
arise from contradicting constraints. Section 7.6.2.3 gives keep(speed>10kph) together with
keep(speed<10kph) on the same actor as the example, and notes that conflicts placed on the same
actor from different scenarios active in parallel "may be less obvious". It also describes
non-local unsatisfiability, for example a minimum following distance on one vehicle combined with
an acceleration constraint on the preceding vehicle forcing the follower past its speed limit.

The standard names this problem and provides no mechanism to detect it. Our ASP encoding decides
it: an unsatisfiable program is exactly an inconsistent specification. This is a headline claim
for the TCPS journal version. Cite ASAM OpenSCENARIO DSL 2.2.0, Sections 7.6.1 and 7.6.2.3.

## Current goals

1. Git cleanup: make main a clean entry point. Includes improving README and setup instructions.
2. Implement the "keep" feature on branch feature/keep, to be merged into main later. Task breakdown lives in .claude/PLAN.md.
3. TODO build a BeamNG.tech backend.
4. TODO make a scenario with a more complex road network (optional)
5. TODO make a working artifact for TCPS
