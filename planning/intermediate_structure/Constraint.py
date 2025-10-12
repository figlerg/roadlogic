from enum import Enum


# from z3 import Int, Real, simplify, And


class Relation(Enum):
    # EDIT 02.03.2024: use the signs instead of ints so it's easier to use this class in experiments
    #  TODO this makes the strings useless/unclean... maybe just return the value now?
    EQ = '=='
    LEQ = '<='
    GEQ = '>='
    L = '<'
    G = '>'
    INEQ = '!='

    def __str__(self):
        if self._name_ == 'EQ':
            return '=='
        if self._name_ == 'LEQ':
            return '<='
        if self._name_ == 'GEQ':
            return '>='
        if self._name_ == 'L':
            return '<'
        if self._name_ == 'G':
            return '>'
        if self._name_ == 'INEQ':
            return '!='

    def __eq__(self, other):
        return str(self) == str(other)


def give_complementary_relation(in_enum):
    if in_enum == Relation.G:
        return Relation.L
    elif in_enum == Relation.L:
        return Relation.G
    elif in_enum == Relation.LEQ:
        return Relation.GEQ
    elif in_enum == Relation.GEQ:
        return Relation.LEQ
    elif in_enum == Relation.EQ:
        return Relation.EQ
    elif in_enum == Relation.INEQ:
        return Relation.INEQ


class Modifier(Enum):
    LANE = 'l'
    POSITION = 'p'

    def __str__(self):
        if self._name_ == 'LANE':
            return 'l'
        if self._name_ == 'POSITION':
            return 'p'

    def __eq__(self, other):
        return str(self) == str(other)


