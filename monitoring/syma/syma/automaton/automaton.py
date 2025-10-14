import json
import networkx as nx
from syma.alphabet.aphabet import Alphabet


class Location(object):
    def __init__(self, id, initial=False, final=False):
        self.id = id
        self.initial = initial
        self.final = final

    @property
    def id(self):
        return self.__id

    @id.setter
    def id(self, id):
        self.__id = id

    @property
    def initial(self):
        return self.__initial

    @initial.setter
    def initial(self, initial):
        self.__initial = initial

    @property
    def final(self):
        return self.__final

    @final.setter
    def final(self, final):
        self.__final = final

    def __str__(self):
        return "[id=" + str(self.id) + ", initial=" + str(self.initial) + ", final=" + str(self.final) + "]"
    
    def __repr__(self) -> str:
        return str(self.id)


class Transition(object):

    def __init__(self, id, source, target, constraint, weight=1):
        self.id = id
        self.source = source
        self.target = target
        self.constraint = constraint
        self.weight = weight

    @property
    def id(self):
        return self.__id

    @id.setter
    def id(self, id):
        self.__id = id

    @property
    def source(self):
        return self.__source

    @source.setter
    def source(self, source):
        self.__source = source

    @property
    def target(self):
        return self.__target

    @target.setter
    def target(self, target):
        self.__target = target

    @property
    def constraint(self):
        return self.__constraint

    @constraint.setter
    def constraint(self, constraint):
        self.__constraint = constraint

    @property
    def weight(self):
        return self.__weight

    @weight.setter
    def weight(self, weight):
        self.__weight = weight


class SymbolicAutomaton(object):
    '''
    Class definind a Symbolic Automaton
    --------------------------------------------
    Symbolic automaton SA is a tuple (A, Q, q_0, F, T), where
    A - is the alphabet (an effective Boolean algebra)
    Q - is a finite set of locations
    q_0 - is the initial location
    F - is the set of final locations
    T - is a finite set of transitions of the form (q, psi, q'), where psi is a Boolean constraint defined in A

    An effective Boolean algebra (alphabet) A is the tuple A = (X, D, Pred, or, and, not)
    X - is a set of variables
    D - is the domain of the variables in X
    Pred - is a set of atomic predicates over variables in X
    or - is the disjunction operation
    and - is the conjunction operation
    not - is the negation operation
    '''

    def __init__(self):
        self.automaton = nx.MultiDiGraph()  # automaton structure
        self.locations = set()  # finite set of locations
        self.init_locations = set()  # initial location
        self.final_locations = set()  # set of final locations
        self.transitions = set()  # finite set of transitions
        self.alphabet = Alphabet()  # alphabet (effective Boolean algebra)
        self.outgoing = dict()
        self.incoming = dict()

    def add_location(self, location):
        self.automaton.add_node(
            location, init=location.initial, final=location.final)
        self.outgoing[location] = []
        self.incoming[location] = []

        self.locations.add(location)

        if location.initial:
            self.init_locations.add(location)
        if location.final:
            self.final_locations.add(location)

    def add_transition(self, source, target, constraint):
        id = self.automaton.add_edge(source, target, constraint=constraint)
        outgoing = self.outgoing[source]
        outgoing.append([id, source, target, constraint])
        self.outgoing[source] = outgoing
        incoming = self.incoming[target]
        incoming.append([id, source, target, constraint])
        self.incoming[target] = incoming

    def add_var(self, name, domain):
        self.alphabet.add_var(name, domain)

    def to_json(self):
        json_dict = dict()

        for init_loc in self.init_locations:
            json_dict['init'] = init_loc.id-1

        loc_list = []

        for loc in self.locations:
            loc_dict = dict()
            loc_dict['id'] = loc.id-1
            loc_dict['name'] = str(loc.id)
            loc_dict['is_accepting'] = loc.final
            tran_list = []
            out_trans = self.outgoing[loc]
            for out_tran in out_trans:
                out_tran_dict = dict()
                out_tran_dict['target'] = out_tran[2].id-1
                out_tran_dict['action'] = str(out_tran[3].formula)
                out_tran_dict['weight'] = out_tran[3].get_volume()
                tran_list.append(out_tran_dict)
            loc_dict['transition'] = tran_list
            loc_list.append(loc_dict)

        json_dict['statelist'] = loc_list
        json_out = json.dumps(json_dict)
        return json_out

    @property
    def init_location(self):
        return self.__init_location

    @init_location.setter
    def init_location(self, init_location):
        self.__init_location = init_location

    @property
    def incoming(self):
        return self.__incoming

    @incoming.setter
    def incoming(self, incoming):
        self.__incoming = incoming

    @property
    def outgoing(self):
        return self.__outgoing

    @outgoing.setter
    def outgoing(self, outgoing):
        self.__outgoing = outgoing

    def __str__(self):
        out = 'Alphabet:\n'
        out += '['
        for i, var in enumerate(self.alphabet.vars):
            out += var
            if i < len(list(self.alphabet.vars)) - 1:
                out += ', '
        out += ']\n'
        out += '--------------\n'

        out += 'Nodes:\n'
        for node in list(self.automaton.nodes(data=True)):
            out += str(node[0]) + '\n'
        out += '--------------\n'

        out += 'Transitions:\n'
        for tran in list(self.automaton.edges(data=True)):
            out += '(' + str(tran[0].id) + ', ' + str(tran[1].id) + \
                ', ' + str(tran[2]['constraint'].formula) + ')\n'

        return out
