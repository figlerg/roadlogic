#!/bin/bash
# Run every mode on every spec, one process per run, results as JSON lines.
# From the repository root, venv active: bash paper_journal/path_modes/run_all.sh <out.jsonl>
OUT=${1:-paper_journal/path_modes/results.jsonl}
: > "$OUT"
for spec in tests/one_of_nested.osc tests/keep_phase_scope.osc experiments_src/exp_parallel/in/spec_parallel.osc paper_journal/path_modes/specs/par3.osc; do
  for n in 6 20; do for early in 0 1; do for m in first lazy spread live; do
    line=$(timeout 300 python paper_journal/path_modes/modes.py "$spec" "$m" "$n" "$early" 2>&1 | grep '^{')
    if [ -n "$line" ]; then echo "$line" >> "$OUT"
    else echo "{\"spec\": \"$(basename "$spec")\", \"mode\": \"$m\", \"early\": $early, \"n\": $n, \"failed\": \"timeout or error\"}" >> "$OUT"; fi
  done; done; done
done
echo ALL_DONE
