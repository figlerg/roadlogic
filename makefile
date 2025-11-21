SHELL := /bin/bash

### MAIN VARIABLES

# The current directory
ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
# Check which venv exist
THE_PYTHON := $(shell if [ -f "venv/bin/python" ]; then echo venv/bin/python; else echo .venv/bin/python; fi )
# Define all the additional modules to import
ADDITIONAL_PYTHONPATH := $(ROOT_DIR):$(ROOT_DIR)/monitoring/syma-arv:$(ROOT_DIR):$(ROOT_DIR)/monitoring/syma
# Ensure that python has always the required path
PYTHON := export PYTHONPATH=$${PYTHONPATH}:$(ADDITIONAL_PYTHONPATH) ; $(THE_PYTHON)

# Host the options for the various commands
# Use default options for execution... Hopefully, they do not break anything
CLI_OPTS ?= --co config_planner.cost.cost_weights.velocity_offset 10.0 --co config_sim.simulation.max_steps 3.0
EXEC_OPTS ?=
PLOT_OPTS ?=

debug : 
	@echo $(ROOT_DIR)
	@echo $(THE_PYTHON)
	@echo $(ADDITIONAL_PYTHONPATH)
# @echo $(PYTHON) # this will call the python executable

PYTHON_CLI_WITH_OPTS=$(PYTHON) cli.py $(CLI_OPTS)


OUTPUT_FOLDER ?= experiments
OUTPUT_FOLDER := $(shell realpath $(OUTPUT_FOLDER))

SCENARIOS_FOLDER ?= scenarios
EXECUTION_OPTS ?= 
SCENARIOS_FOLDER := $(shell realpath $(SCENARIOS_FOLDER))
OSC_FILE ?= osc_files/my_overtake_2.osc
# OSC_FILE ?= osc_files/my_overtake.osc
OSC_FILE := $(shell realpath $(OSC_FILE))
OSC_N ?= 10
CR_SCENARIO_FILE ?= cr_scenarios/threelanes.xml
CR_SCENARIO_FILE := $(shell realpath $(CR_SCENARIO_FILE))

OSC_SCENARIOS := $(shell for I in $$(seq 1 $(OSC_N)); do printf "$(SCENARIOS_FOLDER)/osc2/cr_scenarios/scenario_%04d.xml\n" $$I; done | tr "\n" " ")

# Default utilities
SED=/usr/bin/sed
UNAME := $(shell uname)
# Override if on Mac Os. Assume that you have installed Gnu SED (gsed)
ifeq ($(UNAME),Darwin)
SED := $(shell echo /usr/local/bin/gsed)
endif

# XML := $(wildcard *.txt)

.PHONY: all

# # For each scenario we need to compute a list of metrics
# METRICS_LIST = HW TTC
# SCENARIO_LIST = $(shell find scenarios -iname "*.xml")

# scenario_id_list := $(shell find $(SCENARIOS_FOLDER) -iname "*.xml" | sed -e "s|.*scenario_||g" -e "s|.xml||g")
scenario_id_list := $(shell find $(SCENARIOS_FOLDER) -iname "*.xml" -exec basename {} \; | sed -e "s|.xml||g")

print-scenarios:
# @echo Scenarios found:
# @echo $(scenario_id_list)
	@echo "$(OSC_SCENARIOS)" | tr " " "\n"


# invoke cli.py compute-metrics --help to get the full list
metric_name_list := ACI AGS ALatReq ALongReq AReq BTN CALCT CI CPI CS CURRA CURRO CURRSA CURRV CURRYR CW10M CW20M CW5M DA DCE DFLLB DFLRB DFRLB DFRRB DST DeltaV ET HW INFTRAJSUM LatJ LongJ MSD PERCF PET PF PRI PSD PTTC P_MC P_SMH P_SRS RSS SOI SP STN TC TCI TET THW TIT TTB TTC TTCE TTCStar TTK TTM TTR TTS TTZ TV VH WTTC WTTR LANE LONGPOS


