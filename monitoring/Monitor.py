from planning.intermediate_structure.TranslationGraph import TranslationGraph
from planning.parse.TranslationGraphVisitor import TranslationGraphVisitor
from planning.parse.generated.openscenario2Lexer import openscenario2Lexer
from planning.parse.generated.openscenario2Parser import openscenario2Parser
from antlr4 import FileStream, CommonTokenStream
from planning.intermediate_structure.TranslationGraph import TranslationGraph
from planning.intermediate_structure.Constraint import RelativeConstraint, AbsoluteConstraint, Modifier, Relation, BaseConstraint, Invariant, StabilityInvariant
from planning.intermediate_structure.TranslationGraph import flatten_node
from planning.intermediate_structure.TranslationGraph import TranslationGraph
from planning.misc.errors import HardSyntaxErrorStrategy
from syma.automaton.automaton import Location, SymbolicAutomaton
from syma.constraint.constraint import Constraint
from syma.constraint.node.node import *

from syma_arv.monitor.boolean import BooleanMonitor
from syma_arv.monitor.minmax import MinMaxMonitor
from syma_arv.monitor.tropical import TropicalMonitor
from syma_arv.constraint.evaluator.boolean import BooleanEvaluator

from collections import deque
from typing import Set, Union, List
from commonroad_extensions.plan_execution.id_hash import encode, decode

import csv
from collections import defaultdict, OrderedDict
import os
from planning.asp.MyModel import MyModel, MyPred

from commonroad_extensions.plan_execution.map_plan import no_lanes

from functools import lru_cache


# How close two continuous values have to be to count as equal. A simulated position is a float
# that lands a fraction of a millimetre off what the plan asked for, and a strict comparison turns
# that into a violated trace. This is the same slack aggregate_monitoring_results.py has always
# applied to the MinMax cost, moved into the comparison itself.
COMPARISON_EPSILON = 1e-3


class TolerantBooleanEvaluator(BooleanEvaluator):
    """Boolean verdicts, but a comparison of continuous values may miss by COMPARISON_EPSILON.

    Lanes are integers and are unaffected. Positions and speeds are floats coming out of a motion
    planner, so an exact comparison is meaningless for them.
    """

    def __init__(self, epsilon=COMPARISON_EPSILON):
        super().__init__()
        self.epsilon = epsilon

    def d_geq(self, val1, val2):
        return False if val1 >= val2 - self.epsilon else True

    def d_greater(self, val1, val2):
        return False if val1 > val2 - self.epsilon else True

    def d_leq(self, val1, val2):
        return False if val1 <= val2 + self.epsilon else True

    def d_less(self, val1, val2):
        return False if val1 < val2 + self.epsilon else True

    def d_eq(self, val1, val2):
        return False if abs(val1 - val2) <= self.epsilon else True

    def d_neq(self, val1, val2):
        return False if abs(val1 - val2) > self.epsilon else True


class TolerantBooleanMonitor(BooleanMonitor):
    """The default ring: a plain satisfied or violated verdict, with a float-sized tolerance."""

    def __init__(self, aut):
        BooleanMonitor.__init__(self, aut)
        self.c_evaluator = TolerantBooleanEvaluator()


# How much a quantity may drift between two steps and still count as held. A lane is an integer
# and never drifts, but a simulated speed is a float that wobbles even when the plan asks for a
# constant, so keep_speed() needs a tolerance. See docs/keep-spec.md.
STABILITY_TOLERANCE = 0.5


def variable_name(actor, modifier: Modifier, previous=False) -> str:
    """The syma variable for one quantity of one actor, matching read_valuations."""
    return f"{modifier.value}{'_prev' if previous else ''}({actor})"


