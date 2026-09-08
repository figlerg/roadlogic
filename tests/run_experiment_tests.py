"""Regression runner for the benchmark experiments.

The specs under tests/experiments/*/in are byte-identical copies of the corresponding
experiments_src/*/in folders. Nothing here writes into experiments_src. Refresh the
copies with:

    python tests/run_experiment_tests.py --sync

Two stages:

  plan (default)   Parse each spec.osc, build the translation graph, ground the ASP
                   instance and solve. This is the part that parser, TranslationGraph
                   and encoding changes can break, and it runs in seconds per case.

  full             The real pipeline from experiments_src/common.sh, including Frenetix
                   simulation, metrics and similarity. Hours, not minutes. Only worth it
                   before a release or after touching the execution path.

exp_004 and exp_004_b are skipped by default even in the plan stage: their planning alone
took 45 minutes and 3.4 hours respectively in the recorded runs. Pass --include-slow, or
name them explicitly, to run them anyway.

Usage:
    source venv/bin/activate
    python tests/run_experiment_tests.py                       # plan stage, all cases
    python tests/run_experiment_tests.py exp_002 exp_002_b     # subset
    python tests/run_experiment_tests.py --stage full          # everything, slow
    python tests/run_experiment_tests.py --include-slow         # plan stage including exp_004*
    python tests/run_experiment_tests.py --sync                # re-copy from experiments_src
"""

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import warnings
from dataclasses import dataclass, field
from typing import List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "experiments_src")
DST = os.path.join(HERE, "experiments")

CONTROLLER_LP = os.path.join(ROOT, "create_scenarios", "controller.lp")

# Plan-stage settings. Deliberately small: this is a smoke test of the planning path,
# not a reproduction of the paper numbers, which is what the full stage is for.
PLAN_N = 2
PLAN_IMAX = 20
# The real vanilla pipeline passes no time limit at all. This cap only exists so a broken
# encoding cannot hang the suite indefinitely. It has to be generous: exp_004's planning
# stage took 2731s in the recorded run, which is why that case is marked slow.
PLAN_TIME_LIMIT = 3600
# Partitions to generate for a variability experiment. The paper runs use N=50, which is far
# too slow here, and the point of the smoke test is only that the partition path still plans.
PLAN_PARTITIONS = 3


@dataclass
class Experiment:
    name: str
    pipeline: str                       # vanilla | variability
    n: int                              # N from the original run.sh
    step_length: Optional[int] = None   # vanilla only
    extra: List[str] = field(default_factory=list)
    xfail: str = ""                     # non-empty means a known, tracked failure
    slow: str = ""                      # non-empty means skipped unless --include-slow

    @property
    def dir(self):
        return os.path.join(DST, self.name)

    @property
    def spec(self):
        return os.path.join(self.dir, "in", "spec.osc")

    @property
    def rule_injection(self):
        return os.path.join(self.dir, "in", "rule_injection.lp")


# Mirrors the run.sh of each experiment in experiments_src. Keep in sync by hand if one
# of those changes: the in/ folders are copied automatically but run.sh is not.
EXPERIMENTS: List[Experiment] = [
    Experiment("exp_001", "vanilla", n=10, step_length=60),
    Experiment("exp_001_b", "variability", n=50, extra=["--init-interval", "10", "20"]),
    Experiment("exp_002", "vanilla", n=10, step_length=60),
    Experiment("exp_002_b", "variability", n=50),
    Experiment("exp_003", "vanilla", n=10, step_length=60),
    Experiment("exp_003_b", "variability", n=50),
    Experiment("exp_004", "vanilla", n=10, step_length=60,
               slow="planning alone took 2731s in the recorded run, see "
                    "experiments_src/exp_004/out/times.jsonl"),
    Experiment("exp_004_b", "variability", n=50,
               slow="variability_experiments took 12140s in the recorded run, see "
                    "experiments_src/exp_004_b/out/times.jsonl"),
    Experiment("exp_005", "vanilla", n=10, step_length=60),
    Experiment("exp_005_b", "variability", n=50, extra=["--random-seed", "1"]),
    Experiment("exp_006", "vanilla", n=10, step_length=60),
    Experiment("exp_006_b", "variability", n=50),
    Experiment("exp_007", "vanilla", n=10, step_length=60),
    Experiment("exp_007_b", "variability", n=50, extra=["--init-distance-actor", "obstacle"]),
    Experiment(
        "exp_parallel",
        "vanilla",
        n=2,
        step_length=1,
        xfail="known broken, see docs/known-issues-exp-parallel.md: "
              "grounding loop bug in Planner.py and a clingo syntax error in the generated instance",
    ),
]

PASS, FAIL, XFAIL, XPASS, SKIP = "PASS", "FAIL", "XFAIL", "XPASS", "SKIP"


# ---------------------------------------------------------------- syncing

