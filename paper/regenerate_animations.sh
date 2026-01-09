#!/usr/bin/env bash
set -euo pipefail





# DRY RUN by default — set to 0 to actually delete
DRY_RUN=0


run() {
  if [[ "${DRY_RUN:-1}" -eq 1 ]]; then
    echo "[dry-run] $*"
    return 0
  fi
  echo "[run] $*"
  "$@"
}




targets=(
  # --- PLOT 1: overtake ---
  "paper/02_trajectory_vis/01_overtake/out/cr_simulations/scenario_0002/simulation_00001"

  # --- PLOT 2: fake overtake ---
  "paper/02_trajectory_vis/02_fake_overtake/out/cr_simulations/scenario_0001/simulation_00001"

  # --- PLOT 3a ---
  "paper/02_trajectory_vis/03_similarity/out/cr_simulations/scenario_change_dur_3__init_distance_11__max_acceleration_while_turning_0__max_braking_speed_while_turning_2__max_lane_1__max_segment_300__safety_distance_5/simulation_00001"

  # --- PLOT 3b ---
  "paper/02_trajectory_vis/03_similarity/out/cr_simulations/scenario_change_dur_3__init_distance_11__max_acceleration_while_turning_2__max_braking_speed_while_turning_4__max_lane_1__max_segment_300__safety_distance_5/simulation_00001"

  # --- PLOT 3c ---
  "paper/02_trajectory_vis/03_similarity/out/cr_simulations/scenario_change_dur_3__init_distance_16__max_acceleration_while_turning_0__max_braking_speed_while_turning_3__max_lane_1__max_segment_300__safety_distance_5/simulation_00001"

  # --- PLOT 3d ---
  "paper/02_trajectory_vis/03_similarity/out/cr_simulations/scenario_change_dur_3__init_distance_12__max_acceleration_while_turning_0__max_braking_speed_while_turning_2__max_lane_1__max_segment_300__safety_distance_5/simulation_00001"
)

echo "[cleanup] DRY_RUN=$DRY_RUN"
echo

for simdir in "${targets[@]}"; do
  # hard safety checks
    if [[ ! -d "$simdir" ]]; then
    echo "[skip] missing dir: $simdir"
    continue
  fi

  # allow only: paper/02_trajectory_vis/.../simulation_00001 (relative)
  # or: */paper/02_trajectory_vis/.../simulation_00001 (absolute)
  if [[ "$simdir" != paper/02_trajectory_vis/*/simulation_00001 && "$simdir" != */paper/02_trajectory_vis/*/simulation_00001 ]]; then
    echo "[skip] path rejected by safety rule: $simdir"
    continue
  fi


  gif="$simdir/simulation.gif"
  plots="$simdir/plots"

  echo "[target] $simdir"

  if [[ -f "$gif" ]]; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "  would remove file: $gif"
    else
      rm -f -- "$gif"
      echo "  removed file: $gif"
    fi
  else
    echo "  file not found: $gif"
  fi

  if [[ -d "$plots" ]]; then
    if [[ "$DRY_RUN" -eq 1 ]]; then
      echo "  would remove dir:  $plots"
    else
      rm -rf -- "$plots"
      echo "  removed dir:  $plots"
    fi
  else
    echo "  dir not found:  $plots"
  fi

  echo
done


echo "[animate] DRY_RUN=${DRY_RUN:-1}"
run bash paper/02_trajectory_vis/01_overtake/animate.sh
run bash paper/02_trajectory_vis/02_fake_overtake/animate.sh
run bash paper/02_trajectory_vis/03_similarity/animate.sh




echo "[cleanup] done."
echo "Review output carefully."
echo "When satisfied, set DRY_RUN=0 and re-run."