def convert_invariant(inv: Invariant, tolerance=STABILITY_TOLERANCE) -> Node:
    """The guard a keep puts on a transition.

    An ordinary keep wraps a point constraint, so it converts exactly like one. A stability keep
    (keep_lane(), keep_speed(), keep(x == some_parameter)) says the quantity never changes, which
    a guard cannot see on a single step, so it compares against the previous step's value.
    """
    if isinstance(inv, StabilityInvariant):
        now = VariableNode(variable_name(inv.actor, inv.modifier))
        before = VariableNode(variable_name(inv.actor, inv.modifier, previous=True))
        if inv.modifier == Modifier.LANE:
            return EqualNode(now, before)
        # A float never repeats exactly, so allow a small drift in both directions.
        tol = ConstantNode(tolerance)
        return AndNode(LEQNode(MinusNode(now, before), tol),
                       LEQNode(MinusNode(before, now), tol))

    con = inv.constraint
    if isinstance(con, RelativeConstraint):
        return convert_relative_constraint(con)
    if isinstance(con, AbsoluteConstraint):
        return convert_absolute_constraint(con)
    raise NotImplementedError(f"Cannot monitor an invariant over {type(con).__name__}.")


def invariant_variables(inv: Invariant):
    """Every syma variable a keep's guard reads, the previous-step ones included."""
    if isinstance(inv, StabilityInvariant):
        return [variable_name(inv.actor, inv.modifier),
                variable_name(inv.actor, inv.modifier, previous=True)]
    con = inv.constraint
    if isinstance(con, RelativeConstraint):
        return [con.exp1, con.exp2]
    return [con.exp]


def covered_locations(inv: Invariant, nodes):
    """The locations whose time is inside this keep's window.

    None as the scope means the whole scenario. Otherwise the keep belongs to one invocation, and
    after parallel composition a node is a tuple of component states, so a location belongs to the
    invocation when its id carries that label.
    """
    if inv.scope is None:
        return set(nodes)
    return {node for node in nodes if inv.scope in flatten_node(node)}


def guards_for_transition(source, target, final, guards):
    """The keep guards that apply to one transition, as a list of nodes.

    A keep is checked on the step that enters its location and on every step that stays there, so
    it goes on the incoming transitions and the self loop, never on the one that leaves. The edge
    into the final location is the exception: nothing follows it, so the last segment's keep has
    to cover that step. This mirrors the ASP windows, which tile the plan as [T(k-1), Tk) with
    only the last phase closed. See section 6 of docs/keep-spec.md.
    """
    applicable = []
    for covered, node in guards:
        if target in covered or (target == final and source in covered):
            applicable.append(node)
    return applicable


def conjoin(node, extra):
    """Add every guard in `extra` to `node`, which may be None."""
    for guard in extra:
        node = guard if node is None else AndNode(node, guard)
    return node


