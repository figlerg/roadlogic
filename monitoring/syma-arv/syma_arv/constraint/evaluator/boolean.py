from syma_arv.constraint.evaluator.abstract import AbstractEvaluator


class BooleanEvaluator(AbstractEvaluator):
    def e_plus(self):
        return True

    def e_times(self):
        return False

    def plus(self, val1, val2):
        return val1 and val2

    def times(self, val1, val2):
        return val1 or val2

    def d_geq(self, val1, val2):
        out = False if val1 >= val2 else True
        return out

    def d_greater(self, val1, val2):
        out = False if val1 > val2 else True
        return out

    def d_leq(self, val1, val2):
        out = False if val1 <= val2 else True
        return out

    def d_less(self, val1, val2):
        out = False if val1 < val2 else True
        return out

    def d_eq(self, val1, val2):
        out = False if val1 == val2 else True
        return out

    def d_neq(self, val1, val2):
        out = False if val1 != val2 else True
        return out

    