# selected_metrics := AGS ALatReq ALongReq BTN CALCT CURRA CURRO CURRSA CURRV CURRYR CW10M CW20M CW5M DA DCE DFLLB DFLRB DFRLB DFRRB HW LatJ LongJ MSD PERCF STN TC THW TTB TTC TTCE TTCStar TTK TTS VH
# selected_metrics := CURRA CURRO CURRSA CURRV CURRYR
selected_metrics := LANE LONGPOS
# CURRA is current acceleration, etc
# extract by changing this selected_metrics and then it collects them in csv files for each vehicle and instance in time
# maybe add position?
# option -j: parallelization. -j parallelizes the task 

# TTS takes a lot...
# # ALongReq and BTN failed for: baseline-4-agents-experiments/scenario_baseline_with_4_agents-26/BTN.csv baseline-4-agents-experiments/scenario_baseline_with_4_agents-27/BTN.csv
# Tons of out of projection domain errors

# STN, CPI Take ages ... is this worth it?
# TTR -> Takes ages to compute - Skip it
# TTM -> Crash with error - It requires a manouver input...

list-selected-metrics:
	@echo $(selected_metrics)

list-all-metrics:
	@echo $(metric_name_list)

list-scenario-ids:
	@echo "Scenario:"
	@echo $(scenario_id_list) | tr " " "\n"

# had to change for number padding
# OSC_SCENARIOS := $(shell for I in $$(seq $(OSC_N)); do echo $(SCENARIOS_FOLDER)/osc2/cr_scenarios/scenario_$$I.xml; done | tr "\n" " ") 



### THE BELOW DIDNT WORK: it just never triggered the xml generation

# generate-scenarios: .osc-generated

# clean-osc-scenarios:
# 	@rm -f .osc-generated

# #$(OSC_SCENARIOS) 
# .osc-generated: $(OSC_FILE)
# 	@rm -fvr $(SCENARIOS_FOLDER)/osc2
# 	$(PYTHON) create_scenarios/create_plan_scenarios.py --osc-file $(OSC_FILE) --n $(OSC_N) --output-folder $(SCENARIOS_FOLDER)/osc2 --cr-scenario $(CR_SCENARIO_FILE)
# 	touch .osc-generated


generate-osc-scenarios: .osc-generated

.osc-generated: $(OSC_SCENARIOS)
	touch .osc-generated

clean-osc-scenarios:
	@rm -f .osc-generated
	@rm -rf $(SCENARIOS_FOLDER)/osc2

# empty by default
CONSTANTS_OVERRIDE ?=
STEP_LENGTH ?=
RULE_INJECTION ?=

# NOTE I put the missing packages directly insider the create plan stuff
$(OSC_SCENARIOS)&: $(OSC_FILE)
	$(PYTHON) create_scenarios/create_plan_scenarios.py \
		--osc-file $(OSC_FILE) \
		--n $(OSC_N) \
		--output-folder $(SCENARIOS_FOLDER) \
		--cr-scenario $(CR_SCENARIO_FILE) \
		$(if $(RULE_INJECTION),--rule-injection $(RULE_INJECTION)) \
		$(if $(STEP_LENGTH),--step-length $(STEP_LENGTH)) \
		$(if $(CONSTANTS_OVERRIDE),--constants-override $(CONSTANTS_OVERRIDE))




# Create dynamic target to execute the scenarios found in the scenarios folder
define make-targets-for-scenario-executions

clean-scenario-$1:
	@rm -rfv $(OUTPUT_FOLDER)/$1

clean-all-scenarios: clean-scenario-$1

execute-scenario-$1: $(OUTPUT_FOLDER)/$1/simulation_00001/executed_scenario.xml

execute-all-scenarios: execute-scenario-$1

$(OUTPUT_FOLDER)/$1/simulation_00001/executed_scenario.xml :
	@echo "Executing $$@"
	@rm -rf $(OUTPUT_FOLDER)/$1/simulation_00001
	@rm -f $(OUTPUT_FOLDER)/$1/simulation_00001.log
	@mkdir -p $(OUTPUT_FOLDER)/$1
	$(eval SCENARIO_FILE=$(shell find $(SCENARIOS_FOLDER) -iname "*.xml" | grep $1.xml))
	$(PYTHON_CLI_WITH_OPTS) --output-folder $(OUTPUT_FOLDER)/$1 execute-scenario $(EXEC_OPTS) --scenario-file $(SCENARIO_FILE) --simulation-id 00001 \
		2>&1 | tee $(OUTPUT_FOLDER)/$1/simulation_00001.log
