import json
import os
from syma.automaton.automaton import Location, SymbolicAutomaton
from syma.constraint.constraint import Constraint, RealConstraint
from syma.constraint.node.node import *

if __name__ == "__main__":
    aut = SymbolicAutomaton()
    aut.add_var('x', [0, 10])
    aut.add_var('y', [0, 10])

    # locations
    loc_1 = Location(1, initial=True, final=True)
    loc_2 = Location(2, final=True)
    loc_3 = Location(3, final=True)

    aut.add_location(loc_1)
    aut.add_location(loc_2)
    aut.add_location(loc_3)

    # Constraints
    var_node_x = VariableNode('x')
    var_node_y = VariableNode('y')

    norm = AddNode(PowNode(var_node_x, ConstantNode(2)),
                   PowNode(var_node_x, ConstantNode(2)))

    diff = MinusNode(var_node_x, var_node_y)
    # 1 -- 0.1 <= x^2+y^2 <= 0.5 --> 2
    aut.add_transition(loc_1, loc_2, RealConstraint(formula=AndNode(
        LEQNode(ConstantNode(0.1), norm),
        LEQNode(norm, ConstantNode(0.5),))
    ))
    # 1 -- 0.7 <= x^2+y^2 <= 0.5 --> 1
    aut.add_transition(loc_1, loc_3, RealConstraint(formula=AndNode(
        LEQNode(ConstantNode(0.7), norm),
        LEQNode(norm, ConstantNode(1),))
    ))    # 2 -- x-y>=2 --> 1
    aut.add_transition(loc_2, loc_1, RealConstraint(formula=GEQNode(
        diff, ConstantNode(2))))
    # 2 -- x-y<2 --> 2
    aut.add_transition(loc_2, loc_2, RealConstraint(
        formula=LessNode(diff, ConstantNode(2.0))))
    # 3 -- x<2 y<5 --> 1
    aut.add_transition(loc_3, loc_1, RealConstraint(formula=AndNode(
        LessNode(var_node_x, ConstantNode(2)), LessNode(var_node_y, ConstantNode(5)))))
    # 3 -- 3 ≤ x ≤ 5 y > 7 --> 3
    aut.add_transition(loc_3, loc_3, RealConstraint(formula=AndNode(
        LessNode(ConstantNode(3), var_node_x), AndNode(
            LessNode(var_node_x, ConstantNode(5)),
            LessNode(ConstantNode(7), var_node_y)))))

    json_data = aut.to_json()
    with open("data/data_file.json", "w") as write_file:
        write_file.write(json_data)

    #for some reason the json file is ill formed and must be uniformized
    os.system("jq < data/data_file.json > data/data_file2.json") 

    os.system("~/Documents/wordgen/wordgen data/data_file2.json --traj 10 --expected-size 10 --output-format json data/out_trajectory.json")

    with open("data/out_trajectory.json", "r") as traj_file:
        trajs = json.load(traj_file)
        print(trajs)