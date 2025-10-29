import os
import click

from commonroad_extensions.plan_execution.map_plan import map_plan, plot_similarity_matrix, compute_similarity_matrix, feasibility_checker, validate_plan
from create_scenarios.draw import draw
from commonroad.common.file_reader import CommonRoadFileReader

from planning.Planner import Planner
from planning.asp.MyModel import MyModel, MyPred
from planning.asp.generate_plans import visualize_plans
from copy import deepcopy
from typing import List
import math
import json
import shutil

import concurrent.futures

from planning.asp.generate_plans import NoModelException

from pathlib import Path


from create_scenarios.heuristics import GenerationHeuristicEnum


@click.command()
@click.option('--osc-file', type=click.Path(exists=True), required=True)
@click.option('--input-folder', type=click.Path(), required=True)  # should be folder which is the WD of the heuristic. forced by outside
@click.option('--output-folder', type=click.Path(), required=True)  # should be folder which is the WD of the heuristic. forced by outside
@click.option('--cr-scenario', type=click.Path(exists=True), required=True)
@click.option('--time-limit', default=30)
@click.option("--override/--no-override", default=True, help="Enable or disable override.")
@click.option('--rule-injection', type=click.Path(exists=True), required=False)


def main(osc_file, input_folder, output_folder, cr_scenario, time_limit, override, rule_injection):
    """
    Assume there are some .lp files with additional constraints in input_folder. 
    Simply create n plans for the automatic ASP rules + each of the .lp files. 
    In the end we want to run simulations and monitors for each planning, then compare the results.
    """


    os.makedirs(output_folder, exist_ok=True)

    top_level_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    controller_file = os.path.join(top_level_dir, 'planning','controller.lp')

    print(controller_file)

    plans = []  # output in the end

    scenario, _ = CommonRoadFileReader(cr_scenario).open()

    names = list()
    report = dict()

    for entry in os.scandir(input_folder):
        
        if entry.is_file() and entry.name.endswith(".lp"):
            
            name = os.path.splitext(entry.name)[0]
            print(f"Generating plans for ruleset {name}.")

            rule_sets = [os.path.abspath(controller_file), os.path.abspath(entry.path)]

            if rule_injection:
                rule_sets.append(rule_injection)
                
            rule_sets.append(os.path.abspath('planning/asp/encoding/dynamics.lp'))
            rule_sets.append(os.path.abspath('planning/asp/encoding/facts.lp'))

            sub_folder = os.path.join(output_folder,"aux_asp", name)
            os.makedirs(sub_folder, exist_ok=True)


            new_plan, report[name] = invoke_planner(sub_folder,name,osc_file,rule_sets, time_limit, override=override)


            if new_plan:
                names.append(name)
                plans.append(new_plan)
                print(p:=os.path.join(output_folder,'cr_scenarios',f'scenario_{name}.xml'))
                new_planning_problem_set = map_plan(scenario=scenario, plan_model=new_plan, anchor_lane_idx=1, save_path=p)

    out_path = os.path.join(output_folder, "summary.json")
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    if plans:
        visualize_plans(plans,save_path=output_folder, show=False,save=True, custom_names=names, max_num=len(plans)+1)   

    
    # TODO this will be quite useless without the list of plans, as I split them into several folders
    # plot_similarity_matrix(plans=plans,output_directory=os.path.join(output_folder,'similarity'))

def invoke_planner(sub_folder, name, osc_file, rule_sets, time_limit, override = True):
    planner = Planner(osc_file, out_path=sub_folder)  # need to reinitialize so the out path is correct
    new_plan = None
    
    try:
        new_plan = planner.plans(n=1, external_rules=rule_sets, visualize=False, diversity_step=1, time_limit=time_limit,rules_override=override)[0]
        status = 'SAT'
    except NoModelException:
        print(f"No planning found for rule set injection {name} in folder {sub_folder}.")
        status = "NoModelException"
    except TimeoutError:
        print(f"No planning found for rule set injection {name} in folder {sub_folder} due to timeout (limit is {time_limit}s).")
        status = "TimeoutError"
    except RuntimeError as e:
        print(f"Exception ({e}) raised for example {name}. Is the clingo syntax correct?")
        status = "RuntimeError/parsing problem"
    except Exception as e:
        print(f"Exception ({e}) raised for example {name}.")
        status = str(e)

        print(f"Saving plans for ruleset {name} in folder {sub_folder}.")

        
    return new_plan, status

if __name__ == '__main__':
    main()


    # eg run python create_scenarios/dynamic_feedback.py --osc-file osc_files/my_overtake_2.osc --n 5 --output-folder scenarios --cr-scenario scenarios_old/threelanes.xml




