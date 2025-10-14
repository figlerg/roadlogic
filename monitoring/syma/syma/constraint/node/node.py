class Node(object):
    def __init__(self):
        self.children = list()

    def add_child(self, child):
        self.children.append(child)

    @property
    def children(self):
        return self.__children

    @children.setter
    def children(self, children):
        self.__children = children

    


class ConstantNode(Node):
    def __init__(self, value):
        Node.__init__(self)
        self.value = value

    def __str__(self):
        return str(self.value)

    @property
    def value(self):
        return self.__value

    @value.setter
    def value(self, value):
        self.__value = value


class VariableNode(Node):
    def __init__(self, name):
        Node.__init__(self)
        self.name = name

    def __str__(self):
        return self.name

    @property
    def name(self):
        return self.__name

    @name.setter
    def name(self, name):
        self.__name = name


class LEQNode(Node):
    def __init__(self, op1, op2):
        Node.__init__(self)
        self.children.append(op1)
        self.children.append(op2)

    def __str__(self):
        return '(' + str(self.children[0]) + ') <= (' + str(self.children[1]) + ')'


class LessNode(Node):
    def __init__(self, op1, op2):
        Node.__init__(self)
        self.children.append(op1)
        self.children.append(op2)

    def __str__(self):
        return '(' + str(self.children[0]) + ') < (' + str(self.children[1]) + ')'


class GEQNode(Node):
    def __init__(self, op1, op2):
        Node.__init__(self)
        self.children.append(op1)
        self.children.append(op2)

    def __str__(self):
        return '(' + str(self.children[0]) + ') >= (' + str(self.children[1]) + ')'


class GreaterNode(Node):
    def __init__(self, op1, op2):
        Node.__init__(self)
        self.children.append(op1)
        self.children.append(op2)

    def __str__(self):
        return '(' + str(self.children[0]) + ') > (' + str(self.children[1]) + ')'


class EqualNode(Node):
    def __init__(self, op1, op2):
        Node.__init__(self)
        self.children.append(op1)
        self.children.append(op2)

    def __str__(self):
        return '(' + str(self.children[0]) + ') == (' + str(self.children[1]) + ')'


class NEQNode(Node):
    def __init__(self, op1, op2):
        Node.__init__(self)
        self.children.append(op1)
        self.children.append(op2)

    def __str__(self):
        return '(' + str(self.children[0]) + ') != (' + str(self.children[1]) + ')'


class NotNode(Node):
    def __init__(self, op):
        Node.__init__(self)
        self.children.append(op)

    def __str__(self):
        return 'not(' + str(self.children[0]) + ')'


class AndNode(Node):
    def __init__(self, op1, op2):
        Node.__init__(self)
        self.children.append(op1)
        self.children.append(op2)

    def __str__(self):
        return '(' + str(self.children[0]) + ') and (' + str(self.children[1]) + ')'


class AddNode(Node):
    def __init__(self, op1, op2):
        Node.__init__(self)
        self.children.append(op1)
        self.children.append(op2)

    def __str__(self):
        return '(' + str(self.children[0]) + ') + (' + str(self.children[1]) + ')'


class MinusNode(Node):
    def __init__(self, op1, op2):
        Node.__init__(self)
        self.children.append(op1)
        self.children.append(op2)

    def __str__(self):
        return '(' + str(self.children[0]) + ') - (' + str(self.children[1]) + ')'


class PowNode(Node):
    def __init__(self, op1, op2):
        Node.__init__(self)
        self.children.append(op1)
        self.children.append(op2)

    def __str__(self):
        return '(' + str(self.children[0]) + ') ** (' + str(self.children[1]) + ')'


class OrNode(Node):
    def __init__(self, op1, op2):
        Node.__init__(self)
        self.children.append(op1)
        self.children.append(op2)

    def __str__(self):
        return '(' + str(self.children[0]) + ') or (' + str(self.children[1]) + ')'

class TrueNode(Node):
    def __init__(self):
        Node.__init__(self)

    def __str__(self) -> str:
        return 'T'
    