# Finding: exp_parallel example does not run end to end

Context: verifying the ported TranslationGraph.py bugfix (from e95a768) before committing on main.
Ran `bash experiments_src/exp_parallel/run.sh`, which is the regression example that commit
e95a768 itself added. It does not complete. Two separate, unrelated problems, neither touches
TranslationGraph.py.

## 1. `experiments_src/exp_parallel/in/spec.osc` (the file run.sh actually uses)

Fails in `planning/Planner.py`, in `create_asp_instance`, with:

```
ValueError: Could not ground all actors — disconnected or circular constraints: []
```

Note the empty list at the end. Look at `planning/Planner.py:234-272`:

```python
while remaining:
    progress = False
    for a1 in sorted(list(remaining)):
        ...
        remaining.remove(a1)          # line 269, unconditional

    if not progress:
        raise ValueError(f"Could not ground all actors — disconnected or circular constraints: {remaining}")
```

`remaining.remove(a1)` at line 269 runs for every `a1` in the for loop regardless of whether that
actor actually got grounded. So by the time the `if not progress` check runs, `remaining` is
already empty. The check can fire with nothing left to report, which is what happened here on
`spec.osc`. This looks like a pre-existing logic bug in the grounding loop, not something the
TranslationGraph.py fix touches or introduces.

Confirmed pre-existing on the current main tip (== origin/artifact-hscc26), independent of the
cherry-pick: `Planner.py` was not changed by the port (the Planner.py hunk from e95a768 was
dropped, kept HEAD's version), and `experiments_src/exp_001/in/spec.osc` (already part of the
artifact, also uses parallel composition and relative constraints) grounds and runs fine standalone
via `create_scenarios/create_plan_scenarios.py`. So this isn't a general break, it's specific to
the constraint shape in exp_parallel's spec.osc.

## 2. `experiments_src/exp_parallel/in/spec_parallel.osc` (the second file, not used by run.sh)

Different failure, in ASP generation itself:

```
<tmp>/instance.lp:19:22-23: error: syntax error, unexpected .
...
File "planning/asp/generate_plans.py", line 75, in generate_plans
    ctl.load(file_)
RuntimeError: parsing failed
```

The generated `instance.lp` is not valid clingo syntax for this spec. Separate bug, separate code
path, also does not touch TranslationGraph.py.

## Circumstantial evidence these were already known, unfixed

The original commit e95a768 (same author) also added two empty files alongside the two example
specs: `experiments_src/exp_parallel/in/rule_injection.lp` and
`experiments_src/exp_parallel/bug_disconnected_constraints`. Both are 0 bytes. The name of the
second one matches the exact error text above. Reads like a marker/note left mid-investigation
that never got filled in or fixed.

## What's confirmed to still work

- `python -m planning.Planner plans --osc2_file tests/overtake.osc -n 3 -a` (README's basic test): passes, 3 models.
- `experiments_src/exp_001` scenario generation (existing artifact example, parallel + relative constraints): passes.

The TranslationGraph.py fix itself (the actual thing being ported in this session) has not yet
been exercised through the full pipeline, because both of exp_parallel's own example specs are
blocked by these unrelated, pre-existing bugs before they'd ever reach the parallel-composition
code path in a way that would show a visible difference.

## Not yet decided

How to proceed with verification and with the commit. Open questions for you:
- Do these two bugs belong on a separate task in Section B or elsewhere in PLAN.md?
- Should exp_parallel be fixed before it's useful as a regression example, or is a smaller/different
  test preferred to actually exercise the parallel-composition fix?
