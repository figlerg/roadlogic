#!/bin/bash
# Overnight 2026-11-26: the journal benchmark's stored plans in BeamNG (this laptop) and CARLA (the server at
# ROADLOGIC_CARLA_HOST), at the same time, with all fixes up to 124121f (cars follow their lane after the plan and
# keep their gap, collision detection). Two chains, each in its own log:
#   A  BeamNG: all scenarios of the experiments without variability, 10 per variability experiment   (about 7 h)
#      then 10 videos in exports/videos_<date>/                                                      (about 1 h)
#   B1 CARLA: all scenarios of all experiments, including every variability scenario                   (about 4.5 h)
#   B2 CARLA: three experiments simulated a second time, to measure reproducibility                   (about 15 min)
#   B3 CARLA and Frenetix: the experiments without variability planned with safety_distance=8           (about 3 h)
#   B4 CARLA: the same 10 videos                                                                      (about 30 min)
# Results: paper_journal/beamng/{beamng,carla}_<date>_*.jsonl, tune_<date>_gap8.jsonl, traces in
# paper_journal/benchmark/out/<exp>/sim_beamng/ and sim_carla/. Both machines must stay awake, CARLA running.
# Run from the repository root:  nohup bash paper_journal/beamng/overnight_both.sh > overnight_both.log 2>&1 &
cd "$(dirname "$0")/../.." || exit 1
source venv/bin/activate || exit 1
export ROADLOGIC_CARLA_HOST=${ROADLOGIC_CARLA_HOST:-192.168.1.108}
DAY=$(date +%F)
O=paper_journal/benchmark/out
R=paper_journal/beamng
RUN="python paper_journal/beamng/run_beamng.py"
ALL=$(ls -d $O/*/ | grep -v "/tune_")
PLAIN=$(echo "$ALL" | grep -v "_b/$")
VARIABILITY=$(echo "$ALL" | grep "_b/$")
SPECS=$(for d in $PLAIN; do n=$(basename $d); ls $O/$n/serialized_models/*.pkl >/dev/null 2>&1 && echo $n; done)

timeout 5 bash -c "</dev/tcp/$ROADLOGIC_CARLA_HOST/2000" || { echo "CARLA not reachable at $ROADLOGIC_CARLA_HOST:2000"; exit 1; }

chain_beamng() {
    echo "$(date +%T) A: BeamNG, experiments without variability"
    $RUN $PLAIN --results $R/beamng_${DAY}_plain.jsonl
    echo "$(date +%T) A: BeamNG, 10 per variability experiment"
    $RUN $VARIABILITY --per-exp 10 --results $R/beamng_${DAY}_variability.jsonl
    echo "$(date +%T) A: BeamNG videos"
    videos beamng
    echo "$(date +%T) A done"
}

# Videos of a selection in one simulator ($1: beamng or carla), with all fixes, named after the simulator's and
# Frenetix's verdicts, in exports/videos_<date>/. A video run simulates the scenario again (BeamNG repeats exactly,
# CARLA to within a few centimetres).
videos() {
    local sim=$1
    V=exports/videos_${DAY}
    mkdir -p $V
    for job in "exp_001 0001" "exp_002 0001" "exp_003 0001" "exp_005 0001" "exp_007 0002" "speed_relative 0001" \
               "keep_scenario_scope 0003" "keep_phase_scope 0001" "one_of_nested 0001" "duration_nested 0001"; do
        set -- $job
        $RUN $O/$1 --scenarios $2 --video --backend $sim --results $V/index_${sim}.jsonl
        tag=$(python3 -c "import json;r=[json.loads(l) for l in open('$V/index_${sim}.jsonl')][-1];b=r['beamng']['$2'];c=r['commonroad']['$2'];k=r['collisions'].get('$2');print(('${sim}_pos' if b=='POSITIVE' else '${sim}_neg')+('_frenetix_pos' if c=='POSITIVE' else '_frenetix_neg')+('_collision' if k else ''))")
        cp $O/$1/sim_${sim}/scenario_$2/scenario_$2.mp4 "$V/${sim}_${1}_${2}_${tag}.mp4"
    done
}

chain_carla() {
    echo "$(date +%T) B1: CARLA, all scenarios"
    $RUN $ALL --backend carla --results $R/carla_${DAY}_all.jsonl
    echo "$(date +%T) B2: CARLA, second run of exp_002 exp_004 speed_relative"
    for e in exp_002 exp_004 speed_relative; do
        mkdir -p $O/$e/sim_carla_run1 && cp -r $O/$e/sim_carla/. $O/$e/sim_carla_run1/
    done
    $RUN $O/exp_002 $O/exp_004 $O/speed_relative --backend carla --results $R/carla_${DAY}_repeat.jsonl
    echo "$(date +%T) B3: safety_distance=8, CARLA and Frenetix"
    python paper_journal/beamng/tune_constants.py $R/tune_${DAY}_gap8.jsonl --settings gap8 --specs $SPECS \
        --n 10 --backend carla --plan-limit 1800
    echo "$(date +%T) B4: CARLA videos"
    videos carla
    echo "$(date +%T) B done"
}

chain_beamng > overnight_beamng_chain.log 2>&1 &
chain_carla > overnight_carla_chain.log 2>&1 &
wait
echo "$(date +%T) all done"