class Constraint:
    """
    The internal class for handling relative positional modifiers from OSC2.

    It encodes modifiers such as "lane(same_as:car1, at:start)" as mathematical relations between objects.
    This example would be "l(car1) == l(ego)", where 'at_start' is only used for defining where in the
    graph this constraint is placed.

    TODO for now, I only allow a very small subset of possible constraints:
     Linear constraints where the lanes and positions are not mixed and can only appear with factor 1.
    ...
    Attributes
    ----------
    __actor_1: str
        Name of the first actor.
    __actor_2: str
        Name of the second actor.
    __modifier: Modifier
        Enumerator for the type of modifier that is used (lane, position).
        Mixed usage is not allowed (makes not much sense to have this freedom in the specs).
    __relation: Relation
        Enumerator for specifying the relation between the cars.
    __c: float
        A constant to allow constraints such as 'l(car1) == l(ego) + 1'.

    Methods
    -------
    eval(val):
        Returns True if a set of values satisfies the constraint, False otherwise.
        If the valuation does not have the information necessary to decide, raise an exception.
    ...
    """

    def __init__(self, actor_1, actor_2, modifier, relation, c=0):
        self.__actor_1 = actor_1
        self.__actor_2 = actor_2
        self.__modifier = modifier
        self.__relation = relation
        self.__c = c

        # added: I want to keep a pointer for the other part of the interval in case of position intervals
        self.__interval_partner = None

    @property
    def interval_partner(self):
        return self.__interval_partner

    @property
    def c(self):
        return self.__c

    @property
    def relation(self):
        return self.__relation

    @relation.setter
    def relation(self, value):
        self.__relation = value

    @property
    def modifier(self):
        return self.__modifier

    @modifier.setter
    def modifier(self, value):
        self.__modifier = value

    @property
    def actor_1(self):
        return self.__actor_1

    @actor_1.setter
    def actor_1(self, value):
        self.__actor_1 = value

    @property
    def actor_2(self):
        return self.__actor_2

    @actor_2.setter
    def actor_2(self, value):
        self.__actor_2 = value

    def eval(self, placement: dict):
        a1 = self.actor_1
        a2 = self.actor_2
        c = self.c

        assert a1 in placement.keys() and a2 in placement.keys(), \
            "Encountered a constraint whose truth value cannot be determined. Is the actor not initialized?"

        lane1, segment1 = placement[a1]
        lane2, segment2 = placement[a2]

        # TODO not elegant, but gets the job done...
        if self.modifier == Modifier.LANE:
            if self.relation == Relation.L:
                return lane1 < lane2 + c
            elif self.relation == Relation.G:
                return lane1 > lane2 + c
            elif self.relation == Relation.EQ:
                return lane1 == lane2 + c
            else:
                raise NotImplementedError

        # here I also allow geq, leq
        if self.modifier == Modifier.POSITION:
            if self.relation == Relation.L:
                return segment1 < segment2 + c
            elif self.relation == Relation.G:
                return segment1 > segment2 + c
            elif self.relation == Relation.LEQ:
                return segment1 <= segment2 + c
            elif self.relation == Relation.GEQ:
                return segment1 >= segment2 + c
            elif self.relation == Relation.EQ:
                return segment1 == segment2 + c
            else:
                raise NotImplementedError

        raise NotImplementedError("This should not be reachable.")

    def __str__(self):
        actor_1_decorated = f"{self.__modifier}_{self.__actor_1}"
        actor_2_decorated = f"{self.__modifier}_{self.__actor_2}"

        out = f"{actor_1_decorated} {self.__relation} {actor_2_decorated}"

        if self.__c > 0:
            out += f" + {self.__c}"
        elif self.__c < 0:
            out += f" {self.__c}"

        return out

    def __repr__(self):
        return str(self)

    def __hash__(self):
        return hash(repr(sorted(self.__dict__.items())))

    def __eq__(self, other):

        # normally I would just compare dict, but this leads to an infinite recursion because the __interval_partner
        #  is also a constraint. So I need to compare dict by hand and cast the object to str before comparing.

        dict1_without_interval_partner = {k: v for k, v in self.__dict__.items() if
                                          k != '_Constraint__interval_partner'}
        dict2_without_interval_partner = {k: v for k, v in other.__dict__.items() if
                                          k != '_Constraint__interval_partner'}

        if dict1_without_interval_partner == dict2_without_interval_partner:
            return True

        # there's a second way for the constraints to be equal: namely if they are flipped
        if self.__relation == Relation.EQ or self.__relation == Relation.INEQ:
            a1 = self.__actor_1
            b1 = self.__actor_2
            a2 = other.__actor_1
            b2 = other.__actor_2

            c1 = self.__c
            c2 = other.__c

            # Once we are in this case, the only way the two objects can encode the same constraint is when the two
            # sides are flipped and c is moved to the other side.
            return (a1 == b2) and (a2 == b1) and (c1 == -c2)

        # As long as we don't allow products with l(x) or p(x), all other combinations are surely not the same:
        # The above cases were symmetric, the inequalities are antisymmetric. Thus, we can enforce a cononical position
        #  for the constant c (on the right hand side of the relation w.r. to the actor numbers).
        else:
            return False

    # Some utilities:

    def match(self, other):
        # matches this constraint to another constraint. Is invoked if both are created from a position interval.
        # makes bookkeeping easier

        self.__interval_partner = other
        other.__interval_partner = self

    # def related(self, other):
    #     # check if both modifier and actors coincide
    #     # NOTE: this assumes that the order of two actors is the same, which is how I create them in the parser
    #     return self.actor_1 == other.actor_1 \
    #         and self.actor_2 == other.actor_2 \
    #         and self.__modifier == other.__modifier \

    # def asp_format(self, segment_length = None, t = 0):
    #
    #     if not t:
    #         t_str = '0'  # only initial conditions are handled with a concrete t
    #     else:
    #         t_str = f'T{t}'  # the rest is an abstract time point we don't know a priori (created by clingo)
    #
    #     if self.__modifier == Modifier.LANE:
    #
    #         if self.__relation == Relation.EQ:
    #             out = f"same_lane({self.__actor_1},{self.__actor_2},{t_str})"
    #         elif self.__relation == Relation.L:
    #             out = f"left_of({self.__actor_1},{self.__actor_2},{t_str})"
    #         elif self.__relation == Relation.G:
    #             out = f"right_of({self.__actor_1},{self.__actor_2},{t_str})"
    #         else:
    #             raise NotImplementedError
    #
    #
    #     elif self.__modifier == Modifier.POSITION:
    #         # out = f'% position placeholder for constraint {self.__str__()}'
    #
    #         partner = self.__interval_partner
    #
    #         actor1 = str(self.__actor_1)
    #         actor2 = str(self.__actor_2)
    #
    #         # position constraints always appear in pairs and are of the form p(x) REL p(y) + c. So I can recreate the interval from here.
    #
    #         cs = [self.__c, partner.__c]
    #         a,b = int(min(cs)/segment_length), int(max(cs)/segment_length)
    #         # TODO this might create problems.
    #         #   Won't work for arbitrary floats in the intervals.
    #
    #         # TODO this is a bit weird: might be that I need to handle t=0 and t=T{t} separately... can't write the positive rule below as a fact, right?
    #         # out = f":- S - S2 > {a}, holds(on({actor1},_,S),0), holds(on({actor2},_,S2),0)"
    #         # out += f":- S - S2 < {b}, holds(on({actor1},_,S),0), holds(on({actor2},_,S2),0)"
    #
    #         if t:
    #             # this is the POSITIVE statement that must hold
    #             out = f"segment(S), segment(S2), holds(on({actor1},_,S),{t_str}),holds(on({actor2},_,S2),{t_str}), S - S2 >= {a}, S - S2 <= {b}"
    #             # i.e. "the position at start must be in the interval (scaled down to segment length)"
    #         else:
    #             # at time 0 we need to phrase this as a constraint and negate the inequalities, because otherwise S, S2 are not safe (don't ask me why)
    #             # also, we need to do the two separately to get disjunction of the two possibilities to be NOT in the interval.
    #             out = f":-segment(S), segment(S2), holds(on({actor1},_,S),{t_str}),holds(on({actor2},_,S2),{t_str}), S - S2 < {a}.\n" \
    #                   f":-segment(S), segment(S2), holds(on({actor1},_,S),{t_str}),holds(on({actor2},_,S2),{t_str}), S - S2 > {b}"
    #             # out = '%' # debugging
    #
    #     else:
    #         raise NotImplementedError("Expected lane or position modifier.")
    #
    #
    #     return out

    def asp_goal_format(self, indices):
        # All the constraints are relational constraints between two actors. In the end I want something like this:
        # goal1(T,t) :- time(T,t), query(t), T<=t, holds(state(car1,loc(L1,S1),dyn(Vel1,0)), T), holds(state(ego,loc(L,S),dyn(Vel,0)), T), L < L1.

        # But it could also have multiple constraints for the same actor pair. So I do the part
        # "goal1(T,t) :- time(T,t), query(t), T<=t, holds(state(car1,loc(L1,S1),dyn(Vel1,0)), T), holds(state(ego,loc(L,S),dyn(Vel,0)), T)"
        #  outside and add only some atoms here which encode the relation.

        actor1 = str(self.__actor_1)
        actor2 = str(self.__actor_2)

        goal_atoms = []

        i1 = indices[actor1]
        i2 = indices[actor2]

        if self.__modifier == Modifier.LANE:
            if self.__relation == Relation.L:
                goal_atoms.append(f"L{i1} < L{i2}")
            elif self.__relation == Relation.G:
                goal_atoms.append(f"L{i1} > L{i2}")
            elif self.__relation == Relation.EQ:
                goal_atoms.append(f"L{i1} = L{i2}")
            else:
                raise NotImplementedError

        elif self.__modifier == Modifier.POSITION:
            partner = self.__interval_partner
            cs = [self.__c, partner.__c]
            a, b = int(min(cs)), int(max(cs))

            # ego... with position([a..b], behind:car1, at:start)
            # ego has segment S1, car1 has segment S2

            # working actor is actor1, relative actor is actor2. Depending on 'behind' or 'in_front' directive, we flip S1 and S2.
            if self.relation == Relation.L:
                goal_atoms.append(f"{a} < (S{i1} - S{i2}) < {b}")
            elif self.relation == Relation.G:
                goal_atoms.append(f"{a} < (S{i1} - S{i2}) < {b}")
            elif self.relation == Relation.LEQ:
                goal_atoms.append(f"{a} <= (S{i1} - S{i2}) <= {b}")
            elif self.relation == Relation.GEQ:
                goal_atoms.append(f"{a} <= (S{i1} - S{i2}) <= {b}")
            else:
                raise NotImplementedError


        else:
            raise NotImplementedError

        return goal_atoms

    @property
    def exp1(self):
        return f"{self.__modifier}({self.__actor_1})"

    @property
    def exp2(self):
        return f"{self.__modifier}({self.__actor_2})"

        # In the final structure we want to use z3:
        # def to_z3(self):
        #     if self.__modifier == Modifier.POSITION:
        #         z3_type = Real
        #     elif self.__modifier == Modifier.LANE:
        #         z3_type = Int
        #     else:
        #         raise NotImplementedError()
        # exp1 = z3_type(self.exp1)
        # exp2 = z3_type(self.exp2)
        #
        # if self.__c:
        #
        #     if self.__relation == Relation.EQ:
        #         return exp1 == exp2 + self.__c
        #     elif self.__relation == Relation.LEQ:
        #         return exp1 <= exp2 + self.__c
        #     elif self.__relation == Relation.GEQ:
        #         return exp1 >= exp2 + self.__c
        #     elif self.__relation == Relation.L:
        #         return exp1 < exp2 + self.__c
        #     elif self.__relation == Relation.G:
        #         return exp1 > exp2 + self.__c
        #     elif self.__relation == Relation.INEQ:
        #         return exp1 != exp2 + self.__c
        #     else:
        #         raise Exception('Surprising outcome!')
        #
        # if self.__relation == Relation.EQ:
        #     return exp1 == exp2
        # elif self.__relation == Relation.LEQ:
        #     return exp1 <= exp2
        # elif self.__relation == Relation.GEQ:
        #     return exp1 >= exp2
        # elif self.__relation == Relation.L:
        #     return exp1 < exp2
        # elif self.__relation == Relation.G:
        #     return exp1 > exp2
        # elif self.__relation == Relation.INEQ:
        #     return exp1 != exp2
        # else:
        #     raise Exception('Surprising outcome!')

    def flip(self):
        # rewrite "p(actor2) R p(actor1) + c" as "p(actor) R' p(actor2) -c"
        self.__actor_1, self.__actor_2 = self.actor_2, self.__actor_1
        self.__c *= -1

        new_rel = give_complementary_relation(self.__relation)

        self.__relation = None
        self.__relation = new_rel

    def standardize(self):
        actors = [self.__actor_1, self.__actor_2]
        if not sorted(actors) == actors:
            self.flip()

    def ascending(self):
        if self.relation in [Relation.G, Relation.GEQ]:
            self.flip()

        # To do this here is a bit hacky, but flipping equalities does not hurt ever and will help later when
        # contracting edges (nx always keeps the first node of a contracted edge, and I want ego to stay as a node).
        # So I always swap ego to be the first actor.
        if self.relation == Relation.EQ:
            if self.actor_2 == 'ego':
                self.flip()

    def __lt__(self, other):
        # a < b shall mean that a is a tighter constraint than b.
        # This returns false if they are incomparable or if they contradict.

        if self == other:
            return True

        if self.__modifier != other.__modifier:
            return False

        self.standardize()  # Beware, this happens in place
        other.standardize()

        if self.__actor_1 == other.__actor_1 and self.__actor_2 == other.__actor_2:
            smaller_rels = [Relation.L, Relation.LEQ]
            greater_rels = [Relation.G, Relation.GEQ]

            if self.__relation in smaller_rels and other.__relation in smaller_rels:
                if self.__c < other.__c:
                    return True
                if self.__relation == Relation.L:
                    # This differs between lesser and lesser-equal. This case means that self is stricter.
                    return True

            # a > b + c1, a > b + c2, if c2 is greater the constraint is tighter
            if self.__relation in greater_rels and other.__relation in greater_rels:
                if self.__c > other.__c:
                    return True
                if self.__relation == Relation.G:
                    return True

        return False

    # def __gt__(self, other):
    #     if self == other:
    #         return True
    #     self.standardize() # Beware, this happens in place
    #     other.standardize()
    #
    #
    #     if self.__actor_1 == other.__actor_1 and self.__actor_2 == other.__actor_2:
    #         smaller_rels = [Relation.L, Relation.LEQ]
    #         greater_rels = [Relation.G, Relation.GEQ]
    #
    #         if self.__relation in smaller_rels and other.__relation in smaller_rels:
    #             if self.__c > other.__c:
    #                 return True
    #             if other.__relation == Relation.L:
    #                 # This differs between lesser and lesser-equal. This case means that self is stricter.
    #                 return True
    #
    #         # a > b + c1, a > b + c2, if c2 is greater the constraint is tighter
    #         if self.__relation in greater_rels and other.__relation in greater_rels:
    #             if self.__c < other.__c:
    #                 return True
    #             if other.__relation == Relation.G:
    #                 return True
    #
    #     return False


