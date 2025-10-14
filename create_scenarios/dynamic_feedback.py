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


from create_scenarios.heuristics import GenerationHeuristicEnum


@click.command()
@click.option('--osc-file', type=click.Path(exists=True), required=True)
@click.option('--n', type=int, default=10)
@click.option('--output-folder', type=click.Path(), required=True)  # should be folder which is the WD of the heuristic. forced by outside
@click.option('--cr-scenario', type=click.Path(exists=True), required=True)
@click.option('--heuristic', type=click.Choice(GenerationHeuristicEnum, case_sensitive=False))
@click.option('--rule-injection', type=click.Path(), required=False, default=None)

def main(osc_file, n, output_folder, cr_scenario, heuristic, rule_injection):
    """
    Prepares n plans in a feedback loop to improve results. Our ideas for the heuristic are something like that:
        
        inputs
        - current planning
        - archive (set of plans to establish similarity, not necessairly to be executed)
        - similarity matrix
        - validity of current planning
        - rules_archive
        output
        - either current planning or None (plans for execution)
        - modified_rules_archive

    This means we expect the heuristic to have access to these inputs and populate the "plans" variable with n plans.
    """
    
    os.makedirs(output_folder, exist_ok=True)
    planner = Planner(osc_file, out_path=output_folder)

    top_level_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    controller_file = os.path.join(top_level_dir, 'planning','controller.lp')

    print(controller_file)

    added_rules = list()
    added_rules.append(controller_file)

    if rule_injection:
        added_rules.append(rule_injection)

    plans = []  # output in the end
    plan_archive = []
    
    i = 0
    while len(plans) < n:
        i += 1

        step_length = 1
        plan = planner.plans(n=1, external_rules=added_rules,visualize=False, diversity_step=step_length)[0] # just get one planning
        plan_archive.append(plan)

        scenario, _ = CommonRoadFileReader(cr_scenario).open()
        # draw(scenario,planning_problem_set)

        os.makedirs(os.path.join(output_folder,'cr_scenarios'), exist_ok=True)

        ### LOGIC FOR ADDING RULES
        # translator.add_rule('not holds(state(ego,loc(10,0),dyn(Vel_lon,Vel_lat)), t).')  # just a test

        negated_atoms = [h for h in plan.holds if h[-1] == 1]


        match heuristic:
            # 0... disallow t=1 state of each actor in the next iteration
            # more diversity, but hits a wall quickly
            case GenerationHeuristicEnum.STRICT: 
                plans.append(plan)

                for a in negated_atoms:
                    planner.add_rule(not_rule(a, t=0))

            # 1... disallow t=1 conjunction of states of all actor in the next iteration (weaker constraint)
            # just explore!
            case GenerationHeuristicEnum.BASIC: 
                plans.append(plan)
                planner.add_rule(not_conjunction(negated_atoms,t=0))

            # 2... find where scenario becomes infeasible. disallow conjunction of states immediately before
            # consider validity. a bit smarter. take feasibility into account
            case GenerationHeuristicEnum.VALIDITY: 
                validation_directory = os.path.join(output_folder, "plan_validation")
                directory_containing_plots = os.path.join(validation_directory, f"plan_{i}")
                os.makedirs(directory_containing_plots, exist_ok=True)

                validity, ts = validate_plan(scenario, plan, anchor_lane_idx=1, output_folder=directory_containing_plots)
                
                if not validity:
                    t = ts[0] # the output is a l
                    
                    log_str = f"Plan {i} is " + ( "" if validity else "not" ) + " valid." + ( "" if validity else f" Collision at {t} / 10 s")
                    print(log_str)


                    t_int = t_conv(t)

                    planner.add_rule(not_conjunction(fetch_holds_t(plan, t_int), t=t_int))
                
                else:
                    # In this case I need to eliminate just the chosen planning, so it doesn't pick the same planning multiple times
                    # translator.add_rule(not_conjunction(planning.holds, t=t_int))
                    plans.append(plan)
                    planner.add_rule(not_conjunction(negated_atoms,t=0))
                    # translator.add_rule(not_plan(planning))
                
                # TODO Store to file?







        print(f"Feedback iteration #{i+1} complete.")


    plot_similarity_matrix(plans=plans,output_directory=output_folder)

    visualize_plans(plans,save_path=output_folder, show=False,save=True, max_num=n)   

    for i,plan in enumerate(plans):
        # print(planning.holds)
        print(p:=os.path.join(output_folder,'cr_scenarios',f'scenario_{i+1:04d}.xml'))
        new_planning_problem_set = map_plan(scenario=scenario, plan_model=plan, anchor_lane_idx=1, save_path=p)
        # draw(scenario, new_planning_problem_set)

def t_conv(t_sim):
    t = math.floor(t_sim/10)
    return t

        
def fetch_holds_t(plan:MyModel, t :float):

    out = [h for h in plan.holds if h[-1] == t]
    assert out, "t is beyound the planning time."

    return out

def not_rule(atom:MyPred, t:int):
    # returns a string representation of a "not atom." rule
    # not lane(1).
    # return f"not {atom}.\n"
    # return f":- {atom}.\n"
    atom_t = deepcopy(atom)
    atom_t.time = 't'
    return f":- {atom_t}, t={t}.\n"
     

def not_conjunction(atoms: List[MyPred], t):
    atoms_t = []

    for atom in atoms:
        atom_t = deepcopy(atom)
        atom_t.time = 't'
        atoms_t.append(str(atom_t))
    
    body_atoms_str = ', '.join(atoms_t)

    if not t:
        ts = set([a.time for a in atoms])
        assert len(ts) == 1, 'This function is intended to be used with several holds with the same t. If you just want to use the states with a manually defined t, then give this t as an input.'
        t = ts.pop()

    return f":- {body_atoms_str}, t={t}.\n"

def not_plan(plan:MyModel):
    # construct rules which disallow this exact planning TODO this is much stronger, it disallows any plans with one same position! fix

    out = f"% eliminate planning {plan.holds}\n"
    for t in range(plan.max_t+1):
        out += f"\t{not_conjunction(fetch_holds_t(plan,t),t)}"
    
    out+='\n'

    return out
        


if __name__ == '__main__':
    main()


    # eg run python create_scenarios/dynamic_feedback.py --osc-file osc_files/my_overtake_2.osc --n 5 --output-folder scenarios --cr-scenario scenarios_old/threelanes.xml




