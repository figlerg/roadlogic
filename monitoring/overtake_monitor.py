

from collections import deque
from typing import Set, Union, List
from antlr4 import FileStream, CommonTokenStream
import os

from syma.automaton.automaton import Location, SymbolicAutomaton
from syma.constraint.constraint import Constraint
from syma.constraint.node.node import *
from syma_arv.monitor.boolean import BooleanMonitor
from syma_arv.monitor.minmax import MinMaxMonitor
from syma_arv.monitor.tropical import TropicalMonitor

from planning.intermediate_structure.TranslationGraph import TranslationGraph
from planning.intermediate_structure.Constraint import RelativeConstraint as MyConstraint # Dejan and I used the same name for our classes so I renamed mine in here
from planning.intermediate_structure.TranslationGraph import TranslationGraph
from planning.misc.errors import HardSyntaxErrorStrategy
from planning.parse.TranslationGraphVisitor import TranslationGraphVisitor
from planning.parse.TranslationGraphVisitor import TranslationGraphVisitor
from planning.parse.generated.openscenario2Lexer import openscenario2Lexer
from planning.parse.generated.openscenario2Parser import openscenario2Parser

from monitoring.Monitor import Monitor  # my class




manual_aut = SymbolicAutomaton()
manual_aut.add_var('p(ego)', [-100, 100])
manual_aut.add_var('p(car1)', [-100, 100])
manual_aut.add_var('l(ego)', [-100, 100])
manual_aut.add_var('l(car1)', [-100, 100])

# (init) -> (1) -> (2) -> (3) -> (fin)

# locations
loc_init = Location('init', initial=True)
loc_1 = Location(1)
loc_2 = Location(2)
loc_3 = Location(3)
loc_fin = Location('fin', final=True)

manual_aut.add_location(loc_init)
manual_aut.add_location(loc_1)
manual_aut.add_location(loc_2)
manual_aut.add_location(loc_3)
manual_aut.add_location(loc_fin)

var_l_ego = VariableNode('l(ego)')
var_l_car1 = VariableNode('l(car1)')
var_p_ego = VariableNode('p(ego)')
var_p_car1 = VariableNode('p(car1)')

# init to 1
eq_node = EqualNode(var_l_ego,var_l_car1)
rel_pos_node_1 = LEQNode(AddNode(var_p_car1, ConstantNode(-20)), var_p_ego)
rel_pos_node_2 = GEQNode(AddNode(var_p_car1, ConstantNode(-10)), var_p_ego)
rel_pos_node_1_2 = AndNode(rel_pos_node_1, rel_pos_node_2)
con_1_node = AndNode(rel_pos_node_1_2, eq_node)
constraint_init_1 = Constraint(formula=con_1_node)


# 1 to 2
lesser_node = LessNode(var_l_ego,var_l_car1)
constraint_less = Constraint(formula=lesser_node)

# 2 to 3
rel_pos_node_3 = LEQNode(AddNode(var_p_car1, ConstantNode(1)), var_p_ego)
rel_pos_node_4 = GEQNode(AddNode(var_p_car1, ConstantNode(10)), var_p_ego)
rel_pos_node_3_4 = AndNode(rel_pos_node_3, rel_pos_node_4)
constraint_2_3 = Constraint(formula=rel_pos_node_3_4)

# 3 to fin
rel_pos_node_5 = LEQNode(AddNode(var_p_car1, ConstantNode(5)), var_p_ego)
rel_pos_node_6 = GEQNode(AddNode(var_p_car1, ConstantNode(10)), var_p_ego)
rel_pos_node_5_6 = AndNode(rel_pos_node_5, rel_pos_node_6)
total_node_3_fin = AndNode(rel_pos_node_5_6,eq_node)
constraint_3_fin = Constraint(formula=total_node_3_fin)


manual_aut.add_transition(loc_init, loc_1, constraint=constraint_init_1)
manual_aut.add_transition(loc_1, loc_2, constraint=constraint_less)
manual_aut.add_transition(loc_2, loc_3, constraint=constraint_2_3)
manual_aut.add_transition(loc_3, loc_fin, constraint=constraint_3_fin)

mon = MinMaxMonitor(aut=manual_aut) # Dejan's class
manual_monitor = Monitor.from_syma_aut(manual_aut,ring=MinMaxMonitor)

# ## TEST INSTANCE
# manual_monitor.initialize()
# print(manual_monitor.state)
# manual_monitor.update({'l(ego)':2, 'l(car1)':2, 'p(ego)':1, 'p(car1)':15})
# print(manual_monitor.state)
# manual_monitor.update({'l(ego)':1, 'l(car1)':2, 'p(ego)':1, 'p(car1)':15})
# print(manual_monitor.state)
# manual_monitor.update({'l(ego)':1, 'l(car1)':2, 'p(ego)':17, 'p(car1)':15})
# print(manual_monitor.state)
# manual_monitor.update({'l(ego)':2, 'l(car1)':2, 'p(ego)':21, 'p(car1)':15})
# # manual_monitor.update({'l(ego)':2, 'l(car1)':2, 'p(ego)':17, 'p(car1)':15})
# print(manual_monitor.state)



### AUTOMATICALLY CREATED MONITOR TODO this should be the exact same (besides the node ids)


script_dir = os.path.dirname(os.path.abspath(__file__))
osc_path = os.path.join(script_dir, "../osc_files/my_overtake.osc")
input_stream = FileStream(osc_path)
lexer = openscenario2Lexer(input_stream)
stream = CommonTokenStream(lexer)
parser = openscenario2Parser(stream)
parser._errHandler = HardSyntaxErrorStrategy()
ctx = parser.osc_file()

visitor = TranslationGraphVisitor()
T: TranslationGraph = visitor.visit(ctx)

# translation_graph.draw()

gen_monitor = Monitor.from_translation_graph(T,ring=MinMaxMonitor)

# print(gen_monitor.syma_aut)