if __name__ == '__main__':
    eq = Relation.EQ
    l = Relation.L
    g = Relation.G

    actor1 = 'car1'
    actor2 = 'car2'

    con_lane_l = Constraint(actor1, actor2, Modifier.LANE, Relation.L)
    con_lane_g = Constraint(actor1, actor2, Modifier.LANE, Relation.G)
    con_lane_e = Constraint(actor1, actor2, Modifier.LANE, Relation.EQ)
    con_pos_l = Constraint(actor1, actor2, Modifier.POSITION, Relation.L, 5)
    con_pos_g = Constraint(actor1, actor2, Modifier.POSITION, Relation.G, 10)

    rels = [con_lane_l, con_lane_g, con_lane_e, con_pos_g, con_pos_l]

    for r in rels:
        print(r)
        # r.standardize()
        # print(r)

    # eq = Relation.EQ
    # eq = Relation.EQ
    # testmod = Modifier.LANE
    #
    # test = Constraint('ego', 'car1', testmod, testrel, 1)
    #
    # testrel2 = Relation.EQ
    # testmod2 = Modifier.LANE
    #
    # test2 = Constraint('car1', 'ego', testmod, testrel, -1)

    # test.standardize()
    # test2.standardize()
    #
    # print(test)
    # print(test2)
    #
    # print(test == test2)
