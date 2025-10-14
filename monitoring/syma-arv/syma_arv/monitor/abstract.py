from abc import ABCMeta, abstractmethod
import copy

NOT_IMPLEMENTED = "This method is abstract and must be implemented."


class AbstractMonitor(object):
    __metaclass__ = ABCMeta

    def __init__(self, aut):
        self.state = dict()
        self.pstate = dict()
        self.aut = aut
        self.c_evaluator = None

    @property
    def state(self):
        return self.__state

    @state.setter
    def state(self, state):
        self.__state = state

    @property
    def pstate(self):
        return self.__pstate

    @pstate.setter
    def pstate(self, pstate):
        self.__pstate = pstate

    def initialize(self):
        for key in self.aut.automaton.nodes:
            if key.initial:
                self.state[key] = self.e_times()
                self.pstate[key] = self.e_times()
            else:
                self.state[key] = self.e_plus()
                self.pstate[key] = self.e_plus()

    def update(self, vals):

        for key in self.pstate:
            self.pstate[key] = self.state[key]

        for key in self.state:
            incoming = self.aut.incoming[key]
            val = self.e_plus()
            for in_tran in incoming:
                prev_cost = self.pstate[in_tran[1]]
                constraint = in_tran[3]
                tran_cost = self.c_evaluator.evaluate(constraint, vals)
                cost = self.times(prev_cost, tran_cost)
                val = self.plus(val, cost)
            self.state[key] = val

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



