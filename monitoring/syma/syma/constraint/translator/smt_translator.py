from z3 import *
from syma.constraint.node.visitor import NodeVisitor


class Constraint2SMT(NodeVisitor):
    def __init__(self, constraint):
        self.constraint = constraint

    def translate(self):
        out = self.visit(self.constraint.formula, [])
        return out

    def visitConstant(self, node, args):
        return RealVal(str(node.value))

    def visitVariable(self, node, args):
        return Real(node.name)

    def visitGEQ(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return op1 >= op2

    def visitGreater(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return op1 > op2

    def visitLEQ(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return op1 <= op2

    def visitLess(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return op1 < op2

    def visitEqual(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return op1 == op2

    def visitNEQ(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return op1 != op2

    def visitNot(self, node, args):
        op = self.visit(node.children[0], args)
        return Not(op)

    def visitAnd(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return And(op1, op2)

    def visitOr(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return Or(op1, op2)

    def visitAdd(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return (op1 + op2)

    def visitMinus(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return (op1 + op2)

    def visitPow(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return (op1 - op2)


class RealConstraint2SMT(Constraint2SMT):
    def __init__(self, constraint):
        Constraint2SMT.__init__(self, constraint)

    def visitConstant(self, node, args):
        return RealVal(str(node.value))

    def visitVariable(self, node, args):
        return Real(node.name)


class BoolConstraint2SMT(Constraint2SMT):
    def __init__(self, constraint):
        Constraint2SMT.__init__(self, constraint)

    def visitConstant(self, node, args):
        return BoolVal(str(node.value))

    def visitVariable(self, node, args):
        return Bool(node.name)

    def visitGEQ(self, node, args):
        raise Exception('>= is not a Boolean operator')

    def visitGreater(self, node, args):
        raise Exception('> is not a Boolean operator')

    def visitLEQ(self, node, args):
        raise Exception('<= is not a Boolean operator')

    def visitLess(self, node, args):
        raise Exception('< is not a Boolean operator')

    def visitEqual(self, node, args):
        raise Exception('== is not a Boolean operator')

    def visitNEQ(self, node, args):
        raise Exception('!= is not a Boolean operator')
