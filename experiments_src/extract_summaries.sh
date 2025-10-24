#!/usr/bin/env bash
set -euo pipefail

LOGDIR="experiments_src/logs"
mkdir -p "$LOGDIR"

for dir in experiments_src/exp*/; do
  src="$dir/out/cr_simulations/summary_log.json"
  exp_name=$(basename "$dir")
  dest="$LOGDIR/${exp_name}.json"
  if [[ -f "$src" ]]; then
    echo "Copying $src → $dest"
    cp "$src" "$dest"
  else
    echo "Skipping $dir (no summary_log.json)"
  fi
done

echo "All available summaries collected in $LOGDIR/"
