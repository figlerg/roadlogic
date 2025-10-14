import json
from syma.automaton.automaton import Location, SymbolicAutomaton
from syma.constraint.constraint import Constraint, BoolConstraint
from syma.constraint.node.node import *

if __name__ == "__main__":
    aut = SymbolicAutomaton()
    aut.add_var('a', [-10, 10])

    # locations
    loc_1 = Location(1, initial=True, final=True)
    loc_2 = Location(2, final=True)
    loc_3 = Location(3, final=True)

    aut.add_location(loc_1)
    aut.add_location(loc_2)
    aut.add_location(loc_3)

    # Constraints
    var_node_1 = VariableNode('a')
    var_node_2 = VariableNode('b')
    var_node_3 = VariableNode('c')
    and_node = AndNode(var_node_1, NotNode(var_node_2))
    or_node = OrNode(var_node_3, and_node)


    # a < 5
    constraint_1 = BoolConstraint(formula=or_node)
    print("Volume({}) = {}".format(constraint_1.formula, constraint_1.get_volume()))
    # a >= 5
    constraint_2 = BoolConstraint(formula=and_node)
    print("Volume({}) = {}".format(constraint_2.formula, constraint_2.get_volume()))
    # a >= 0 and a < 5
    constraint_3 = BoolConstraint(formula=var_node_1)
    print("Volume({}) = {}".format(constraint_3.formula, constraint_3.get_volume()))

    # 1 -- a<5 --> 1
    aut.add_transition(loc_1, loc_1, constraint_1)
    # 1 -- a>=5 --> 2
    aut.add_transition(loc_1, loc_2, constraint_2)
    # 2 -- a>=5 --> 2
    aut.add_transition(loc_2, loc_2, constraint_2)
    # 2 -- 0<=a<5 --> 3
    aut.add_transition(loc_2, loc_3, constraint_3)
    # 3 -- 0<=a<5 --> 1
    aut.add_transition(loc_3, loc_1, constraint_3)
    # 3 -- a>=5 --> 2
    aut.add_transition(loc_3, loc_2, constraint_2)

    json_data = aut.to_json()
    with open("data/data_file.json", "w") as write_file:
        write_file.write(json_data)
