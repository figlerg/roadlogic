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
from planning.intermediate_structure.Constraint import RelativeConstraint, AbsoluteConstraint, Modifier
from planning.parse.TranslationGraphVisitor import TranslationGraphVisitor
from planning.parse.generated.openscenario2Lexer import openscenario2Lexer
from planning.parse.generated.openscenario2Parser import openscenario2Parser
from planning.misc.errors import HardSyntaxErrorStrategy



## TODO appending planning/ at the start above should solve things for the makefile, but somehow the parsing craps out?


# How the phase goals are combined into acceptance of a plan. Change these two to switch back.
#
# "tuple"    the original encoding: one goal(T1,...,Tn,t) rule over every ordered tuple of goal
#            times. Its grounding grows like t^(n-1) in the number of phase boundaries.
# "boundary" the same acceptance condition written per boundary, which grows linearly. The
#            goal(T1,...,Tn,t) atoms are rebuilt in Python after solving, so code reading them
#            sees the same atoms. Needed for keep constraints scoped to a phase.
GOAL_ENCODING = "tuple"

# True keeps the original requirement that a plan runs two more steps after its last goal, which
# made the animations play out longer. False ends every plan exactly at the first step at which
# all goals are met, even when plans are collected over several horizons.
PAD_AFTER_GOALS = True


def _flatten_node(node):
    """Component labels of a translation-graph node. Parallel composition makes tuples of them."""
    if isinstance(node, tuple):
        return {label for part in node for label in _flatten_node(part)}
    return {node}


def _ordered_splits(times, lower=0):
    """Every non-decreasing choice of one time per boundary, from the times each goal holds."""
    if not times:
        yield ()
        return
    for t in times[0]:
        if t >= lower:
            for rest in _ordered_splits(times[1:], t):
                yield (t,) + rest


def reconstruct_goal_atoms(model, n_boundaries, pad, from_passes):
    """Add the goal(T1,...,Tn,t) atoms the tuple encoding would have derived for this plan.

    Under the boundary encoding the solver never builds the tuple, but map_plan chooses among all
    valid splits to find the gentlest lane change, so they are rebuilt from the goal_i atoms with
    the same condition as the tuple rule: 0 <= T1 <= ... <= Tn <= t, plus t > Tn + 1 when padding.
    With phase-scoped keeps only the split the solver chose is valid, so that one is used.
    """
    from planning.asp.MyModel import MyPred

    if from_passes:
        chosen = {pred.arguments[0]: pred.arguments[1] for pred in model if pred.name == "pass"}
        splits = [tuple(chosen[i] for i in range(1, n_boundaries + 1))]
    else:
        times = [sorted(pred.arguments[0] for pred in model if pred.name == f"goal{i}")
                 for i in range(1, n_boundaries + 1)]
        splits = list(_ordered_splits(times))

    first = 2 if pad else 0
    for split in splits:
        for t in range(split[-1] + first, model.max_t + 1):
            model.symbols.append(MyPred("goal", list(split) + [t]))
    return model


