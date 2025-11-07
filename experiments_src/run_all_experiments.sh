#!/usr/bin/env bash
set -euo pipefail

ANIMATE=false
VANILLA_ONLY=false

# parse flags
for arg in "$@"; do
  case "$arg" in
    --animate) ANIMATE=true ;;
    --vanilla-only) VANILLA_ONLY=true ;;
  esac
done

STATUS_LOG="experiments_src/logs/run_status.jsonl"
: > "$STATUS_LOG"

for dir in experiments_src/exp*/; do
  exp_name=$(basename "$dir")

  # Skip non-vanilla if flag is active
  if $VANILLA_ONLY && [[ "$exp_name" =~ _[a-z]+$ ]]; then
    echo "Skipping $exp_name (not vanilla)"
    continue
  fi

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
