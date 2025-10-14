from syma_arv.constraint.evaluator.abstract import AbstractEvaluator


class MinMaxEvaluator(AbstractEvaluator):
    def e_plus(self):
        return float('inf')

    def e_times(self):
        return 0

    def plus(self, val1, val2):
        return min(val1, val2)

    def times(self, val1, val2):
        return max(val1, val2)

    def d_geq(self, val1, val2):
        out = 0 if val1 >= val2 else abs(val1 - val2)
        return out

    def d_greater(self, val1, val2):
        out = 0 if val1 > val2 else abs(val1 - val2)
        return out

    def d_leq(self, val1, val2):
        out = 0 if val1 <= val2 else abs(val1 - val2)
        return out

    def d_less(self, val1, val2):
        out = 0 if val1 < val2 else abs(val1 - val2)
        return out

    def d_eq(self, val1, val2):
        out = 0 if val1 == val2 else abs(val1 - val2)
        return out

    def d_neq(self, val1, val2):
        out = 0 if val1 != val2 else abs(val1 - val2)
        return out