class Monitor:
    
    """ This is a class for monitoring an OSC2 specification.
        In its most basic form it needs to have the following functionality:
        - input: a specification (.osc file), a set of simulation folders (with LANE.csv and LONGPOS.csv files indicating the positions)
        - output: a csv file (or similar) 


        Its members should be
        - the syma automaton corresponding to the spec
        - what else?

        There should then be some method for an instance mon:
        - mon.membership(lane_file, longpos_file)       -> checks a single set of files, returns true or false (or robustness)
        - mon.inclusion(experiments_folder)             -> checks all simulations in folder and creates a csv
    """

    def __init__(self, ring : Union[BooleanMonitor, MinMaxMonitor, TropicalMonitor] = TolerantBooleanMonitor) -> None:
        
        self.syma_aut = None
        self._translation_graph = None
        # self.populate_syma_aut()
        self.ring = ring
        self.monitor = None


    # I give here two useful versions of constructors: 
    #   Either create the object from an existing translation graph (from my osc2scenic tool) OR
    #   Simply use a manually defined symbolic automaton (from Dejan's syma-arv)

    @classmethod
    def from_translation_graph(cls, translation_graph:TranslationGraph, ring : Union[BooleanMonitor, MinMaxMonitor, TropicalMonitor] = TolerantBooleanMonitor):
        mon = cls(ring=ring)
        
        mon.ring = ring
        mon._translation_graph = translation_graph
        mon.populate_syma_aut()

        return mon

    @classmethod
    def from_syma_aut(cls, syma_aut:SymbolicAutomaton, ring : Union[BooleanMonitor, MinMaxMonitor, TropicalMonitor] = TolerantBooleanMonitor):
        mon = cls(ring=ring)
        mon.ring = ring
        mon.syma_aut = syma_aut

        return mon
    
    @classmethod
    @lru_cache(maxsize=None)
    def from_osc2_file(cls, osc_file, ring : Union[BooleanMonitor, MinMaxMonitor, TropicalMonitor] = TolerantBooleanMonitor):
        input_stream = FileStream(osc_file)
        lexer = openscenario2Lexer(input_stream)
        stream = CommonTokenStream(lexer)
        parser = openscenario2Parser(stream)
        parser._errHandler = HardSyntaxErrorStrategy()
        ctx = parser.osc_file()

        visitor = TranslationGraphVisitor()
        T: TranslationGraph = visitor.visit(ctx)

        return cls.from_translation_graph(T, ring=ring)
    
    @classmethod
    def invariant_from_plan(cls, plan:MyModel, ring : Union[BooleanMonitor, MinMaxMonitor, TropicalMonitor] = MinMaxMonitor, tolerance = 1, plan_config=None):
        """
        I want to have an invariant such as "has completed the planning fully" and check it automatically.
        This should catch plans which for whatever reason could not be completed by the controllers.

        This is dependent on each planning separately so I want as input a planning (MyModel) and as output a monitoring object which checks specifically if that planning was completed.

        input: MyModel
        output: Monitor
        """
        mon = cls(ring=ring)
        mon.ring = ring

        syma_aut = SymbolicAutomaton()
        
        ## 3 nodes
        init_loc = Location('init', initial=True, final=False)
        syma_aut.add_location(init_loc)  # this method expects the location object

        actor_initial_state_check_node = Location('actor_initial_state_check')
        syma_aut.add_location(actor_initial_state_check_node)

        actor_final_state_check_node = Location('actor_final_state_check', final=True)
        syma_aut.add_location(actor_final_state_check_node)

        ## 2 transitions (andnodes of all actor's positions at start and end)

        if plan:
            actors = [pred.arguments[0] for pred in plan if pred.name == 'vehicle']

            min_lane = min([h[0][1][1] for h in plan.holds])
            max_lane = max([h[0][1][1] for h in plan.holds])
            min_pos = min([h[0][1][0] for h in plan.holds]) + 10
            max_pos = max([h[0][1][0] for h in plan.holds]) - 10

            initial_holds = dict()
            final_holds = dict()

            for pred in plan.holds:
                # holds(state(actor, loc(x,y), dyn()), time) I think
                pred_actor = str(pred[0][0]) 
                lon,lat = pred[0][1]
                t = pred[-1]

                if t == 0:
                    initial_holds[pred_actor] = (lon,lat)
                if t == plan.max_t:
                    final_holds[pred_actor] =  (lon,lat)

                leftmost_lane = min([pred.arguments[0] for pred in plan if pred.name == 'lane'])
        
        # just a silly way of sideloading manually the values. needed because I was using some old files as test cases which were in wrong format
        else:
            actors = plan_config['actors']
            min_lane = plan_config['min_lane']
            max_lane = plan_config['max_lane']
            min_pos  = plan_config['min_pos']
            max_pos  = plan_config['max_pos']
            initial_holds = plan_config['initial_holds']
            final_holds = plan_config['final_holds']
            leftmost_lane = plan_config['leftmost_lane']




        total_con_init = None
        total_con_final = None


        # initial constraints: be close to initial state
        # final constraints: be close to the last target
        for actor in actors:

            # first I create syma nodes for the variables and target constants
            pos_var = f'p({actor})'
            lane_var = f'l({actor})'
            pos_target_init, lane_target_init  =  initial_holds[str(actor)]
            pos_target_final, lane_target_final  =  final_holds[str(actor)]


            # here I am doing translation of leftmost lane to 0, so the monitoring has the same reference as the instrumentation
            lane_target_init -= leftmost_lane  
            lane_target_final -= leftmost_lane 

            lane_var_node = VariableNode(lane_var)
            pos_var_node = VariableNode(pos_var)
            lane_target_init_node = ConstantNode(lane_target_init)
            pos_target_init_node = ConstantNode(pos_target_init)
            lane_target_final_node = ConstantNode(lane_target_final)
            pos_target_final_node = ConstantNode(pos_target_final)

            tol_node = ConstantNode(tolerance)
            
            # add the variables to the aut object. give some big enough ranges (heuristic)
            syma_aut.add_var(lane_var, domain=(min_lane, max_lane))  
            syma_aut.add_var(pos_var, domain=(min_pos, max_pos))  


            # check lane exactly and pos with tolerance for the initial state
            lower_init = LessNode(MinusNode(pos_var_node, tol_node), pos_target_init_node)
            upper_init = LessNode(pos_target_init_node, AddNode(VariableNode(pos_var),tol_node))
            pos_check_init = AndNode(lower_init, upper_init)
            lane_check_init = EqualNode(lane_var_node, lane_target_init_node)

            # every actor adds a new set of constraints to start/end transition
            new_con_init = AndNode(pos_check_init, lane_check_init) # this is the whole check for the initial goal

            if total_con_init:
                total_con_init = AndNode(total_con_init,new_con_init)
            else:
                total_con_init = new_con_init


            # check lane exactly and pos with tolerance for the final goal
            lower_final = LessNode(MinusNode(pos_var_node, tol_node), pos_target_final_node)
            upper_final = LessNode(pos_target_final_node, AddNode(VariableNode(pos_var),tol_node))
            pos_check_final = AndNode(lower_final, upper_final)
            lane_check_final = EqualNode(lane_var_node, lane_target_final_node)

            # every actor adds a new set of constraints to start/end transition
            new_con_final = AndNode(pos_check_final, lane_check_final) # this is the whole check for the final goal

            if total_con_final:
                total_con_final = AndNode(total_con_final,new_con_final)
            else:
                total_con_final = new_con_final

            # print(f"planning initial position {actor} = {pos_target_init}")
            # print(f"planning final position {actor} = {pos_target_final}")
            # print(f"planning initial lane {actor} = {lane_target_init}")
            # print(f"planning final lane {actor} = {lane_target_final}")


            # print(f"total con init = {total_con_init}")
            # print(f"total con final = {total_con_final}")


        syma_aut.add_transition(init_loc,actor_initial_state_check_node,Constraint(formula=total_con_init))
        syma_aut.add_transition(actor_initial_state_check_node,actor_final_state_check_node,Constraint(formula=total_con_final))

        add_self_loops(syma_aut)

        mon.syma_aut = syma_aut

        return mon


    def initialize(self):
        mon = self.ring(self.syma_aut)
        mon.initialize()
        self.monitor = mon


    def eval(self, trace:List[dict], verbose = False):
        if verbose:
            print(self.state)

        for state in trace:
            self.update(state)
            print(self.state)

    def update(self, state:dict):
            self.monitor.update(state)


    @property
    def state(self):
        return self.monitor.state


    def populate_syma_aut(self):
        
        
        T = self._translation_graph
        # NOTE: these graphs always have exactly one initial node and one final node. 

        q = deque()
        syma_aut = SymbolicAutomaton()
        
        # I need to remember the id:object pairs
        location_by_id = dict()

        # simple BFS to translate the osc2scenic structure into the syma structure


        # Keeps become guards on the transitions rather than locations of their own.
        guards = []
        for inv in sorted(T.invariants, key=str):
            for name in invariant_variables(inv):
                syma_aut.add_var(name, domain=(-100, 100))  # TODO these limits are hardcoded
            guards.append((covered_locations(inv, T.graph.nodes), convert_invariant(inv)))

        i = T.initial
        q.append(i)
        location_by_id[i] = Location(i, initial=True, final=False)
        syma_aut.add_location(location_by_id[i])  # this method expects the location object


        while q:
            v = q.popleft()

            adj = [w for _,w in T.out_edges(v)]
            q += adj

            # The graph is always a tree with our grammar, so we could simplify this a bit more (BFS will never touch any node twice)
            for w in adj:

                if w not in location_by_id.keys():
                    loc_w = Location(id=w, initial=False, final=(w == T.final))
                    location_by_id[w] = loc_w
                

                syma_aut.add_location(location_by_id[w])

                ## Some examples from syma-arv main
                # var_node = VariableNode('a')
                # zero_node = ConstantNode(0)
                # less_5_node = LessNode(var_node, five_node)
                # geq_5_node = GEQNode(var_node, five_node)
                # in_0_5_node = AndNode(geq_0_node, less_5_node)
                # # a < 5
                # constraint_1 = Constraint(formula=less_5_node)
                # # a >= 5
                # constraint_2 = Constraint(formula=geq_5_node)
                # # a >= 0 and a < 5
                # constraint_3 = Constraint(formula=in_0_5_node)

                # # 2 -- 0<=a<5 --> 3
                # aut.add_transition(loc_2, loc_3, constraint_3)

                cons_osc:Set[BaseConstraint] = T[v,w]

                cons_syma_node = None

                # add cons one by one via the and operation
                for con in cons_osc:

                    # potentially we introduce new variables
                    con:Union[RelativeConstraint, AbsoluteConstraint]

                    if isinstance(con, RelativeConstraint):
                        v1 = con.exp1
                        v2 = con.exp2

                        syma_aut.add_var(v1, domain=(-100, 100))  # TODO these limits are hardcoded
                        syma_aut.add_var(v2, domain=(-100, 100))  # TODO these limits are hardcoded

                        new_con = convert_relative_constraint(con)
                    
                    elif isinstance(con, AbsoluteConstraint):
                        v1 = con.exp
                        syma_aut.add_var(v1, domain=(-100, 100))  # TODO these limits are hardcoded

                        new_con = convert_absolute_constraint(con)
                        

                    # first node
                    if not cons_syma_node:
                        cons_syma_node = new_con
                    else:
                        cons_syma_node = AndNode(cons_syma_node, new_con)

                if cons_syma_node is None and not guards_for_transition(v, w, T.final, guards):
                    cons_syma_node = TrueNode()

                cons_syma_node = conjoin(cons_syma_node,
                                         guards_for_transition(v, w, T.final, guards))

                cons_syma = Constraint(formula=cons_syma_node)  # TODO not sure if the alphabet param is ecpected

                
                syma_aut.add_transition(location_by_id[v],location_by_id[w], constraint=cons_syma)

        add_self_loops(syma_aut, guards=guards, final=T.final)

        self.syma_aut = syma_aut
            


    # GPT
    def read_valuations(self,
                        lane_path: str,
                        long_path: str,
                        vel_path: str = None) -> list[dict[str, Union[int, float]]]:
        """
        Build valuations [{l(ego):…, l(car1):…, p(ego):…, p(car1):…}, …]
        from two CommonRoad-style CSV logs.

        Parameters
        ----------
        lane_path : str
            Path to LANE.csv (must have columns: time, agent_id, lane).
        long_path : str
            Path to LONGPOS.csv (must have columns: time, agent_id, longitudinal_position).

        Returns
        -------
        list[dict[str, int|float]]
            One valuation per time-step, ordered by the time column.
        """

        def _read(file_path: str, value_col: str) -> dict[float, dict[str, Union[int, float]]]:
            out = defaultdict(dict)
            with open(file_path, newline="") as fh:
                for row in csv.DictReader(fh):
                    t = float(row["time"])
                    aid = int(row["agent_id"])
                    val = float(row[value_col]) if "." in row[value_col] else int(row[value_col])
                    out[t][aid] = val
            return out

        lane_data = _read(lane_path, "lane")
        pos_data = _read(long_path, "longitudinal_position")
        # Speed is only logged when CURRV was among the computed metrics. Older result folders
        # have no such file, and a spec without a speed constraint never asks for the variable.
        vel_data = _read(vel_path, "velocity") if vel_path and os.path.isfile(vel_path) else {}

        times = sorted(set(lane_data) | set(pos_data))
        valuations = []

        for t in times:
            val = OrderedDict()
            all_ids = set(lane_data.get(t, {})) | set(pos_data.get(t, {}))
            for hash_id in all_ids:
                name = decode(hash_id)
                if hash_id in lane_data.get(t, {}):
                    val[f"l({name})"] = lane_data[t][hash_id]
                if hash_id in pos_data.get(t, {}):
                    val[f"p({name})"] = pos_data[t][hash_id]
                if hash_id in vel_data.get(t, {}):
                    val[f"v({name})"] = vel_data[t][hash_id]
            valuations.append(val)

        return with_previous(valuations)

    def eval_trace(self, gen_folder, verbose = False, log_name_override = None):
        lane_path = os.path.join(gen_folder,'LANE.csv')
        long_path = os.path.join(gen_folder,'LONGPOS.csv')
        vel_path = os.path.join(gen_folder,'CURRV.csv')

        valuations = self.read_valuations(lane_path=lane_path, long_path=long_path,
                                          vel_path=vel_path)

        last_full_index = valuations_sanity_check(valuations)

        if last_full_index:
            valuations = valuations[:last_full_index] # cut all the values where one actor vanished

        assert len(set(len(v) for v in valuations))==1, f"{valuations}"

        self.log_monitoring_results(gen_folder, valuations, verbose=verbose, log_name_override=log_name_override)

        return self.state
    
    def log_monitoring_results(self, gen_folder: str, trace: list[dict], log_name_override = None, verbose=False):
        """
        Evaluates the trace and writes the resulting state dict at each time step
        into a CSV file located in `gen_folder/eval_trace.csv`.

        Parameters
        ----------
        gen_folder : str
            Folder containing the simulation results (LANE.csv, LONGPOS.csv).
        trace : list[dict]
            The sequence of valuations to evaluate and log.
        """
        if not log_name_override:
            log_path = os.path.join(gen_folder, "monitoring_results.csv")
            log_path_metadata = os.path.join(gen_folder, "monitoring_metadata.log")

        # for some monitors I want to specify the name from outside. it should be just the filename
        else:
            log_path = os.path.join(gen_folder, log_name_override + '.csv')
            log_path_metadata = os.path.join(gen_folder, log_name_override + '_metadata.log')


        self.initialize()

        incomplete = False
        states_for_writer = []

        if verbose:
            print(self.state)

        for state in trace:
            try:
                self.update(state)

                if verbose:
                    print(self.state)

                flat_state = {self._flattened_str(k): self._flattened_value(v)
                              for k, v in self.state.items()}
                states_for_writer.append(flat_state)


            except KeyError:
                incomplete = True
                break


        if not incomplete:

            with open(log_path, mode="w", newline="") as f:
                writer = None


                if writer is None:
                    writer = csv.DictWriter(f, fieldnames=flat_state.keys())
                    writer.writeheader()

                for flat_state in states_for_writer:
                    writer.writerow(flat_state)

            with open(log_path_metadata, mode='w') as f:
                f.write(str(self.syma_aut))


    @staticmethod
    def _flattened_value(value):
        """Verdicts as numbers, so every ring writes the same kind of CSV.

        The boolean ring gives True or False, where False means satisfied, because the algebra
        orders False below True. aggregate_monitoring_results.py reads the last column as a float
        and counts a run as a positive trace when it is 0, so False has to reach it as 0.
        """
        if isinstance(value, bool):
            return int(value)
        return value

    def _flattened_str(self, key):
        """
        Convert dictionary key to a flat string for CSV output.
        E.g., ('c0.drive', 'A.drive') -> '(c0.drive;A.drive)'
        """
        if isinstance(key, tuple):
            return f"({';'.join(key)})"
        return str(key)


