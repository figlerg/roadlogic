EXP=experiments_src/exp_008_b
LOG="$EXP/out/times.log"

gio trash $EXP/out/; # reset things
mkdir $EXP/out/

N=100

time_step () {
  local label="$1"; shift
  local start end dur
  start=$(date +%s)
  echo "[START] $label" | tee -a "$LOG"
  "$@"
  end=$(date +%s)
  dur=$((end - start))
  printf "[DONE ] %-35s %3dm%02ds\n" "$label" $((dur/60)) $((dur%60)) | tee -a "$LOG"
}

time_step "create_variability_instances" \
python create_scenarios/create_variability_instances.py \
	--output-folder $EXP/out/partitions/ \
	--n $N

time_step "variability_experiments" \
python create_scenarios/variability_experiments.py \
	--output-folder $EXP/out \
	--input-folder $EXP/out/partitions/ \
	--osc-file $EXP/in/spec.osc \
	--cr-scenario cr_scenarios/threelanes.xml \

time_step "execute-all-scenarios" \
make execute-all-scenarios \
	SCENARIOS_FOLDER=$EXP/out/cr_scenarios \
	OUTPUT_FOLDER=$EXP/out/cr_simulations

time_step "generate-summary" \
make generate-summary \
	SCENARIOS_FOLDER=$EXP/out/cr_scenarios \
	OUTPUT_FOLDER=$EXP/out/cr_simulations

echo "Timing summary written to $LOG"
