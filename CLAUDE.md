# CLAUDE.md

## Project

RoadLogic: scenario-based testing for autonomous driving systems. Scenarios in an OpenSCENARIO 2.1 subset are compiled to ASP for concretization and variation. Before working on the ASP encoding, the symbaut encoding, monitors, or semantics, read docs/method.md.

## Environment

- WSL Ubuntu, Python venv at .venv. Activate it before running anything: `source .venv/bin/activate`
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
- After any change to plotting code, render the affected figure(s) to PNG and visually inspect the image before reporting done. Check: no clipped or overlapping text, no missing legends or labels, font sizes readable at paper column width, style consistent with existing figures.

## Code style

- Short, reusable functions. Extend existing utilities instead of writing one-off variants.
- No em dashes and no semicolons in any prose output: README, docs, comments, commit messages.

## Git state

- main is being cleaned up. The pre-reset history is bookmarked as main-legacy. Cherry-pick from main-legacy only after explicit per-commit approval.
- artifact-hscc26 is the HSCC 2026 artifact branch. [TODO: confirm whether this branch is frozen and must never be modified]

## Current goals

1. Git cleanup: make main a clean entry point. Includes improving README and setup instructions.
2. Implement the "keep" feature on branch feature/keep, to be merged into main later. Task breakdown lives in .claude/PLAN.md.