def with_previous(valuations):
    """Add the previous step's value of every variable, as `l_prev(car1)` and friends.

    A guard only sees one step, so a keep that says a quantity never changes needs the step
    before it to compare against. At the first step there is no previous one, so the current
    value is used and nothing can be violated there.
    """
    out = []
    previous = None
    for val in valuations:
        row = OrderedDict(val)
        source = previous if previous is not None else val
        for name, value in val.items():
            quantity, _, actor = name.partition("(")
            row[f"{quantity}_prev({actor}"] = source.get(name, value)
        out.append(row)
        previous = val
    return out


def convert_relative_constraint(con:RelativeConstraint) -> Node:
    """
    Transforms a single constraint in the osc2scenic format to a constraint Node object in the syma-arv format.

    Note that the former is composed as:
        p(actor2) R p(actor1) + c
    or 
        l(actor2) R l(actor1) + c
    where p,l mean longitudinal position, lane respectively.
    """

    # introduce the metrics of interest as new variables in syma
    v1 = con.exp1
    v2 = con.exp2
    v1_node = VariableNode(v1)
    v2_node = VariableNode(v2)

    # c is a number and will be a ConstantNode. For simplicity I skip if c is 0
    c = con.c 
    
    rhs = v2_node
    if c:
        c_node = ConstantNode(c)

        rhs = AddNode(v2_node, c_node)
    
    lhs = v1_node
    
    match con.relation.value:

        case '==':
            out = EqualNode(lhs,rhs)
            
        case '<=':
            out = LEQNode(lhs,rhs)

        case '>=':
            out = GEQNode(lhs,rhs)

        case '<':
            out = LessNode(lhs,rhs)

        case '>':
            out = GreaterNode(lhs,rhs)

        case '!=':
            out = NotNode(EqualNode(lhs,rhs))

    return out