endef


define make-targets-for-plotting-scenarios

plot-scenario-$1: $(OUTPUT_FOLDER)/$1/simulation_00001/plots/.done

clean-plot-scenario-$1: 
	@rm -rvf $(OUTPUT_FOLDER)/$1/simulation_00001/plots

clean-plot-all-scenarios: clean-plot-scenario-$1

animate-scenario-$1: $(OUTPUT_FOLDER)/$1/simulation_00001/simulation.gif

clean-animate-scenario-$1: 
	@rm -vf $(OUTPUT_FOLDER)/$1/simulation_00001/simulation.gif

clean-animate-all-scenarios: clean-animate-scenario-$1

animate-all-scenarios: $(OUTPUT_FOLDER)/$1/simulation_00001/simulation.gif

$(OUTPUT_FOLDER)/$1/simulation_00001/plots/.done: $(OUTPUT_FOLDER)/$1/simulation_00001/executed_scenario.xml
	@echo "Plotting $$@"
	$(eval SCENARIO_FILE=$(shell find $(SCENARIOS_FOLDER) -iname "*.xml" | grep $1.xml))
	$(PYTHON_CLI_WITH_OPTS) --output-folder $(OUTPUT_FOLDER)/$1/simulation_00001/plots plot-simulation $(PLOT_OPTS) --simulation-folder $(OUTPUT_FOLDER)/$1/simulation_00001
	@touch $(OUTPUT_FOLDER)/$1/simulation_00001/plots/.done

$(OUTPUT_FOLDER)/$1/simulation_00001/simulation.gif: $(OUTPUT_FOLDER)/$1/simulation_00001/plots/.done
	@echo "Animating $$@"
	$(eval SCENARIO_FILE=$(shell find $(SCENARIOS_FOLDER) -iname "*.xml" | grep $1.xml))
	$(PYTHON_CLI_WITH_OPTS) --output-folder $(OUTPUT_FOLDER)/$1/simulation_00001 animate-simulation --plots-folder $(OUTPUT_FOLDER)/$1/simulation_00001/plots

endef

# gif generation with check on gifski
# python cli.py --output-folder experiments/00018 plot-simulation --simulation-folder experiments/00018/simulation_00001/

# Create dynamic target to compute all the metrics about all the scenarios found in the scenarios folder
define make-targets-for-metric-computation

$(OUTPUT_FOLDER)/$1/$2.csv: $(OUTPUT_FOLDER)/$1/simulation_00001/executed_scenario.xml
	@echo "Analyse $$@"
	$(PYTHON_CLI_WITH_OPTS) --output-folder $(OUTPUT_FOLDER)/$1 \
		compute-metrics \
			--metric $2 --simulation-folder $(OUTPUT_FOLDER)/$1/simulation_00001 --group-by SINGLE

compute-metric-$2-for-scenario-$1: $(OUTPUT_FOLDER)/$1/$2.csv

compute-metric-$2-for-all-scenarios: $(OUTPUT_FOLDER)/$1/$2.csv

compute-all-metrics-for-scenario-$1: $(OUTPUT_FOLDER)/$1/$2.csv

endef

compute-selected-metrics-for-all-scenarios:
	@echo "Done"
	
define make-group-targets-for-selected-metric-computation

compute-selected-metrics-for-scenario-$1: $(OUTPUT_FOLDER)/$1/$2.csv

compute-selected-metrics-for-all-scenarios: $(OUTPUT_FOLDER)/$1/$2.csv

endef

# Generating the targets for executing the scenarios based on the files in the scenario folder
$(foreach scenario_id,$(scenario_id_list),$(eval $(call make-targets-for-scenario-executions,$(scenario_id))))


# Generating the targets for plotting the scenarios based on the files in the scenario folder
$(foreach scenario_id,$(scenario_id_list),$(eval $(call make-targets-for-plotting-scenarios,$(scenario_id))))

# Generating the basic targets for computing single metrics
$(foreach metric_name,$(metric_name_list),$(foreach scenario_id,$(scenario_id_list),$(eval $(call make-targets-for-metric-computation,$(scenario_id),$(metric_name)))))

