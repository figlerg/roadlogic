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

  log_file="${dir%/}/run.log"
  err_tail_dir="experiments_src/logs/error_tails"
  mkdir -p "$err_tail_dir"

  if [[ -x "$dir/run.sh" ]]; then
    echo "   (logging to $log_file)"
    : > "$log_file"
    if bash "$dir/run.sh" 2>&1 | tee "$log_file"; then
      status="ok"
    else
      status="error"
      tail_file="$err_tail_dir/${exp_name}_error_tail.log"
      tail -n 100 "$log_file" > "$tail_file" || true
      echo "[ERROR] $exp_name failed. Last 100 lines saved to $tail_file"
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


# vanilla pics
python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_00[0-9].json" \
  --out "experiments_src/vis/vis_vanilla_combined.pdf"

python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_00[0-9].json" \
  --out "experiments_src/vis/vis_vanilla_timing.pdf" \
  --mode timing \

python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_00[0-9].json" \
  --out "experiments_src/vis/vis_vanilla_success.pdf" \
  --mode success \


# parameter variation pics
python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_*_b.json" \
  --mode timing \
  --out experiments_src/vis/vis_partitioning_timing.pdf

python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_*_b.json" \
  --mode success \
  --out experiments_src/vis/vis_partitioning_success.pdf

python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_*_b.json" \
  --out "experiments_src/vis/vis_partitioning_combined.pdf"


# parameter variation plus fixed car1
python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_*_c.json" \
  --out "experiments_src/vis/vis_partitioning_fixedcar1_combined.pdf"

python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_*_c.json" \
  --mode success \
  --out experiments_src/vis/vis_partitioning_fixedcar1_success.pdf

python experiments_src/vis_success_rates.py \
  --pattern "experiments_src/logs/exp_*_c.json" \
  --mode timing \
  --out experiments_src/vis/vis_partitioning_fixedcar1_timing.pdf