def convert_absolute_constraint(con: AbsoluteConstraint) -> Node:
    """
    Transforms a single absolute constraint into a constraint Node object
    in the syma-arv format.

    Absolute constraints have the form:
        p(actor) R c
        l(actor) R c
    where p, l mean longitudinal position and lane, respectively.
    """

    # same variable name as used in syma_aut.add_var(...)
    v1 = con.exp          # "p(ego)" or "l(ego)"
    v2 = con.value        # numeric constant

    v1_node = VariableNode(v1)
    v2_node = ConstantNode(v2)

    lhs = v1_node
    rhs = v2_node

    match con.relation.value:
        case '==':
            out = EqualNode(lhs, rhs)
        case '<=':
            out = LEQNode(lhs, rhs)
        case '>=':
            out = GEQNode(lhs, rhs)
        case '<':
            out = LessNode(lhs, rhs)
        case '>':
            out = GreaterNode(lhs, rhs)
        case '!=':
            out = NotNode(EqualNode(lhs, rhs))
        case _:
            raise NotImplementedError(
                f"Unexpected relation in AbsoluteConstraint: {con.relation}"
            )

    return out



def convert_holds(pos_var, lane_var, pos_target, lane_target, tolerance) -> Node:
    # check lane exactly and pos with tolerance
    lower = LessNode(VariableNode(pos_var)-tolerance, ConstantNode(pos_target))
    upper = LessNode(ConstantNode(pos_target), VariableNode(pos_var)+tolerance)

    pos_check = AndNode(lower, upper)

    lane_check = EqualNode(VariableNode(lane_var), ConstantNode(lane_target))

    return AndNode(pos_check, lane_check)


