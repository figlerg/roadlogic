from syma.automaton.automaton import Location, SymbolicAutomaton
from syma.constraint.constraint import Constraint
from syma.constraint.node.node import *

from syma_arv.monitor.boolean import BooleanMonitor
from syma_arv.monitor.minmax import MinMaxMonitor
from syma_arv.monitor.tropical import TropicalMonitor

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
    var_node = VariableNode('a')
    zero_node = ConstantNode(0)
    five_node = ConstantNode(5)
    less_5_node = LessNode(var_node, five_node)
    geq_5_node = GEQNode(var_node, five_node)
    geq_0_node = GEQNode(var_node, zero_node)
    in_0_5_node = AndNode(geq_0_node, less_5_node)


    # a < 5
    constraint_1 = Constraint(formula=less_5_node)
    # a >= 5
    constraint_2 = Constraint(formula=geq_5_node)
    # a >= 0 and a < 5
    constraint_3 = Constraint(formula=in_0_5_node)

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

    # print('Tropical:\n')
    # t_mon = TropicalMonitor(aut)
    # t_mon.initialize()
    # print(str(t_mon.state))
    # t_mon.update({'a': 1})
    # print(str(t_mon.state))
    # t_mon.update({'a': 2})
    # print(str(t_mon.state))
    # t_mon.update({'a': 7})
    # print(str(t_mon.state))

    print('MinMax:\n')
    m_mon = MinMaxMonitor(aut)
    m_mon.initialize()
    # print(str(m_mon.state))
    # m_mon.update({'a': 1})
    # print(str(m_mon.state))
    # m_mon.update({'a': 2})
    # print(str(m_mon.state))
    m_mon.update({'a': 7})
    print(str(m_mon.state))

    # print(f'Aut:\n{aut}')

    # print('Boolean:\n')
    # b_mon = BooleanMonitor(aut)
    # b_mon.initialize()
    # # print(str(b_mon.state))
    # # b_mon.update({'a': 1})
    # # print(str(b_mon.state))
    # # b_mon.update({'a': 2})
    # # print(str(b_mon.state))
    # b_mon.update({'a': 7})
    # print(str(b_mon.state))


    