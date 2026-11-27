#!/usr/bin/env bash
set -euo pipefail

echo "=== Clearing all experiment outputs ==="

for dir in experiments_src/exp*/; do
  out_dir="${dir%/}/out"
  echo "Removing $out_dir"
  gio trash "$out_dir" 2>/dev/null || gio trash "$out_dir"
  mkdir "$out_dir"
done

echo "=== Done clearing experiment outputs ==="
