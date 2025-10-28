import numpy as np
from z3 import *
from syma.constraint.translator.smt_translator import Constraint2SMT, RealConstraint2SMT, BoolConstraint2SMT

class Constraint(object):
    def __init__(self, alphabet=None, formula=None):
        self.alphabet = alphabet
        self.formula = formula

    def is_sat(self):
        solver = Solver()
        solver.add(self.smt_formula)
        result = solver.check()
        if result == sat:
            return True
        else:
            return False

    @property
    def formula(self):
        return self.__formula

    @formula.setter
    def formula(self, formula):
        self.__formula = formula

    @property
    def alphabet(self):
        return self.__alphabet

    @alphabet.setter
    def alphabet(self, alphabet):
        self.__alphabet = alphabet

    # felix 10/2025: 
    def __bool__(self):
        return bool(self.formula)


class RealConstraint(Constraint):

    def __init__(self, alphabet=None, formula=None):
        Constraint.__init__(self, alphabet, formula)
        self.smt_formula = RealConstraint2SMT(self).translate()
        self._volume = None

    def get_volume(self):
        if self._volume is None:
            return 1.0
        return self._volume

class BoolConstraint(Constraint):

    def __init__(self, alphabet=None, formula=None):
        Constraint.__init__(self, alphabet, formula)
        self.smt_formula = BoolConstraint2SMT(self).translate()
        self._volume = None

    def get_volume(self):
        if self._volume is None:
            self._compute_volume()
        return self._volume

    def isDNF(self):
        """ to be implemented """
        return True

    def _dnf_preprocessing(self):
        """
        Generate out of self.formula a new representation of the Boolean constraint in terms of a tuple
        (alphabet, s_, s__) as follows:

        alphabet => a dictionary mapping the Boolean variables occurring in the DNF Boolean formula to integer indices.
            The length of alphabet will give the number of Boolean variables n.

        s_ => a list of lists, i.e. s_ = [C1, C2, ..., Cm] where Ci represents the i-th (conjunction) clause of the
            DNF formula. Each Ci is a list containing the indices of the variables occurring in the literals of the i-th
            clause.
        s__ => a list of lists of 0's and 1's, analogue to s_, which is used together with s_ to build the
            literals of the DNF formula. 1 is used to indicate that the corresponding variable in s_ is negated,
            whereas 0 is used for positive literals.
        The length of s__ (as well as of s_) will give the number m of 'and' clauses occurring in the DNF formula.

        If an assignment to the Boolean variables of the DNF formula F is encoded into a bit vector bv of length n,
        where n is the number of Boolean variables occurring in F, then the above data representation allows to easily
        evaluate the Boolean constraint and any of its clauses individually.
        Example: Consider the DNF formula F = (a AND (NOT b) AND c) OR ((NOT a) AND c) OR (b AND c). Then:
                 alphabet =  {'a': 0, 'b': 1, 'c': 2}
                 s_  = [[0, 1, 2], [0, 2], [1, 2]]
                 s__ = [[0, 1, 0], [1, 0], [0, 0]]
            For the assignment {a=True, b=False, c=False}, then bv = [1, 0, 0] with 1 meaning True and 0 False.
            The evaluation of F is computed as
                max(min(abs(bv[s_[0]]-s__[0])), min(abs(bv[s_[1]]-s__[1])), min(abs(bv[s_[2]]-s__[2])))
            or alternatively
                max(min((bv[s_[0]]+s__[0]) mod 2), min((bv[s_[1]]+s__[1]) mod 2), min((bv[s_[2]]+s__[2]) mod 2))
            which yields
                max(min(1,1,0), min(0,0), min (0,0)) = 0 = False

        NOTE: We assume that self.formula is a Boolean DNF formula by construction.
        """
        s = str(self.formula).replace("(", " ").replace(")", " ")
        s_ = []
        s__ = []
        alphabet = {}
        n_vars = 0
        and_clauses = s.split(' or ')
        for and_clause in and_clauses:
            and_clause_ = []
            and_clause__ = []
            literals = and_clause.split(' and ')
            for literal in literals:
                literal = literal.strip()
                if literal.startswith('not '):
                    literal = literal[4:].strip()
                    and_clause__.append(1)
                else:
                    and_clause__.append(0)
                if literal not in alphabet:
                    alphabet[literal] = n_vars
                    n_vars += 1
                and_clause_.append(alphabet[literal])
            s_.append(and_clause_)
            s__.append(and_clause__)
        return s_, s__, alphabet

    def _compute_volume(self, epsilon=0.1, delta=0.05):
        """
        The volume of a Boolean constraint F with n Boolean variables is defined as the ratio #models/2^n, where
        #models is the number of models satisfying the Boolean formula F, i.e. the number of different assignments to
        the n Boolean variables which yield F true. Note that 2^n represents the total number of possible assignments.

        Computing #models is intractable in practice, thus we will strive for an approximate value of #models.
        We assume the Boolean constraint F is in disjunctive normal form (DNF), i.e. F = C_1 v C_2 v ... v C_m, and
        implement the KLM self-adjusting coverage algorithm to compute an approximate value of #models in
        O(n * m * log(1/delta) / epsilon^2) time, where n denotes the number of variables and m the number of clauses
        appearing in F (s. https://www.math.cmu.edu/users/af1p/Teaching/MCC17/Papers/KLM.pdf, page 437).

        NOTE: the algorithm does not work if an 'and' clause is not satisfiable, e.g. if a clause C_i contains the
              positive and the negative literals of the same variable at the same time
              (i.e. C_i = ... and v_k and ... and not v_k ...). However, duplicated literals do not cause any problem.

        Parameters:
        ----------
        epsilon: float \in (0, 1)
            Specification of the allowed error.
        delta: float \in (0, 1)
            Specification of the desired probabilistic guarantee.

        Return:
        ------
        The method applies first the KLM algorithm (s. above) to compute an approximation Y of the exact number of
        models #F of the Boolean constraint F s.t.
            Pr[(1 − epsilon) * #F ≤ Y ≤ (1 + epsilon) * #F] ≥ 1 − delta
        Then it uses Y to set self._volume:
            self._volume = Y / 2^n
        """

        assert self.isDNF(), "the Boolean constraint must be a Boolean formula in disjunctive normal form"

        # get the representation of the data into a format which allows an easier implementation of the KLM algo
        s_, s__, alphabet = self._dnf_preprocessing()

        m = len(s_)  # number of 'and' clauses
        n = len(alphabet)  # number of Boolean variables

        # gtime counts the global number of steps executed
        gtime = 0
        NT = 0
        T = np.ceil((8 * (1 + epsilon) * m * np.log(2 / delta)) / (epsilon ** 2))

        cardDs = [2 ** (n - len(set(Ci))) for Ci in
                  s_]  # taking len(set(Ci)) instead of len(Ci) makes it work also with duplicated literals
        A = [0]
        for i in range(m):
            A.append(A[-1] + cardDs[i])
        cardU = A[m]  # equivalent to cardU = np.sum(cardDs)

        outerLoopBreak = False
        while True:
            # randomly choose (s,i) in U with probability 1/|U|
            r = np.random.randint(low=1, high=cardU + 1)
            i = np.searchsorted(A, r)  # uses binary search to find the index i in A s.t. A[i-1]<r<=A[i] (1<= i <= m)
            i -= 1  # the indices of the m clauses range between {0, ..., m-1} in s_/s__, so we need to shift left by 1
            s = np.random.randint(low=0, high=2, size=n)  # equivalent to s = np.random.choice([0, 1], n)
            s[s_[i]] = 1 - np.array(s__[i])  # set the truth assignment for the vars which appear in C_i to satisfy C_i

            while True:
                gtime += 1
                if gtime > T:
                    outerLoopBreak = True   # enable the exit from the outer "while"
                    break
                j = np.random.randint(low=0, high=m)  # randomly choose j \in {0, ..., m-1} with proba = 1/m
                if min(abs(s[s_[j]] - np.array(s__[j]))) == 1:  # s \in D_j, i.e. s satisfies C_j
                    break
            if outerLoopBreak:
                break

            NT += 1

        Y_estimate = float(T * cardU) / (m * NT)  # approx. nr of models

        self._volume = Y_estimate / 2 ** n