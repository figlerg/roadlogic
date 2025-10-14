from syma_arv.monitor.abstract import AbstractMonitor
from syma_arv.constraint.evaluator.boolean import BooleanEvaluator

class BooleanMonitor(AbstractMonitor):
    def __init__(self, aut):
        AbstractMonitor.__init__(self, aut)
        self.c_evaluator = BooleanEvaluator()

    def e_plus(self):
        return True

    def e_times(self):
        return False

    def plus(self, val1, val2):
        return val1 and val2

    def times(self, val1, val2):
        return val1 or val2