class IncompleteTraceError(Exception):
    pass

def valuations_sanity_check(valuations:List[OrderedDict]):
    variables = set(valuations[0].keys())

    incomplete = False
    for i, val in enumerate(valuations):
        next_vars = set(val.keys())
        if next_vars!=variables:
            incomplete = True
            last_full_idx = i
            break
            # diff_vars = variables.difference(next_vars)
            # raise IncompleteTraceError(f"Sanity check for valuations failed. The set of variables changed. Missing variables: {variables.difference(next_vars)}")

    # last_values = [(a,b) for (a,b) in variables[i-1] if a in diff_vars]

    if incomplete:
        return last_full_idx
    return 0

def add_self_loops(syma_aut:SymbolicAutomaton, guards=None, final=None):
        # simply adds self loops with True constraint to all nodes, according to our semantics. Works in place
        # A location covered by a keep gets that keep on its self loop instead of a plain True, so
        # staying there means the invariant still holds.
        #
        # The initial location gets no self loop: the scenario starts with the trace, matching the
        # planner, which pins the initial constraints at t=0. Waiting there would also let a keep
        # on the first phase be dodged by entering that phase after the violating step.

        # in each state we can stay for as long as we like
        for loc in syma_aut.locations:
            if loc.initial:
                continue
            applicable = guards_for_transition(loc.id, loc.id, final, guards or [])
            node = conjoin(None, applicable)
            if node is None:
                node = TrueNode()
            # true_node = EqualNode(ConstantNode(1),ConstantNode(1))  # TODO this is necessary in order to give float distances. Truenode just says true for some of those. think about what is the right way to do it
            con = Constraint(formula=node)
            syma_aut.add_transition(loc, loc, con)

        