def sync():
    """Re-copy every experiments_src/*/in into tests/experiments/*/in."""
    copied = []
    for name in sorted(os.listdir(SRC)):
        src_in = os.path.join(SRC, name, "in")
        if not os.path.isdir(src_in):
            continue
        dst_in = os.path.join(DST, name, "in")
        os.makedirs(dst_in, exist_ok=True)
        for f in sorted(os.listdir(src_in)):
            shutil.copy2(os.path.join(src_in, f), os.path.join(dst_in, f))
        copied.append(name)
    print(f"Synced {len(copied)} experiment inputs from experiments_src: {', '.join(copied)}")


def check_sync():
    """Warn if a copy has drifted from its source. Not fatal, the copy is what runs."""
    drifted = []
    for exp in EXPERIMENTS:
        src_in = os.path.join(SRC, exp.name, "in")
        dst_in = os.path.join(exp.dir, "in")
        if not os.path.isdir(src_in) or not os.path.isdir(dst_in):
            drifted.append(exp.name)
            continue
        cmp = filecmp.dircmp(src_in, dst_in)
        if cmp.left_only or cmp.right_only or cmp.diff_files:
            drifted.append(exp.name)
    if drifted:
        print(f"WARNING: these copies differ from experiments_src: {', '.join(drifted)}")
        print("         run with --sync to refresh them\n")


# ---------------------------------------------------------------- plan stage

def _plan_one(planner_spec, out_dir, external_rules, n=PLAN_N, rules_override=False):
    """Run the planner once and return its plans.

    rules_override=True means external_rules already contains the encoding files, which is
    how variability_experiments.py invokes the planner. Passing it wrong loads constants.lp,
    facts.lp and dynamics.lp twice.
    """
    from planning.Planner import Planner

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        planner = Planner(planner_spec, out_path=out_dir)
        return planner.plans(
            n=n,
            external_rules=external_rules,
            visualize=False,
            imax=PLAN_IMAX,
            time_limit=PLAN_TIME_LIMIT,
            rules_override=rules_override,
        )


def _describe(plans):
    horizons = sorted({p.max_t for p in plans})
    actors = sorted({str(pred.actor) for pred in plans[0].holds
                     if pred.arguments[0].name == "state"})
    return f"horizons {horizons}, actors {actors}"


def run_plan_stage_vanilla(exp: Experiment, case_dir: str):
    """Mirrors create_scenarios/create_plan_scenarios.py: one planner call on the spec."""
    external_rules = [CONTROLLER_LP]
    if os.path.exists(exp.rule_injection) and os.path.getsize(exp.rule_injection) > 0:
        external_rules.append(exp.rule_injection)

    try:
        plans = _plan_one(exp.spec, case_dir, external_rules)
    except Exception:
        return False, traceback.format_exc().strip()

    if not plans:
        return False, f"no plan found within {PLAN_IMAX} steps"
    return True, f"{len(plans)} plans, {_describe(plans)}"


def run_plan_stage_variability(exp: Experiment, case_dir: str):
    """Mirrors create_scenarios/variability_experiments.py.

    The partition instances carry the init(...) facts, so planning the bare spec is not a
    faithful check. Individual partitions are allowed to come back unsatisfiable or to time
    out, exactly as invoke_planner records them in summary.json. The regression signal is
    that the partition path still produces at least one plan.
    """
    from planning.asp.generate_plans import NoModelException

    partitions_dir = os.path.join(case_dir, "partitions")
    os.makedirs(partitions_dir, exist_ok=True)

    cmd = [sys.executable, "create_scenarios/create_variability_instances.py",
           "--output-folder", partitions_dir, "--n", str(PLAN_PARTITIONS), *exp.extra]
    proc = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stdout.splitlines()[-15:])
        return False, f"create_variability_instances exited {proc.returncode}\n{tail}"

    instances = sorted(f for f in os.listdir(partitions_dir) if f.endswith(".lp"))
    if not instances:
        return False, f"no partition instances produced in {partitions_dir}"

    # rules_override=True in the real pipeline, so the encoding files are passed explicitly.
    enc = os.path.join(ROOT, "planning", "asp", "encoding")
    statuses, first_ok = [], None
    for inst in instances:
        rule_sets = [CONTROLLER_LP, os.path.join(partitions_dir, inst)]
        if os.path.exists(exp.rule_injection) and os.path.getsize(exp.rule_injection) > 0:
            rule_sets.append(exp.rule_injection)
        # No constants.lp: the partition instance supplies the constants, which is exactly
        # what rules_override is for. Adding it back makes clingo fail to parse.
        rule_sets += [os.path.join(enc, "dynamics.lp"), os.path.join(enc, "facts.lp")]

        sub = os.path.join(case_dir, "aux_asp", os.path.splitext(inst)[0])
        os.makedirs(sub, exist_ok=True)
        try:
            # n=1 like invoke_planner: one plan per partition, not PLAN_N.
            plans = _plan_one(exp.spec, sub, rule_sets, n=1, rules_override=True)
            statuses.append(f"{inst}=SAT")
            if first_ok is None and plans:
                first_ok = plans
        except NoModelException:
            statuses.append(f"{inst}=UNSAT")
        except TimeoutError:
            statuses.append(f"{inst}=timeout")
        except RuntimeError as exc:
            # invoke_planner records this as a clingo parsing problem rather than aborting.
            statuses.append(f"{inst}=clingo-error({exc})")
        except Exception:
            return False, f"{inst} raised unexpectedly\n" + traceback.format_exc().strip()

    detail = f"{len(instances)} partitions: {', '.join(statuses)}"
    if first_ok is None:
        return False, f"no partition yielded a plan. {detail}"
    return True, f"{detail}. {_describe(first_ok)}"


