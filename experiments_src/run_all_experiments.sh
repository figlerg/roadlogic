#!/usr/bin/env bash
set -euo pipefail

ANIMATE=false
if [[ "${1:-}" == "--animate" ]]; then
  ANIMATE=true
  shift
fi

STATUS_LOG="experiments_src/run_status.jsonl"
: > "$STATUS_LOG"

for dir in experiments_src/exp*/; do
  exp_name=$(basename "$dir")
  start_iso=$(date -Iseconds)
  echo "=== Running $dir/run.sh ==="

  if [[ -x "$dir/run.sh" ]]; then
    if bash "$dir/run.sh"; then
      status="ok"
    else
      status="error"
    fi
  else
    echo "Skipping $dir (no run.sh)"
    status="skipped"
  fi

  end_iso=$(date -Iseconds)
  printf '{"experiment":"%s","status":"%s","started_at":"%s","finished_at":"%s"}\n' \
    "$exp_name" "$status" "$start_iso" "$end_iso" >> "$STATUS_LOG"

  if $ANIMATE && [[ "$status" == "ok" && -x "$dir/animate.sh" ]]; then
    echo "--- Animating $dir/animate.sh ---"
    bash "$dir/animate.sh" || echo "[WARN] animation failed for $exp_name"
    echo
  fi
  echo
done

bash experiments_src/extract_summaries.sh || true

echo
echo "=== Experiment run summary ==="
cat "$STATUS_LOG"
echo "Summary written to $STATUS_LOG"
