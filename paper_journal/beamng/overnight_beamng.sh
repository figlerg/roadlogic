#!/bin/bash
# BeamNG stress test over the journal benchmark's stored plans (no planning), in three phases, each usable on
# its own if the next one does not finish:
#   1. one scenario per experiment (28, about 45 minutes)
#   2. all scenarios of the experiments without variability (about 5 hours)
#   3. the first 10 scenarios of each variability experiment (about 1.5 hours)
# A fresh BeamNG per scenario, about 1.5 minutes each. Results: one JSON line per experiment and phase in
# paper_journal/beamng/stress_<date>_phase<N>.jsonl, traces in paper_journal/benchmark/out/<exp>/sim_beamng/.
# Run from the repository root:  nohup bash paper_journal/beamng/overnight_beamng.sh > beamng_overnight.log 2>&1 &
cd "$(dirname "$0")/../.." || exit 1
source venv/bin/activate || exit 1
DAY=$(date +%F)
O=paper_journal/benchmark/out
R=paper_journal/beamng/stress_${DAY}
RUN="python paper_journal/beamng/run_beamng.py"
PLAIN=$(ls -d $O/*/ | grep -v "_b/$")
VARIABILITY=$(ls -d $O/*_b/)

rm -rf $O/*/sim_beamng           # earlier BeamNG test runs, some made with older code
echo "$(date +%T) phase 1: one scenario per experiment"
$RUN $O/*/ --per-exp 1 --results ${R}_phase1.jsonl
echo "$(date +%T) phase 2: all scenarios, experiments without variability"
$RUN $PLAIN --skip-done --results ${R}_phase2.jsonl
echo "$(date +%T) phase 3: 10 scenarios per variability experiment"
$RUN $VARIABILITY --per-exp 10 --skip-done --results ${R}_phase3.jsonl
echo "$(date +%T) all done"