def run_plan_stage(exp: Experiment, out_dir: str):
    case_dir = os.path.join(out_dir, exp.name)
    os.makedirs(case_dir, exist_ok=True)
    if exp.pipeline == "vanilla":
        return run_plan_stage_vanilla(exp, case_dir)
    return run_plan_stage_variability(exp, case_dir)


# ---------------------------------------------------------------- full stage

def run_full_stage(exp: Experiment):
    """Invoke the real pipeline from experiments_src/common.sh against the tests copy."""
    rel = os.path.relpath(exp.dir, ROOT)
    if exp.pipeline == "vanilla":
        call = f'run_vanilla_experiment "{rel}" {exp.n} {exp.step_length}'
    else:
        call = f'run_variability_experiment "{rel}" {exp.n}'
    if exp.extra:
        call += " " + " ".join(f'"{a}"' for a in exp.extra)

    script = f'set -euo pipefail\nsource experiments_src/common.sh\n{call}\n'
    proc = subprocess.run(
        ["bash", "-c", script], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stdout.splitlines()[-25:])
        return False, f"pipeline exited {proc.returncode}\n{tail}"
    return True, "pipeline completed"


# ---------------------------------------------------------------- driver

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="experiment names to run, default all")
    ap.add_argument("--stage", choices=["plan", "full"], default="plan")
    ap.add_argument("--include-slow", action="store_true",
                    help="also run the cases marked slow, which take tens of minutes each")
    ap.add_argument("--sync", action="store_true",
                    help="re-copy the in folders from experiments_src and exit")
    args = ap.parse_args(argv)

    if args.sync:
        sync()
        return 0

    cases = [e for e in EXPERIMENTS if not args.names or e.name in args.names]
    if not cases:
        print(f"No experiment matched {args.names}. Known: {[e.name for e in EXPERIMENTS]}")
        return 2

    check_sync()

    out_dir = tempfile.mkdtemp(prefix="experiment_tests_")
    print(f"Stage '{args.stage}', {len(cases)} experiments, artifacts in {out_dir}\n")
    if args.stage == "full":
        print("The full stage writes into tests/experiments/*/out and takes hours.\n")

    results = []
    for exp in cases:
        if exp.slow and not args.include_slow and not args.names:
            results.append((SKIP, exp, exp.slow))
            print(f"[{SKIP:>5}] {exp.name:<14} {exp.pipeline:<12}   skipped")
            print(f"        {exp.slow}")
            print("        run with --include-slow or name it explicitly\n")
            continue

        started = time.time()
        if args.stage == "plan":
            ok, detail = run_plan_stage(exp, out_dir)
        else:
            ok, detail = run_full_stage(exp)
        elapsed = time.time() - started

        if exp.xfail:
            status = XFAIL if not ok else XPASS
        else:
            status = PASS if ok else FAIL

        results.append((status, exp, detail))
        print(f"[{status:>5}] {exp.name:<14} {exp.pipeline:<12} {elapsed:6.1f}s")
        if status == XFAIL:
            print(f"        expected failure: {exp.xfail}")
        elif status == XPASS:
            print(f"        unexpectedly passed, the xfail note is stale: {exp.xfail}")
        if status in (FAIL, XPASS) or args.stage == "plan":
            for line in detail.splitlines():
                print(f"        {line}")
        print()

    counts = {s: sum(1 for r, _e, _d in results if r == s)
              for s in (PASS, FAIL, XFAIL, XPASS, SKIP)}
    print(f"{counts[PASS]} passed, {counts[FAIL]} failed, "
          f"{counts[XFAIL]} expected failures, {counts[XPASS]} unexpected passes, "
          f"{counts[SKIP]} skipped as slow")

    if counts[FAIL] == 0 and counts[XPASS] == 0:
        shutil.rmtree(out_dir, ignore_errors=True)
    else:
        print(f"Artifacts kept in {out_dir}")

    return 1 if (counts[FAIL] or counts[XPASS]) else 0


if __name__ == "__main__":
    sys.exit(main())
