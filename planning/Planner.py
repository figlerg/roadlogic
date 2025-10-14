from collections import defaultdict

import argparse
import networkx as nx
import os
import shutil
import time
import warnings
from antlr4 import *
from typing import List,Union, Sequence

from planning.asp.MyModel import MyModel
from planning.asp.generate_plans import generate_plans, visualize_plans
from planning.intermediate_structure.TranslationGraph import TranslationGraph
from planning.parse.TranslationGraphVisitor import TranslationGraphVisitor
from planning.parse.generated.openscenario2Lexer import openscenario2Lexer
from planning.parse.generated.openscenario2Parser import openscenario2Parser
from planning.misc.errors import HardSyntaxErrorStrategy

## TODO appending planning/ at the start above should solve things for the makefile, but somehow the parsing craps out?


class Planner:
    """
    The API for the planning module. Create a Planner object, either from a OS2 file or an intermediate structure.
    """

    def __init__(self, osc_path, verbose=False, out_path=None, animate_plans=False):
        """
        Constructor which does the parsing of the input OSC file and initialises the structures for translation.

        @param osc_path: Input OSC2 file path.
        """
        input_stream = FileStream(osc_path)
        lexer = openscenario2Lexer(input_stream)
        stream = CommonTokenStream(lexer)
        parser = openscenario2Parser(stream)
        parser._errHandler = HardSyntaxErrorStrategy()
        ctx = parser.osc_file()

        visitor = TranslationGraphVisitor()
        self._translation_graph: TranslationGraph = visitor.visit(ctx)

        self.verbose = verbose
        if verbose:
            self._translation_graph.draw(show=True)

        self.visualize = animate_plans

        self.__additional_single_rules = None

        if out_path:
            self.__out_path = out_path
        else:
            # Get the directory of this file
            this_dir = os.path.dirname(__file__)
            parent_dir = os.path.dirname(this_dir)

            # Fallback path: ../generated relative to this file
            fallback_path = os.path.join(this_dir, "generated")

            # Ensure the folder exists
            os.makedirs(fallback_path, exist_ok=True)

            self.__out_path = fallback_path

        # Copy the input file to the output directory
        dst_path = os.path.join(self.__out_path, os.path.basename(osc_path))
        try:
            shutil.copy(osc_path, dst_path)
        except shutil.SameFileError:
            print(f"Skipped copying '{osc_path}' — source and destination are the same.")

    @property
    def out_path(self):
        return self.__out_path

    @out_path.setter
    def out_path(self, value):
        self.__out_path = value

    @property
    def translation_graph(self):
        return self._translation_graph

    @translation_graph.setter
    def translation_graph(self, value):
        self._translation_graph = value



    def plans(self, n, external_rules: Union[str, os.PathLike, Sequence[Union[str, os.PathLike]]] = None,
              visualize=True, imin=1, imax=30, show=False, diversity_step=1, time_limit = None,
              rules_override = False, deterministic=False) -> List[MyModel]:
        # simply returns plans in ASP format

        G = self._translation_graph
        actor_ids = [actor.id for actor in G.actors]

        # we select one path from the tree-like
        aut_path = next(nx.all_simple_paths(G.graph, 'init', 'fin'))
        warnings.warn('Picked one qualitative path from the translation graph. '
                      'If one_of operator is used, this constrains the search.'
                      'Finding all models may be addressed in a future release.')

        self.create_asp_instance(actor_ids, aut_path)

        this_dir = os.path.dirname(__file__)
        parent_dir = os.path.dirname(this_dir)
        files = [os.path.join(self.__out_path, 'instance.lp'),
                #  os.path.join(parent_dir, "asp/encoding/optimizations.lp")
                 ]

        if external_rules:
            if isinstance(external_rules, (list, tuple)):  # in case one loads multiple files at once
                for p in external_rules:
                    files.append(p)
            else:
                files.append(external_rules)  # can also use a simple path


        models = generate_plans(files=files, rules=self.__additional_single_rules, n=diversity_step * n, imin=imin,
                                imax=imax, save_path=self.__out_path, verbose=self.verbose, time_limit=time_limit,
                                override_files=rules_override, deterministic=deterministic)
        models = models[::diversity_step]

        if self.verbose:
            print(models)

        if visualize:
            visualize_plans(models, save=True, show=show, save_path=self.__out_path, verbose=self.verbose, max_num=n)

        return models

    def add_rule(self, rule: str):
        if self.__additional_single_rules is None:
            self.__additional_single_rules = list()

        self.__additional_single_rules.append(rule)


    # LOGIC ETC:

    def create_asp_instance(self, actor_ids, aut_path):

        instance_file_target = os.path.join(self.__out_path, 'instance.lp')

        G = self.translation_graph

        # infer the possible initial settings
        edge0 = (aut_path[0], aut_path[1])
        gamma0 = G.edges[edge0]['object']

        init_rules = ['init(state(ego,loc(0,0),dyn(1,0))).\n']

        grounded = {'ego'}
        remaining = set(actor_ids) - grounded

        pair_subconstraints = defaultdict(set)  # each pair of actors may have a relational constraint

        idx = {actor_str: i + 1 for i, actor_str in enumerate(actor_ids)}
        # I need to assign each actor a number so that the variable names are not swapped between actors

        for con in gamma0:
            key = (con.actor_1, con.actor_2)
            key_flipped = (con.actor_2, con.actor_1)
            pair_subconstraints[key].add(con)
            pair_subconstraints[key_flipped].add(con)

        while remaining:
            progress = False

            for a1 in list(remaining):

                usable_rels = {}
                for (key_a1, a2), constraint_set in pair_subconstraints.items():
                    if key_a1 != a1 or a2 not in grounded:
                        continue

                    modifiers = {con.modifier.value for con in constraint_set}
                    if "l" in modifiers and "p" in modifiers:
                        usable_rels[(a1, a2)] = constraint_set

                        subconstraints_strs = set()
                        for sub in pair_subconstraints[(a1, a2)]:
                            subconstraints_strs.update(sub.asp_goal_format(idx))

                        subconstraints_str = ', '.join(subconstraints_strs)

                        rule = (
                            f"1 {{ init(state({a1}, loc(S{idx[a1]}, L{idx[a1]}), dyn(1,0))) : "
                            f"segment(S{idx[a1]}),lane(L{idx[a1]}), {subconstraints_str} }} 1 \n\t"
                            f":- init(state({a2}, loc(S{idx[a2]}, L{idx[a2]}), dyn(1,0))).\n"
                        )

                        init_rules.append(rule)
                        progress = True

                remaining.remove(a1)

            if not progress:
                raise ValueError(f"Could not ground all actors — disconnected or circular constraints: {remaining}")

        goals_rules = []

        for i, _ in enumerate(aut_path):
            if i == 0 or i == len(aut_path) - 1:
                continue  # first handled above, last is out of bounds

            edge = (aut_path[i], aut_path[i + 1])
            gamma = G.edges[edge]['object']

            # the base is the part which needs to be in each of the goal rules
            rule = f'goal{i}(t) :- time(t), '

            # TODO this is probably not good yet. I just place all actors in the order of their appearance
            idx = {}
            for j, actor in enumerate(actor_ids):
                idx[actor] = j + 1
                rule += f'holds(state({actor},loc(S{j + 1},L{j + 1}),dyn(_,_)), T)'
                if j + 1 == len(actor_ids):
                    break
                else:
                    rule += ','  # not elegant

            # now add the goals one by one. These have to be true at the same time.
            done_atoms = set()
            for con in gamma:

                atoms = con.asp_goal_format(idx)

                atoms_str = ', ' + ', '.join(atoms)

                # here I want ',atom1,atom2,...'
                if atoms_str not in done_atoms:
                    rule += atoms_str
                    done_atoms.add(atoms_str)

            rule += '.\n'  # finish rule

            goals_rules.append(rule)

        # now we only need the assertion that the checklist is sat
        n = len(aut_path) - 1
        times = [f'T{i}' for i in range(1, n)]
        vehicles = [f'vehicle({actor}).\n' for actor in actor_ids]

        goals = [f'goal{i}(T{i})' for i in range(1, n)]

        # not sure why I added a constant to the final time. probably to see what is happening better on the animation
        # TODO maybe add this as a padding_param=1 above. It could be useful in general, but IMO not worth it computing for 5 more steps
        goal = f"goal({','.join(times)},t) :-  {','.join(goals)}, 0 <= {'<='.join(times)} <= t, t > {times[-1]} + 1.\n"
        goal_assertion = f":- query(t), not goal({','.join(['_'] * (n - 1))},t).\n"

        with open(instance_file_target, 'w') as f:
            f.write('% INITIAL SETUP FACTS:\n')  # just in-file documentation
            f.write('\n#program base.\n\n')  # all the initials are in base
            f.writelines(init_rules)  # the initials
            f.writelines(['\n'] + vehicles + ['\n'])

            f.write('\n#program check(t).\n\n')  # all the initials are in base

            f.write('% GOAL RULES:\n')
            f.write('time(t).\n\n')
            f.writelines(goals_rules)

            f.write('\n\n % GOAL ASSERTION:\n')
            f.write(goal)
            f.write(goal_assertion)

            # TODO I would like some movement, but this rule doesn't work
            # f.write('\n\n % MANUAL RULES:\n')
            # f.write(':- holds(state(_,loc(_,_),dyn(VEL,_)), T), VEL = 0, T>10.')

        print(f'Initial setup saved to temporary file {instance_file_target}!')








