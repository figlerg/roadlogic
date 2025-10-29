#!/usr/bin/env bash
# Common helper: logs timing info as JSON in $EXP/out/times.jsonl

time_step() {
  local label="$1"; shift
  local start end dur start_iso end_iso status rc log_json
  log_json="$EXP/out/times.jsonl"
  mkdir -p "$(dirname "$log_json")"

  start=$(date +%s); start_iso=$(date -Iseconds)
  echo "[START] $label"
  "$@"; rc=$?
  end=$(date +%s); end_iso=$(date -Iseconds)
  dur=$((end - start))
  if (( rc == 0 )); then status="ok"; else status="error"; fi

  printf '[DONE ] %-35s %3dm%02ds (%s)\n' "$label" $((dur/60)) $((dur%60)) "$status"
  printf '{"step":"%s","seconds":%d,"status":"%s","started_at":"%s","finished_at":"%s"}\n' \
         "$label" "$dur" "$status" "$start_iso" "$end_iso" >> "$log_json"

  return "$rc"  # <-- propagate success/failure to caller
}
