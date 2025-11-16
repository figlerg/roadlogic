from enum import Enum
from abc import ABC, abstractmethod

# from z3 import Int, Real, simplify, And



from abc import ABC, abstractmethod
from typing import Dict, Tuple



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

    @property
    def flipped(self):
        if self == Relation.G:
            return Relation.L
        elif self == Relation.L:
            return Relation.G
        elif self == Relation.LEQ:
            return Relation.GEQ
        elif self == Relation.GEQ:
            return Relation.LEQ
        elif self == Relation.EQ:
            return Relation.EQ
        elif self == Relation.INEQ:
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



# Placement: actor -> (lane, position)
Placement = Dict[str, Tuple[int, float]]


class BaseConstraint(ABC):
    """
    Abstract base class for all constraint types.

    This class defines the common interface that every constraint must implement.
    Concrete subclasses include `RelativeConstraint` for binary actor-to-actor
    relations and `AbsoluteConstraint` for constraints involving global positions
    or lane indices.

    Methods
    -------
    eval(placement)
        Evaluate the constraint for the given placement mapping
        actor -> (lane, position). Must be implemented by subclasses.
    __str__()
        Return a human-readable representation of the constraint.
    is_relative()
        Whether this constraint represents a relative actor-to-actor relation.
        Defaults to False, can be overridden by subclasses.
    is_absolute()
        Whether this constraint represents an absolute (global) condition.
        Defaults to False, can be overridden by subclasses.
    """

    @abstractmethod
    def eval(self, placement: Placement) -> bool:
        raise NotImplementedError

    @abstractmethod
    def __str__(self) -> str:
        raise NotImplementedError

    def is_relative(self) -> bool:
        return False

    def is_absolute(self) -> bool:
        return False


class AbsoluteConstraint(BaseConstraint):
    """
    A constraint expressing an absolute condition on a single actor.

    This class represents constraints that refer to global values, such as
    requiring an actor to be on a specific lane or within a longitudinal
    interval. Unlike `RelativeConstraint`, it does not relate two actors to
    each other but compares an actor's attribute against a fixed value.

    Examples
    --------
    - lane(ego) == 1
    - pos(car1) >= 10
    - pos(ego) <= 20

    Attributes
    ----------
    _actor : str
        Name of the actor to which the constraint applies.
    _modifier : Modifier
        Specifies whether the constraint refers to lane or position.
    _relation : Relation
        Comparison operator applied between the actor’s value and the constant.
    _value : float
        Constant reference value used in the comparison.

    Methods
    -------
    eval(placement)
        Evaluate the absolute constraint for the given placement mapping
        actor -> (lane, position). Raises an exception if the actor is missing.
    __str__()
        Return a readable string representation.
    is_absolute()
        Override: this constraint is absolute.
    """

    def __init__(self, actor: str, modifier: Modifier, relation: Relation, value: float):
        self._actor = actor
        self._modifier = modifier
        self._relation = relation
        self._value = value

    @property
    def actor(self) -> str:
        return self._actor

    @property
    def modifier(self) -> Modifier:
        return self._modifier

    @property
    def relation(self) -> Relation:
        return self._relation

    @property
    def value(self) -> float:
        return self._value

    def is_absolute(self) -> bool:
        return True

    def eval(self, placement: Placement) -> bool:
        if self._actor not in placement:
            raise KeyError(
                f"Actor '{self._actor}' not found in placement; "
                f"cannot evaluate absolute constraint."
            )

        lane, position = placement[self._actor]

        if self._modifier == Modifier.LANE:
            x = lane
        elif self._modifier == Modifier.POSITION:
            x = position
        else:
            raise NotImplementedError(f"Unsupported modifier: {self._modifier}")

        v = self._value
        r = self._relation

        if r == Relation.L:
            return x < v
        if r == Relation.G:
            return x > v
        if r == Relation.LEQ:
            return x <= v
        if r == Relation.GEQ:
            return x >= v
        if r == Relation.EQ:
            return x == v
        if r == Relation.INEQ:
            return x != v

        raise NotImplementedError(f"Unsupported relation: {r}")

    def __str__(self) -> str:
        return f"{self._modifier}({self._actor}) {self._relation.value} {self._value}"

    def __repr__(self) -> str:
        return str(self)


class RelativeConstraint(BaseConstraint):
    """
    A constraint representing a relative positional relationship between two actors.

    This class encodes binary relations such as "lane(car1) < lane(car2)" or
    "pos(a) >= pos(b) + c". These are the original constraint types used throughout
    the project and always involve two distinct actors. The modifier determines
    whether the relation applies to lane indices or longitudinal positions.
    Absolute or global constraints are handled separately via `AbsoluteConstraint`.

    With the introduction of `BaseConstraint` and `AbsoluteConstraint`, this class
    strictly models actor-to-actor relations. Transformations such as flipping,
    standardization, or ascending ordering are meaningful only for this binary
    constraint type. Code that requires relative constraints should explicitly check
    for `isinstance(obj, RelativeConstraint)` to ensure that absolute constraints are
    rejected early.

    Attributes
    ----------
    __actor_1 : str
        Name of the first actor.
    __actor_2 : str
        Name of the second actor.
    __modifier : Modifier
        Specifies whether the constraint compares lane or position.
    __relation : Relation
        The comparison operator used between the two actors.
    __c : float
        Constant offset, e.g. for constraints of the form
        pos(a) == pos(b) + c.

    Methods
    -------
    eval(placement)
        Evaluate the constraint for a given placement mapping
        actor -> (lane, position). Raises an exception if required
        information is missing.
    flip()
        Return an equivalent constraint with actor_1 and actor_2 swapped.
    standardize()
        Normalize the constraint by reordering actors where appropriate.
    ascending(actor_list)
        Return the constraint rewritten according to an ordering of actors.
    __str__()
        Return a human-readable representation.
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

        new_rel = self.__relation.flipped

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

    print(l.flipped)

    actor1 = 'car1'
    actor2 = 'car2'

    con_lane_l = RelativeConstraint(actor1, actor2, Modifier.LANE, Relation.L)
    con_lane_g = RelativeConstraint(actor1, actor2, Modifier.LANE, Relation.G)
    con_lane_e = RelativeConstraint(actor1, actor2, Modifier.LANE, Relation.EQ)
    con_pos_l = RelativeConstraint(actor1, actor2, Modifier.POSITION, Relation.L, 5)
    con_pos_g = RelativeConstraint(actor1, actor2, Modifier.POSITION, Relation.G, 10)

    con_lane_l.flip()
    print(con_lane_l)


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