if __name__ == '__main__':

    start = time.time()

    parser = argparse.ArgumentParser()
    parser.add_argument("--osc2_file", default=r"planning/tests/my_overtake.osc")
    parser.add_argument("--planner_rules", default=r"planning/asp/road_planner.lp")
    parser.add_argument("--external_rules", default=None)
    parser.add_argument("--velocity", "-v", default=1)
    parser.add_argument("--nr_samples", "-n", default=1, type=int)
    parser.add_argument("--animate_plans", "-a", action="store_true", help="Enable planning animation")
    parser.add_argument("--deterministic", "-d", action="store_true", help="Switch off parallelization to make order of models deterministic")

    # Add a command-line argument for selecting the mode
    parser.add_argument('mode', choices=['save_gif', 'visualize', 'translate', 'plans'],
                        help="Select the mode: 'save_gif' or 'visualize' or 'translate' or 'plans'")

    parser.add_argument('--verbose', action='store_true', default=False, help='Show the intermediate results and '
                                                                              'visualisations.')

    args = parser.parse_args()

    osc_spec = args.osc2_file
    road_planner = args.planner_rules
    external_rules = args.external_rules
    mode = args.mode
    velocity = args.velocity
    verbose = args.verbose
    n = args.nr_samples
    animate_plans = (mode == 'visualize') or args.animate_plans
    deterministic = args.deterministic

    planner = Planner(osc_spec, verbose=verbose, animate_plans=animate_plans)


    for plan in planner.plans(n, external_rules=external_rules, visualize=animate_plans, show=False,
                              deterministic=deterministic):
        print(plan)

    # plans1 = [p for p in planner.plans(n, external_rules=external_rules, visualize=animate_plans, show=False,deterministic=deterministic)]
    # plans2 = [p for p in planner.plans(n, external_rules=external_rules, visualize=animate_plans, show=False,deterministic=deterministic)]
    # print(plans1==plans2)

    print(f"Elapsed: {time.time() - start:.3f} s")
