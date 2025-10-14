from syma.constraint.node.node import *

def test_constant_node():
    node = ConstantNode(5)

    assert str(node) == '5'


def test_variable_node():
    node = VariableNode('req')

    assert str(node) == 'req'


def test_leq_node():
    node1 = VariableNode('req')
    node2 = ConstantNode('5')
    node = LEQNode(node1, node2)

    assert str(node) == '(req) <= (5)'


def test_less_node():
    node1 = VariableNode('req')
    node2 = ConstantNode('5')
    node = LessNode(node1, node2)

    assert str(node) == '(req) < (5)'


def test_geq_node():
    node1 = VariableNode('req')
    node2 = ConstantNode('5')
    node = GEQNode(node1, node2)

    assert str(node) == '(req) >= (5)'


def test_greater_node():
    node1 = VariableNode('req')
    node2 = ConstantNode('5')
    node = GreaterNode(node1, node2)

    assert str(node) == '(req) > (5)'

def test_eq_node():
    node1 = VariableNode('req')
    node2 = ConstantNode('5')
    node = EqualNode(node1, node2)

    assert str(node) == '(req) == (5)'

def test_neq_node():
    node1 = VariableNode('req')
    node2 = ConstantNode('5')
    node = NEQNode(node1, node2)

    assert str(node) == '(req) != (5)'

def test_not_node():
    node1 = VariableNode('req')
    node = NotNode(node1)

    assert str(node) == 'not(req)'

def test_and_node():
    node11 = VariableNode('req')
    node12 = ConstantNode('5')
    node1 = GEQNode(node11, node12)

    node21 = VariableNode('gnt')
    node22 = ConstantNode('3')
    node2 = GEQNode(node21, node22)

    node = AndNode(node1, node2)

    assert str(node) == '((req) >= (5)) and ((gnt) >= (3))'


def test_or_node():
    node11 = VariableNode('req')
    node12 = ConstantNode('5')
    node1 = GEQNode(node11, node12)

    node21 = VariableNode('gnt')
    node22 = ConstantNode('3')
    node2 = GEQNode(node21, node22)

    node = OrNode(node1, node2)

    assert str(node) == '((req) >= (5)) or ((gnt) >= (3))'
