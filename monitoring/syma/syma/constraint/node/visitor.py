from abc import ABCMeta, abstractmethod
from syma.constraint.node.node import *

NOT_IMPLEMENTED = "You should implement this."


class NodeVisitor:
    __metaclass__ = ABCMeta

    def visit(self, node, args):
        out = None

        if isinstance(node, ConstantNode):
            out = self.visitConstant(node, args)
        elif isinstance(node, VariableNode):
            out = self.visitVariable(node, args)
        elif isinstance(node, LEQNode):
            out = self.visitLEQ(node, args)
        elif isinstance(node, LessNode):
            out = self.visitLess(node, args)
        elif isinstance(node, GEQNode):
            out = self.visitGEQ(node, args)
        elif isinstance(node, GreaterNode):
            out = self.visitGreater(node, args)
        elif isinstance(node, EqualNode):
            out = self.visitEqual(node, args)
        elif isinstance(node, NEQNode):
            out = self.visitNEQ(node, args)
        elif isinstance(node, NotNode):
            out = self.visitNot(node, args)
        elif isinstance(node, AndNode):
            out = self.visitAnd(node, args)
        elif isinstance(node, OrNode):
            out = self.visitOr(node, args)
        elif isinstance(node, AddNode):
            out = self.visitAdd(node, args)
        elif isinstance(node, PowNode):
            out = self.visitPow(node, args)
        elif isinstance(node, MinusNode):
            out = self.visitMinus(node, args)
        elif isinstance(node, TrueNode):
            out = self.visitTrue(node, args)
        else:
            raise Exception('Node Visitor: unexpected method called.')
        return out

    @abstractmethod
    def visitConstant(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitVariable(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitGEQ(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitGreater(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitLEQ(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitLess(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitEqual(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitNEQ(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitNot(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitAnd(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitOr(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitAdd(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitPow(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)

    @abstractmethod
    def visitMinus(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)
    
    @abstractmethod
    def visitTrue(self, node, args):
        raise NotImplementedError(NOT_IMPLEMENTED)