# Generating the group targets for computing all the metrics
# $(foreach metric_name,$(metric_name_list),$(foreach scenario_id,$(scenario_id_list),$(eval $(call make-group-targets-for-all-metric-computation,$(scenario_id),$(metric_name)))))

# Generating the group targets for computing only selected the metrics
$(foreach metric_name,$(selected_metrics),$(foreach scenario_id,$(scenario_id_list),$(eval $(call make-group-targets-for-selected-metric-computation,$(scenario_id),$(metric_name)))))


define make-scenario-analysis 


# $(OUTPUT_FOLDER)/$1/monitoring_results.csv: $(OUTPUT_FOLDER)/$1/LANE.csv $(OUTPUT_FOLDER)/$1/LONGPOS.csv
# 		$(PYTHON) monitoring/gen_monitoring_results.py \
# 			--output-folder $(OUTPUT_FOLDER)/$1/ \
# 			--osc-file $(OSC_FILE) \

# new version where I load the pickled plan as well for the invariant monitor
$(OUTPUT_FOLDER)/$1/monitoring_results.csv: \
  $(OUTPUT_FOLDER)/$1/LANE.csv \
  $(OUTPUT_FOLDER)/$1/LONGPOS.csv
	$(PYTHON) monitoring/gen_monitoring_results.py \
		--output-folder $(OUTPUT_FOLDER)/$1/ \
		--osc-file $(OSC_FILE) \
		--check-plan $(OUTPUT_FOLDER)/../serialized_models/$(patsubst scenario_%,%,$1).pkl

endef

$(foreach scenario_id,$(scenario_id_list),$(eval $(call make-scenario-analysis,$(scenario_id))))


generate-summary:$(OUTPUT_FOLDER)/summary_log.json

# generate-summary:$(OUTPUT_FOLDER)/summary_log.json

BLUEPRINT_FOLDER ?=

# $(OUTPUT_FOLDER)/summary_log.json: $(addprefix $(OUTPUT_FOLDER)/, $(addsuffix /monitoring_results.csv, $(scenario_id_list)))
# 	rm -f $(OUTPUT_FOLDER)/summary_log.json
# 	$(PYTHON) monitoring/aggregate_monitoring_results.py $(OUTPUT_FOLDER) $
$(OUTPUT_FOLDER)/summary_log.json: $(addprefix $(OUTPUT_FOLDER)/, $(addsuffix /monitoring_results.csv, $(scenario_id_list)))
	rm -f $(OUTPUT_FOLDER)/summary_log.json
	$(PYTHON) monitoring/aggregate_monitoring_results.py $(OUTPUT_FOLDER) $(BLUEPRINT_FOLDER)




####### Targets for the evaluation
# RQ1 can any of our heuristics generate valid scenarios?
HEURISTICS := $(shell $(PYTHON) create_scenarios/heuristics.py)

RULE_INJECTION ?= 

define setup_r1

clean-$1:
	$(RM) -r results/rq1/$1

results/rq1/$1/.ready:
	echo "Setting up Heuristic $1"
	$(PYTHON) create_scenarios/dynamic_feedback.py --output-folder results/rq1/$1 --heuristic $1 \
		--osc-file $(OSC_FILE)  --n $(OSC_N) --cr-scenario $(CR_SCENARIO_FILE) $(if $(RULE_INJECTION),--rule-injection $(RULE_INJECTION))
	touch results/rq1/$1/.ready

setup-rq1: clean-$1 results/rq1/$1/.ready

# for debugging my plan generation
setup-rq1-$1: clean-$1 results/rq1/$1/.ready

generate-summary-$1: results/rq1/$1/.ready
	@$(MAKE) --no-print-directory -j 8 \
		CLI_OPTS="--co config_planner.cost.cost_weights.velocity_offset 10.0 --co config_sim.simulation.max_steps 3.0" \
		SCENARIOS_FOLDER="results/rq1/$1/cr_scenarios" \
		OUTPUT_FOLDER="results/rq1/$1/cr_simulations" \
			generate-summary
	@cp results/rq1/$1/cr_simulations/summary_log.json results/rq1/summary_log_$1.json

generate-all-summaries: setup-rq1 generate-summary-$1

