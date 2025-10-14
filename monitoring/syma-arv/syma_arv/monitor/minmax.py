from syma_arv.monitor.abstract import AbstractMonitor
from syma_arv.constraint.evaluator.minmax import MinMaxEvaluator


class MinMaxMonitor(AbstractMonitor):
    def __init__(self, aut):
        AbstractMonitor.__init__(self, aut)
        self.c_evaluator = MinMaxEvaluator()

    def e_plus(self):
        return float('inf')

    def e_times(self):
        return 0

    def plus(self, val1, val2):
        return min(val1, val2)

    def times(self, val1, val2):
        return max(val1, val2)