class Planner:
    """
    The API for the planning module. Create a Planner object, either from a OS2 file or an intermediate structure.
    """

    def __init__(self, osc_path, verbose=False, out_path=None, animate_plans=False,
                 goal_encoding=None, pad_after_goals=None):
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

        # Read the module switches at call time, so changing them at runtime takes effect.
        self.goal_encoding = GOAL_ENCODING if goal_encoding is None else goal_encoding
        if self.goal_encoding not in ("tuple", "boundary"):
            raise ValueError(f"Unknown goal encoding '{self.goal_encoding}', use 'tuple' or 'boundary'.")
        self.pad_after_goals = PAD_AFTER_GOALS if pad_after_goals is None else pad_after_goals

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
              rules_override = False, deterministic=True) -> List[MyModel]:
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

        if self.goal_encoding == "boundary":
            for model in models:
                reconstruct_goal_atoms(model, self._acceptance["boundaries"], self.pad_after_goals,
                                       from_passes=self._acceptance["choice"])

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

        # --- decide mode: legacy (relative-only) vs. absolute-aware ---
        # Only placement constraints decide this. A speed constraint says nothing about where an
        # actor starts, so counting it here would drop the legacy anchor without replacing it and
        # leave the actor ungroundable.
        has_absolute = any(isinstance(c, AbsoluteConstraint) and c.modifier != Modifier.SPEED
                           for c in gamma0)

        # Actors whose initial velocity is constrained. Their init rule needs a variable in the
        # dyn term instead of the hardcoded 1, and every reference to that init must match.
        speed_actors = {c.actor for c in gamma0
                        if isinstance(c, AbsoluteConstraint) and c.modifier == Modifier.SPEED}
        speed_actors |= {a for c in gamma0
                         if isinstance(c, RelativeConstraint) and c.modifier == Modifier.SPEED
                         for a in (c.actor_1, c.actor_2)}
        # A scenario-scoped speed invariant covers t=0 as well, since holds(F,0) :- init(F).
        # Its actor therefore needs a free initial velocity too, otherwise the hardcoded 1
        # contradicts the invariant and the specification is unsatisfiable for the wrong reason.
        speed_actors |= {a for inv in G.invariants
                         if inv.scope is None and inv.modifier == Modifier.SPEED
                         for a in inv.actors}

        def dyn_term(actor):
            """dyn(...) for an actor's init atom, plus the domain atom its variable needs."""
            if actor in speed_actors:
                return f"dyn(V{idx[actor]},0)", f"velocity_lon(V{idx[actor]})"
            return "dyn(1,0)", None

        idx = dict()

        warnings.warn(
            "Legacy initialization: ego fixed at lane index 2. "
            "This assumes a 3-lane road (with lane ids 1,2,3) and must be removed in future versions.",
            RuntimeWarning
        )


        if has_absolute:
            # no fixed ego anchor; let constraints define everything
            init_rules = []
            grounded = set()
        else:
            placement=2
            # legacy mode: ego is anchor at (0,placement) -> lane "placement" as default
            idx['ego'] = placement
            if 'ego' in speed_actors:
                # The anchor is still fixed in place, but its initial velocity is chosen rather
                # than pinned to 1, so a speed constraint or invariant can decide it.
                conditions = [f"velocity_lon(V{placement})"]
                conditions += sorted(
                    atom
                    for c in gamma0
                    if isinstance(c, AbsoluteConstraint) and c.modifier == Modifier.SPEED
                    and c.actor == 'ego'
                    for atom in c.asp_goal_format({'ego': placement})
                )
                init_rules = [
                    f"1 {{ init(state(ego,loc(0,{placement}),dyn(V{placement},0))) : "
                    f"{', '.join(conditions)} }} 1.\n"
                ]
            else:
                init_rules = [f'init(state(ego,loc(0,{placement}),dyn(1,0))).\n']
            grounded = {'ego'}

        remaining = set(actor_ids) - grounded
        remaining = sorted(remaining)

        try:
            remaining.remove('obstacle')
            warnings.warn(
                "'obstacle' is a special variable name and is used to encode static obstacles. "
                "Make sure this is what you want."
            )
        except (KeyError, ValueError):
            pass

        pair_subconstraints = defaultdict(set)   # each pair of actors may have relational constraints
        abs_constraints = defaultdict(set)       # absolute constraints per actor

        # I need to assign each actor a number so that the variable names are not swapped between actors
        already_indexed_no = len(idx)
        idx.update({actor_str: already_indexed_no + i for i, actor_str in enumerate(sorted(actor_ids))})

        # collect relative + absolute constraints on the initial edge
        for con in sorted(gamma0, key=str):
            if isinstance(con, RelativeConstraint):
                con.standardize()  # just to be safe, flip this to alphabetical version to eliminate nondeterminism
                key = (con.actor_1, con.actor_2)
                key_flipped = (con.actor_2, con.actor_1)
                pair_subconstraints[key].add(con)
                pair_subconstraints[key_flipped].add(con)
            elif isinstance(con, AbsoluteConstraint):
                abs_constraints[con.actor].add(con)

        # --- if we are in absolute-aware mode, first ground actors that are fully constrained absolutely ---
        if has_absolute:
            for a in list(remaining):
                cons_abs = abs_constraints.get(a, set())
                # use the string values of the modifiers, like in the relative case
                mods = {c.modifier.value for c in cons_abs}

                # require both lane and position absolutes to ground purely from absolutes
                if "l" in mods and "p" in mods:
                    subconstraints_strs = set()
                    for c in cons_abs:
                        subconstraints_strs.update(c.asp_goal_format(idx))

                    dyn, vel_atom = dyn_term(a)
                    if vel_atom:
                        subconstraints_strs.add(vel_atom)

                    subconstraints_str = ', '.join(sorted(subconstraints_strs)) if subconstraints_strs else 'true'

                    rule = (
                        f"1 {{ init(state({a}, loc(S{idx[a]}, L{idx[a]}), {dyn})) : "
                        f"segment(S{idx[a]}),lane(L{idx[a]}), {subconstraints_str} }} 1.\n"
                    )

                    init_rules.append(rule)
                    grounded.add(a)
                    remaining.remove(a)

        # --- existing relative-constraint logic, now possibly on top of absolute-anchored actors ---
        while remaining:
            progress = False

            for a1 in sorted(list(remaining)):

                usable_rels = {}
                for (key_a1, a2), constraint_set in pair_subconstraints.items():
                    if key_a1 != a1 or a2 not in grounded:
                        continue

                    modifiers = {con.modifier.value for con in constraint_set}
                    if "l" in modifiers and "p" in modifiers:
                        usable_rels[(a1, a2)] = constraint_set

                        subconstraints_strs = set()
                        # relative constraints between a1 and a2
                        for sub in pair_subconstraints[(a1, a2)]:
                            subconstraints_strs.update(sub.asp_goal_format(idx))

                        # also include any absolute constraints on a1 (if present)
                        for c_abs in abs_constraints.get(a1, set()):
                            subconstraints_strs.update(c_abs.asp_goal_format(idx))

                        dyn1, vel_atom1 = dyn_term(a1)
                        dyn2, _ = dyn_term(a2)
                        if vel_atom1:
                            subconstraints_strs.add(vel_atom1)

                        subconstraints_str = ', '.join(sorted(subconstraints_strs))

                        rule = (
                            f"1 {{ init(state({a1}, loc(S{idx[a1]}, L{idx[a1]}), {dyn1})) : "
                            f"segment(S{idx[a1]}),lane(L{idx[a1]}), {subconstraints_str} }} 1 \n\t"
                            f":- init(state({a2}, loc(S{idx[a2]}, L{idx[a2]}), {dyn2})).\n"
                        )

                        init_rules.append(rule)
                        grounded.add(a1)
                        progress = True

                        # Only drop an actor once it is actually grounded. This used to run
                        # unconditionally, which emptied `remaining` regardless of progress and
                        # made the error below report an empty list, hiding which actors were
                        # stuck.
                        remaining.remove(a1)
                        break

            if not progress:
                raise ValueError(
                    f"Could not ground all actors: {sorted(remaining)}. Each needs either "
                    f"absolute lane and position constraints, or lane and position constraints "
                    f"relative to an already grounded actor. Grounded so far: {sorted(grounded)}."
                )

        init_rules = sorted(init_rules)


        goals_rules = []

        for i, _ in enumerate(aut_path):
            if i == 0 or i == len(aut_path) - 1:
                continue  # first handled above, last is out of bounds

            edge = (aut_path[i], aut_path[i + 1])
            gamma = G.edges[edge]['object']

            edge_actor_ids = set()
            for con in gamma:
                if isinstance(con, RelativeConstraint):
                    edge_actor_ids.add(con.actor_1)
                    edge_actor_ids.add(con.actor_2)
                elif isinstance(con, AbsoluteConstraint):
                    edge_actor_ids.add(con.actor)
            
            edge_actor_ids = sorted(list(edge_actor_ids), key=str)

            # the base is the part which needs to be in each of the goal rules.
            # An edge with no constraints contributes no body atoms, so the comma after time(t)
            # is only written when something follows it. Without this the rule came out as
            # "goal1(t) :- time(t), ." and clingo refused to parse the whole instance. That
            # happens whenever a phase constrains only its start, leaving its outgoing edge
            # empty, which is a perfectly ordinary specification.
            rule = f'goal{i}(t) :- time(t)'
            if edge_actor_ids:
                rule += ', '

            # TODO this is probably not good yet. I just place all actors in the order of their appearance
            # Actors whose velocity this edge constrains need a variable in the dyn term.
            # Everyone else keeps the anonymous wildcards, so instances without speed
            # constraints are generated exactly as before.
            edge_speed_actors = {c.actor for c in gamma
                                 if isinstance(c, AbsoluteConstraint) and c.modifier == Modifier.SPEED}
            edge_speed_actors |= {a for c in gamma
                                  if isinstance(c, RelativeConstraint) and c.modifier == Modifier.SPEED
                                  for a in (c.actor_1, c.actor_2)}

            idx = {}
            for j, actor in enumerate(edge_actor_ids):
                idx[actor] = j + 1
                vel = f'V{j + 1}' if actor in edge_speed_actors else '_'
                rule += f'holds(state({actor},loc(S{j + 1},L{j + 1}),dyn({vel},_)), t)'
                if j + 1 == len(edge_actor_ids):
                    break
                else:
                    rule += ','  # not elegant

            # now add the goals one by one. These have to be true at the same time.
            done_atoms = set()
            for con in sorted(gamma, key=str):

                atoms = con.asp_goal_format(idx)

                atoms_str = ', ' + ', '.join(sorted(atoms))

                # here I want ',atom1,atom2,...'
                if atoms_str not in done_atoms:
                    rule += atoms_str
                    done_atoms.add(atoms_str)

            rule += '.\n'  # finish rule

            goals_rules.append(rule)

        goals_rules = sorted(goals_rules)

        # now we only need the assertion that the checklist is sat
        n = len(aut_path) - 1
        times = [f'T{i}' for i in range(1, n)]
        vehicles = [f'vehicle({actor}).\n' for actor in actor_ids]
        vehicles = sorted(vehicles)

        goals = [f'goal{i}(T{i})' for i in range(1, n)]

        n_boundaries = n - 1
        phase_invariants = [inv for inv in G.invariants if inv.scope is not None]
        acceptance, window_rules, step_rules, base_rules = [], [], [], []
        choice = False

        if self.goal_encoding == "tuple":
            if phase_invariants:
                listed = "\n  ".join(str(inv) for inv in phase_invariants)
                raise NotImplementedError(
                    "keep constraints scoped to a phase need the boundary goal encoding. The tuple "
                    "encoding has no fixed phase boundaries to attach them to:\n  " + listed +
                    "\nUse Planner(..., goal_encoding='boundary') or set "
                    "planning.Planner.GOAL_ENCODING. Scenario-scoped keeps work with either."
                )
            # The padding was added so the animations play out a little longer.
            padding = f", t > {times[-1]} + 1" if self.pad_after_goals else ""
            acceptance = [
                f"goal({','.join(times)},t) :-  {','.join(goals)}, 0 <= {'<='.join(times)} <= t{padding}.\n",
                f":- query(t), not goal({','.join(['_'] * (n - 1))},t).\n",
            ]
            if not self.pad_after_goals:
                # Without padding the plan ends at the first step at which the goals can all be
                # complete, so a trace that could already have ended one step earlier is rejected.
                acceptance.append(f":- query(t), goal({','.join(['_'] * (n - 1))},t-1).\n")

        elif not phase_invariants:
            # Same condition as the tuple rule, one boundary at a time. reached(I,t) holds once
            # goals 1..I have been met in order by step t, several at the same step allowed. That
            # is exactly "some T1 <= ... <= TI <= t exists", and it needs no choice.
            last = f"t-2" if self.pad_after_goals else "t"
            acceptance.append("reached(1,t) :- goal1(t).\n")
            for i in range(2, n_boundaries + 1):
                acceptance.append(f"reached({i},t) :- reached({i - 1},t), goal{i}(t).\n")
            acceptance.append(f":- query(t), not reached({n_boundaries},{last}).\n")
            if not self.pad_after_goals:
                # end exactly when the goals are first complete, not at some later step
                acceptance.append(f":- query(t), reached({n_boundaries},t-1).\n")
            step_rules.append("reached(I,t) :- reached(I,t-1).\n")

        else:
            raise NotImplementedError(
                "keep constraints scoped to a phase are not encoded yet: "
                + ", ".join(str(inv) for inv in phase_invariants)
            )

        self._acceptance = {"boundaries": n_boundaries, "choice": choice}

        # keep constraints. Unlike the goal rules these are not tied to one transition: each is
        # an integrity constraint in check(t), so it is instantiated per step and forbids any
        # state that breaks the invariant.
        invariant_rules = []
        for invariant in sorted(G.invariants, key=str):
            for rule in invariant.asp_integrity_rules():
                invariant_rules.append(f"% {invariant}\n{rule}\n")

        with open(instance_file_target, 'w') as f:
            f.write('% INITIAL SETUP FACTS:\n')  # just in-file documentation
            f.write('\n#program base.\n\n')  # all the initials are in base
            f.writelines(init_rules)  # the initials
            f.writelines(['\n'] + vehicles + ['\n'])

            f.write('\n#program check(t).\n\n')  # all the initials are in base

            f.write('% GOAL RULES:\n')
            f.write('time(t).\n\n') # toggle additional time pred?
            f.writelines(goals_rules)

            f.write('\n\n % GOAL ASSERTION:\n')
            f.writelines(acceptance)
            f.writelines(window_rules)

            if invariant_rules:
                f.write('\n% INVARIANTS (keep):\n')
                f.writelines(invariant_rules)

            if step_rules:
                f.write('\n#program step(t).\n\n')
                f.writelines(step_rules)

            if base_rules:
                f.write('\n#program base.\n\n')
                f.writelines(base_rules)

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
