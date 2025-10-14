from abc import ABCMeta, abstractmethod
from syma.constraint.node.visitor import NodeVisitor

NOT_IMPLEMENTED = "This method is abstract and must be implemented."


class AbstractEvaluator(NodeVisitor):
    __metaclass__ = ABCMeta

    def evaluate(self, constraint, val):
        out = self.visit(constraint.formula, [val])
        return out

    def visitConstant(self, node, args):
        return float(node.value)

    def visitVariable(self, node, args):
        val = args[0]

        if node.name not in val.keys():
            raise Exception(f'Reference to a non-existing variable: {node.name} is not in {val.keys()}')

        return val[node.name]

    def visitGEQ(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        out = self.d_geq(op1, op2)
        return out

    def visitGreater(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        out = self.d_greater(op1, op2)
        return out

    def visitLEQ(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        out = self.d_leq(op1, op2)
        return out

    def visitLess(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        out = self.d_less(op1, op2)
        return out

    def visitEqual(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        out = self.d_eq(op1, op2)
        return out

    def visitNEQ(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        out = self.d_neq(op1, op2)
        return out

    def visitAnd(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return self.times(op1, op2)

    def visitOr(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return self.plus(op1, op2)
    
    def visitNot(self, node, args):
        raise Exception('Cannot evaluate the Not node.')
    
    def visitAdd(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return op1+op2
    
    def visitMinus(self, node, args):
        op1 = self.visit(node.children[0], args)
        op2 = self.visit(node.children[1], args)
        return op1-op2
    
    def visitTrue(self, node, args):
        return 0

    @abstractmethod
    def e_plus(self):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def e_times(self):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def plus(self, val1, val2):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def times(self, val1, val2):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def d_geq(self, val1, val2):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def d_greater(self, val1, val2):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def d_leq(self, val1, val2):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def d_less(self, val1, val2):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def d_eq(self, val1, val2):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def d_neq(self, val1, val2):
        raise NotImplementedError(NOT_IMPLEMENTED)
