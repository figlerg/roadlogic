import os
import sys

# this_file = os.path.abspath(__file__)
# the_create_scenarios = os.path.dirname(this_file)
# the_project = os.path.dirname(the_create_scenarios)
# the_common_road_extendion = os.path.join(the_project, "commonroad_extensions")

# sys.path.insert(0, the_project)
# sys.path.insert(0, the_common_road_extendion)
import click

from commonroad_extensions.plan_execution.map_plan import map_plan
from create_scenarios.draw import draw
from commonroad.common.file_reader import CommonRoadFileReader
from pathlib import Path

#
from planning.Planner import Planner


@click.command()
@click.option('--osc-file', type=click.Path(exists=True), required=True)
@click.option('--n', type=int, default=10)
@click.option('--output-folder', type=click.Path(), required=True)
@click.option('--cr-scenario', type=click.Path(exists=True), required=True)
@click.option('--constants-override', type=click.Path(exists=True), required=False)
@click.option('--step-length', type=int, default=100)
@click.option('--rule-injection', type=click.Path(exists=True), required=False)


def main(osc_file, n, output_folder, cr_scenario, step_length, constants_override=None, rule_injection=None):
    
    # print(translate.__file__)
    # print(os.listdir(os.curdir))
    # n = 10
    # this_dir = os.path.dirname(__file__)
    # par_dir = os.path.dirname(this_dir)
    # osc_file = os.path.join(this_dir,'..','osc_files', 'my_overtake.osc')


    # output_folder = os.path.join(par_dir,'temp-debug','planner_generated')
    os.makedirs(output_folder, exist_ok=True)
    translator = Planner(osc_file, out_path=output_folder)

    parent_folder = os.path.dirname(os.path.abspath(__file__))
    top_folder = os.path.dirname(parent_folder)

    # controller_file = os.path.join(parent_folder,'controller.lp')
    controller_file = os.path.join(top_folder,'planning', 'asp', 'encoding', 'controller.lp')
    
    external_rule_files = [controller_file]

    if rule_injection:
        external_rule_files.append(rule_injection)
    
    # a bit messy: I want to easily load new constants into this program so we can easily generate models for a partition. simply supply the new file 
    if constants_override:
        external_rule_files.append(os.path.join(top_folder,'planning', 'asp', 'encoding', 'dynamics.lp'))
        external_rule_files.append(os.path.join(top_folder,'planning', 'asp', 'encoding', 'facts.lp'))
        external_rule_files.append(constants_override) # this is the actual input. constants.lp is swapped out by it

    # same as below, need the format to match for the invariant monitoring
    # custom_names = [os.path.join(output_folder,'serialized_models',f"{i+1:04d}.pkl") for i in range(n)]
    # TODO Do this better: for now I just create 10*n plans and pick every tenth
    plans = translator.plans(n=n, external_rules=external_rule_files, visualize=True, diversity_step=step_length,rules_override=constants_override)


    scenario, _ = CommonRoadFileReader(cr_scenario).open()
    # draw(scenario,planning_problem_set)

    os.makedirs(os.path.join(output_folder,'cr_scenarios'), exist_ok=True)

    for i,plan in enumerate(plans):
        print(p:=os.path.join(output_folder,'cr_scenarios',f'scenario_{i+1:04d}.xml'))
        new_planning_problem_set = map_plan(scenario=scenario, plan_model=plan, anchor_lane_idx=1, save_path=p)
        # draw(scenario, new_planning_problem_set)

if __name__ == '__main__':
    main()





