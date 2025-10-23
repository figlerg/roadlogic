#!/usr/bin/env bash
set -euo pipefail

ANIMATE=false
if [[ "${1:-}" == "--animate" ]]; then
  ANIMATE=true
  shift
fi

for dir in experiments_src/exp*/; do
  if [[ -x "$dir/run.sh" ]]; then
    echo "=== Running $dir/run.sh ==="
    bash "$dir/run.sh"
    echo
    if $ANIMATE && [[ -x "$dir/animate.sh" ]]; then
      echo "--- Animating $dir/animate.sh ---"
      bash "$dir/animate.sh"
      echo
    fi
  else
    echo "Skipping $dir (no run.sh)"
  fi
done