if __name__ == "__main__":

    # from monitoring.overtake_monitor import manual_monitor as mon  # this is a fixed aut made by hand
    from monitoring.overtake_monitor import gen_monitor as mon

    
    # mon_result = mon.eval_trace('experiments/scenario_0001')


    # print(mon_result)
    

    import pickle

    # with open(r"C:\Users\giglerf\PycharmProjects\osc2scenic\generated\serialized_models\model0001.pkl",'w') as f:
        # a = pickle.load(f)

    with open("/home/figlerg/dev/cr-dynamic-traffic-generation/results/rq1/BASIC/serialized_models/model0001.pkl", "rb") as f:
        plan = pickle.load(f)

    # mon_result_1 = mon.eval_trace(gen_folder="/home/figlerg/dev/cr-dynamic-traffic-generation/results/rq1/BASIC/cr_simulations/scenario_0001", verbose=True)
    # print(mon_result_1)
    
    mon_inv:Monitor = Monitor.invariant_from_plan(plan,tolerance=1)
    mon_result_2 = mon_inv.eval_trace(gen_folder="/home/figlerg/dev/cr-dynamic-traffic-generation/results/rq1/BASIC/cr_simulations/scenario_0001")

    print(mon_result_2)

    ### TEST FOR POSITIVE SAMPLE... it is a bit silly because I was saving the models as tuples earlier, so there is no way to get the MyModel from it
    # this is scenario 1
    plan_config1 = dict()
    plan_config1['actors'] = ['ego', 'car1']
    plan_config1['min_lane'] = [-100,100]
    plan_config1['max_lane'] = [-100, 100]
    plan_config1['min_pos'] = [-100, 100]
    plan_config1['max_pos'] = [-100, 100]
    plan_config1['initial_holds'] = {'ego': (0,0), 'car1': (10,0)}
    plan_config1['final_holds'] = {'ego': (47,-1), 'car1': (27,-1)}
    plan_config1['leftmost_lane'] = -1
    
    # this is scenario 2
    plan_config2 = dict()
    plan_config2['actors'] = ['ego', 'car1']
    plan_config2['min_lane'] = [-100,100]
    plan_config2['max_lane'] = [-100, 100]
    plan_config2['min_pos'] = [-100, 100]
    plan_config2['max_pos'] = [-100, 100]
    plan_config2['initial_holds'] = {'ego': (0,0), 'car1': (16,0)}
    plan_config2['final_holds'] = {'ego': (42,-1), 'car1': (32,-1)}
    plan_config2['leftmost_lane'] = -1


    mon_inv3:Monitor = Monitor.invariant_from_plan(plan=None,tolerance=1, plan_config=plan_config1)
    mon_result_3 = mon_inv.eval_trace(gen_folder="/home/figlerg/dev/cr-dynamic-traffic-generation/temp-debug/scenario_0001")
    print(mon_result_3)

    mon_inv4:Monitor = Monitor.invariant_from_plan(plan=None,tolerance=1, plan_config=plan_config2)
    mon_result_4 = mon_inv.eval_trace(gen_folder="/home/figlerg/dev/cr-dynamic-traffic-generation/temp-debug/scenario_0005")
    print(mon_result_4)