animate-heuristic-sim-$1: results/rq1/$1/.ready
	@$(MAKE) animate-all-scenarios SCENARIOS_FOLDER=results/rq1/$1/cr_scenarios OUTPUT_FOLDER=results/rq1/$1/cr_simulations


animate-all-heuristic-sims: animate-heuristic-sim-$1

generate-summaries-and-animations-$1: generate-summary-$1 animate-heuristic-sim-$1
generate-all-summaries-and-animations: setup-rq1 generate-summaries-and-animations-$1

endef

$(foreach h_name,$(HEURISTICS),$(eval $(call setup_r1,$(h_name))))



## I WOULD LIKE TO MOVE ALL ANIMATIONS TO A SPECIAL FOLDER FOR BETTER VIEWING
# define make-animation-folder-sim-targets
# # 1 is the heuristic, 2 is the scenario name
# move-sim-$2-$1 : results/rq1/$1/$2/simulation_00001/simulation.gif
# 	@mkdir -p results/rq1/$1/cr_animations
# 	@cp results/rq1/$1/$2/simulation_00001/simulation.gif results/rq1/$1/cr_animations/$2.gif
 
# endef

# $(foreach h,$(HEURISTICS), \
#   $(foreach s,$(scenario_id_list), \
#     $(eval $(call make-animation-folder-sim-targets,$(h),$(s)))))

# debug: move-sim
# 	echo 


# setup-rq1:
# Clean up the RQ1 folder
# 	$(RM) -r results/rq1
# Invoke the script
# 	$(PYTHON) rq1.py

# Executing RQ1 requires the following command:
# make -j 8 CLI_OPTS="--co config_planner.cost.cost_weights.velocity_offset 10.0" SCENARIOS_FOLDER="results/rq1/cr_scenarios" OUTPUT_FOLDER="results/rq1/cr_simulations" generate-summary



# # Usage: make setup-rq2
# VARIABILITY_OUTPUT_FOLDER ?= results/rq2
# VARIABILITY_INPUT_FOLDER ?= create_scenarios/variability_experiments_instances
# # Find all .lp files in the input folder's cr_scenarios subfolder
# LP_FILES := $(filter-out .ready,$(notdir $(basename $(wildcard $(VARIABILITY_INPUT_FOLDER)*.lp))))

# # Setup macro for RQ2 experiments
# define setup_variability_experiments

# # Setup target for RQ2 (cleans and creates .ready file)
# setup-rq2:
# 	@echo "Setting up RQ2 experiments in $(VARIABILITY_OUTPUT_FOLDER)"
# 	@$(RM) -r $(VARIABILITY_OUTPUT_FOLDER)
# 	@mkdir -p $(VARIABILITY_OUTPUT_FOLDER)
# 	@touch $(VARIABILITY_OUTPUT_FOLDER)/.ready

	

# # Generate monitoring_results.csv per scenario
# define make-scenario-analysis

# $(VARIABILITY_OUTPUT_FOLDER)/$1/monitoring_results.csv: $(VARIABILITY_OUTPUT_FOLDER)/$1/LANE.csv $(VARIABILITY_OUTPUT_FOLDER)/$1/LONGPOS.csv
# 	@$(PYTHON) monitoring/gen_monitoring_results.py $(VARIABILITY_OUTPUT_FOLDER)/$1/

# endef

# $(foreach lp_file,$(LP_FILES),$(eval $(call make-scenario-analysis,$(lp_file))))

# # Generate summary_log.json from list of monitoring_results.csv files
# $(VARIABILITY_OUTPUT_FOLDER)/summary_log.json: $(addprefix $(VARIABILITY_OUTPUT_FOLDER)/, $(addsuffix /monitoring_results.csv, $(LP_FILES)))
# 	@rm -f $(VARIABILITY_OUTPUT_FOLDER)/summary_log.json
# 	@$(PYTHON) monitoring/aggregate_monitoring_results.py $(VARIABILITY_OUTPUT_FOLDER)

# # Meta-target to generate all summaries
# generate-all-rq2-summaries: setup-rq2 $(addprefix $(VARIABILITY_OUTPUT_FOLDER)/, $(addsuffix /monitoring_results.csv, $(LP_FILES))) $(VARIABILITY_OUTPUT_FOLDER)/summary_log.json

# endef

# # Expand the macro
# $(eval $(call setup_variability_experiments))

