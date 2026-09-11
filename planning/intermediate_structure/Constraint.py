from enum import Enum
from abc import ABC, abstractmethod

# from z3 import Int, Real, simplify, And



from abc import ABC, abstractmethod
from typing import Dict, Tuple, List



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

    def __hash__(self):
        # Defining __eq__ on a class drops the inherited __hash__, which would make these
        # unusable as dict keys or set members. Hash on the same value __eq__ compares.
        return hash(str(self))

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
    # Longitudinal velocity, Vel_lon in the ASP state. Deliberately not 'p' or 'l': the
    # groundability checks in Planner.create_asp_instance test those two literals to decide
    # whether an actor is pinned down, and speed must not count towards that.
    SPEED = 'v'

    def __str__(self):
        if self._name_ == 'LANE':
            return 'l'
        if self._name_ == 'POSITION':
            return 'p'
        if self._name_ == 'SPEED':
            return 'v'

    def __eq__(self, other):
        return str(self) == str(other)

    def __hash__(self):
        return hash(str(self))



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
    
    @abstractmethod  # maybe needed because sometimes I use sets and don't want double constraints
    def __eq__(self) -> bool:
        raise NotImplementedError
    
    @abstractmethod
    def asp_goal_format(self, indices) -> str:
        raise NotImplementedError
    
    def is_relative(self) -> bool:
        return False

    def is_absolute(self) -> bool:
        return False
    

    @property
    def interval_partner(self):
        return self._interval_partner
    
    def match(self, other):
        # matches this constraint to another constraint. Is invoked if both are created from a position interval.
        # makes bookkeeping easier

        self._interval_partner = other
        other._interval_partner = self

    @property
    def relation(self):
        return self._relation

    @relation.setter
    def relation(self, value):
        self._relation = value

    @property
    def modifier(self):
        return self._modifier

    @modifier.setter
    def modifier(self, value):
        self._modifier = value




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

        self._interval_partner = None


    @property
    def actor(self) -> str:
        return self._actor
    
    @actor.setter
    def actor(self, value):
        self._actor = value

    @property
    def value(self) -> float:
        return self._value

    @property
    def exp(self)-> str:
        if self.modifier == Modifier.POSITION:
            out = f"p({self.actor})"
        elif self.modifier == Modifier.LANE:
            out = f"l({self.actor})"
        else:
            raise NotImplementedError(f"Unsupported modifier in AbsoluteConstraint: {self.modifier}")

        return out

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
    
    def __hash__(self):
        return hash(repr(sorted(self.__dict__.items())))
    
    def __eq__(self, other):

        if type(other) is not type(self):
            return False

        # normally I would just compare dict, but this leads to an infinite recursion because the __interval_partner
        #  is also a constraint. So I need to compare dict by hand and cast the object to str before comparing.

        dict1_without_interval_partner = {k: v for k, v in self.__dict__.items() if
                                          k != '_Constraint__interval_partner'}
        dict2_without_interval_partner = {k: v for k, v in other.__dict__.items() if
                                          k != '_Constraint__interval_partner'}

        if dict1_without_interval_partner == dict2_without_interval_partner:
            return True


    def asp_goal_format(self, indices) -> List[str]:
        """
        Return a list of ASP atoms encoding this absolute constraint.

        Parameters
        ----------
        indices : dict[str, int]
            Mapping from actor name to integer index used in the ASP state
            variables (e.g. ego -> 0 so that we use L0, S0, ...).

        Returns
        -------
        list[str]
            List of strings representing ASP atoms.
        """
        actor = str(self.actor)
        if actor not in indices:
            raise KeyError(
                f"Actor '{actor}' not found in indices passed to asp_goal_format."
            )

        i = indices[actor]
        goal_atoms: list[str] = []

        # lane vs position
        if self.modifier == Modifier.LANE:
            var = f"L{i}"

            partner = getattr(self, "interval_partner", None)
            if partner is not None:
                # If you ever support lane intervals, you could handle them here.
                raise NotImplementedError(
                    "Lane intervals for AbsoluteConstraint not supported."
                )

            rel = self.relation
            val = self.value

            # make lane values pretty (int) if they are integral floats
            if isinstance(val, float) and val.is_integer():
                val = int(val)

            if rel == Relation.EQ:
                op = "="
            elif rel in (Relation.L, Relation.G, Relation.LEQ, Relation.GEQ, Relation.INEQ):
                op = rel.value  # '<', '>', '<=', '>=', '!='
            else:
                raise NotImplementedError(
                    f"Unexpected relation in AbsoluteConstraint (lane): {rel}"
                )

            goal_atoms.append(f"{var} {op} {val}")
            return goal_atoms

        elif self.modifier == Modifier.POSITION:
            var = f"S{i}"
            partner = getattr(self, "interval_partner", None)

            # ----- interval case: two AbsoluteConstraints paired via interval_partner -----
            if partner is not None:
                v1 = self.value
                v2 = partner.value

                # normalize to integers where appropriate
                vals = []
                for v in (v1, v2):
                    if isinstance(v, float) and v.is_integer():
                        v = int(v)
                    vals.append(v)

                low, high = sorted(vals)
                goal_atoms.append(f"{low} <= {var} <= {high}")
                return goal_atoms

            # ----- non-interval / single inequality case -----
            rel = self.relation
            val = self.value
            if isinstance(val, float) and val.is_integer():
                val = int(val)

            if rel == Relation.EQ:
                op = "="
            elif rel in (Relation.L, Relation.G, Relation.LEQ, Relation.GEQ, Relation.INEQ):
                op = rel.value
            else:
                raise NotImplementedError(
                    f"Unexpected relation in AbsoluteConstraint (position): {rel}"
                )

            goal_atoms.append(f"{var} {op} {val}")
            return goal_atoms

        elif self.modifier == Modifier.SPEED:
            var = f"V{i}"
            partner = getattr(self, "interval_partner", None)

            # ----- interval case: speed([a..b], at: ...) -----
            if partner is not None:
                vals = []
                for v in (self.value, partner.value):
                    if isinstance(v, float) and v.is_integer():
                        v = int(v)
                    vals.append(v)

                low, high = sorted(vals)
                goal_atoms.append(f"{low} <= {var} <= {high}")
                return goal_atoms

            # ----- single value or inequality -----
            rel = self.relation
            val = self.value
            if isinstance(val, float) and val.is_integer():
                val = int(val)

            if rel == Relation.EQ:
                op = "="
            elif rel in (Relation.L, Relation.G, Relation.LEQ, Relation.GEQ, Relation.INEQ):
                op = rel.value
            else:
                raise NotImplementedError(
                    f"Unexpected relation in AbsoluteConstraint (speed): {rel}"
                )

            goal_atoms.append(f"{var} {op} {val}")
            return goal_atoms

        else:
            raise NotImplementedError(
                f"Unsupported modifier in AbsoluteConstraint.asp_goal_format: {self.modifier}"
            )



    



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
        self._actor_1 = actor_1
        self._actor_2 = actor_2
        self._modifier = modifier
        self._relation = relation
        self._c = c

        # added: I want to keep a pointer for the other part of the interval in case of position intervals
        self._interval_partner = None

    @property
    def c(self):
        return self._c

    @property
    def actor_1(self):
        return self._actor_1

    @actor_1.setter
    def actor_1(self, value):
        self._actor_1 = value

    @property
    def actor_2(self):
        return self._actor_2

    @actor_2.setter
    def actor_2(self, value):
        self._actor_2 = value

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
        actor_1_decorated = f"{self._modifier}_{self._actor_1}"
        actor_2_decorated = f"{self._modifier}_{self._actor_2}"

        out = f"{actor_1_decorated} {self._relation} {actor_2_decorated}"

        if self._c > 0:
            out += f" + {self._c}"
        elif self._c < 0:
            out += f" {self._c}"

        return out

    def __repr__(self):
        return str(self)

    def __hash__(self):
        return hash(repr(sorted(self.__dict__.items())))

    def __eq__(self, other):

        if type(other) is not type(self):
            return False

        # normally I would just compare dict, but this leads to an infinite recursion because the __interval_partner
        #  is also a constraint. So I need to compare dict by hand and cast the object to str before comparing.

        dict1_without_interval_partner = {k: v for k, v in self.__dict__.items() if
                                          k != '_Constraint__interval_partner'}
        dict2_without_interval_partner = {k: v for k, v in other.__dict__.items() if
                                          k != '_Constraint__interval_partner'}

        if dict1_without_interval_partner == dict2_without_interval_partner:
            return True

        # there's a second way for the constraints to be equal: namely if they are flipped
        if self._relation == Relation.EQ or self._relation == Relation.INEQ:
            a1 = self._actor_1
            b1 = self._actor_2
            a2 = other._actor_1
            b2 = other._actor_2

            c1 = self._c
            c2 = other._c

            # Once we are in this case, the only way the two objects can encode the same constraint is when the two
            # sides are flipped and c is moved to the other side.
            return (a1 == b2) and (a2 == b1) and (c1 == -c2)

        # As long as we don't allow products with l(x) or p(x), all other combinations are surely not the same:
        # The above cases were symmetric, the inequalities are antisymmetric. Thus, we can enforce a cononical position
        #  for the constant c (on the right hand side of the relation w.r. to the actor numbers).
        else:
            return False


    def asp_goal_format(self, indices):
        # All the constraints are relational constraints between two actors. In the end I want something like this:
        # goal1(T,t) :- time(T,t), query(t), T<=t, holds(state(car1,loc(L1,S1),dyn(Vel1,0)), T), holds(state(ego,loc(L,S),dyn(Vel,0)), T), L < L1.

        # But it could also have multiple constraints for the same actor pair. So I do the part
        # "goal1(T,t) :- time(T,t), query(t), T<=t, holds(state(car1,loc(L1,S1),dyn(Vel1,0)), T), holds(state(ego,loc(L,S),dyn(Vel,0)), T)"
        #  outside and add only some atoms here which encode the relation.

        actor1 = str(self._actor_1)
        actor2 = str(self._actor_2)

        goal_atoms = []

        i1 = indices[actor1]
        i2 = indices[actor2]

        if self._modifier == Modifier.LANE:
            if self._relation == Relation.L:
                goal_atoms.append(f"L{i1} < L{i2}")
            elif self._relation == Relation.G:
                goal_atoms.append(f"L{i1} > L{i2}")
            elif self._relation == Relation.EQ:
                goal_atoms.append(f"L{i1} = L{i2}")
            else:
                raise NotImplementedError

        elif self._modifier == Modifier.SPEED:
            # speed(faster_than: other) and friends. Compares Vel_lon of the two actors at the
            # same step, so it needs both velocity variables bound in the surrounding rule.
            if self._relation == Relation.G:
                goal_atoms.append(f"V{i1} > V{i2}")
            elif self._relation == Relation.L:
                goal_atoms.append(f"V{i1} < V{i2}")
            elif self._relation == Relation.EQ:
                goal_atoms.append(f"V{i1} = V{i2}")
            else:
                raise NotImplementedError(
                    f"Unexpected relation in RelativeConstraint (speed): {self._relation}"
                )

        elif self._modifier == Modifier.POSITION:
            partner = self._interval_partner
            cs = [self._c, partner._c]
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
        return f"{self._modifier}({self._actor_1})"

    @property
    def exp2(self):
        return f"{self._modifier}({self._actor_2})"


    def flip(self):
        # rewrite "p(actor2) R p(actor1) + c" as "p(actor) R' p(actor2) -c"
        self._actor_1, self._actor_2 = self.actor_2, self._actor_1
        self._c *= -1

        new_rel = self._relation.flipped

        self._relation = None
        self._relation = new_rel

    def standardize(self):
        actors = [self._actor_1, self._actor_2]
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

        if self._modifier != other._modifier:
            return False

        self.standardize()  # Beware, this happens in place
        other.standardize()

        if self._actor_1 == other._actor_1 and self._actor_2 == other._actor_2:
            smaller_rels = [Relation.L, Relation.LEQ]
            greater_rels = [Relation.G, Relation.GEQ]

            if self._relation in smaller_rels and other._relation in smaller_rels:
                if self._c < other._c:
                    return True
                if self._relation == Relation.L:
                    # This differs between lesser and lesser-equal. This case means that self is stricter.
                    return True

            # a > b + c1, a > b + c2, if c2 is greater the constraint is tighter
            if self._relation in greater_rels and other._relation in greater_rels:
                if self._c > other._c:
                    return True
                if self._relation == Relation.G:
                    return True

        return False





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


class Invariant:
    """A `keep` constraint: it must hold at every step inside its window.

    This is deliberately a separate kind from `AbsoluteConstraint` and `RelativeConstraint`,
    which are point constraints. Those are folded into a single `goal_i(t)` rule and are
    required to hold at one solver-chosen step. An invariant instead becomes a standalone
    integrity constraint, so it needs its own type rather than a flag. See section 5 of
    docs/keep-spec.md.

    The payload is an ordinary constraint, so the relational case reuses everything
    `RelativeConstraint` already knows about emitting itself. `Invariant` adds the window and
    the emission site.

    Attributes
    ----------
    constraint : BaseConstraint
        What must hold. Absolute or relative.
    strength : str
        'hard' or 'default'. Only 'hard' is supported. An unqualified keep is hard per 7.3.11.3.
    scope : object
        None means the whole scenario. Anything else identifies the behavior invocation whose
        lifetime bounds the window. Phase scoping is not implemented, see DECIDE 3 in the spec,
        so this is currently recorded but not acted on.
    """

    def __init__(self, constraint: 'BaseConstraint', strength: str = 'hard', scope=None):
        if strength not in ('hard', 'default'):
            raise ValueError(f"Unknown constraint strength '{strength}'.")
        self.constraint = constraint
        self.strength = strength
        self.scope = scope

    @property
    def actors(self):
        """Every actor this invariant talks about."""
        c = self.constraint
        if isinstance(c, RelativeConstraint):
            return {c.actor_1, c.actor_2}
        return {c.actor}

    @property
    def modifier(self):
        return self.constraint.modifier

    def substitute_actor(self, original_name, new_name):
        # Constraints carry their actor as a plain attribute rather than offering a method,
        # matching how TranslationGraph.substitute_actor rewrites edge constraints.
        c = self.constraint
        if isinstance(c, RelativeConstraint):
            if c.actor_1 == original_name:
                c.actor_1 = new_name
            if c.actor_2 == original_name:
                c.actor_2 = new_name
        elif isinstance(c, AbsoluteConstraint):
            if c.actor == original_name:
                c.actor = new_name

    # An invariant is emitted as an integrity constraint, which forbids the states that break
    # it, so each relation is written as its negation.
    FORBIDDEN = {
        Relation.EQ: '!=',
        Relation.INEQ: '=',
        Relation.L: '>=',
        Relation.LEQ: '>',
        Relation.G: '<=',
        Relation.GEQ: '<',
    }

    # Which slot of the state atom each modifier reads.
    STATE_SLOT = {
        Modifier.LANE: 'loc(_,{var})), dyn(_,_)',
        Modifier.POSITION: 'loc({var},_)), dyn(_,_)',
        Modifier.SPEED: 'loc(_,_)), dyn({var},_)',
    }

    @staticmethod
    def _holds(actor, modifier, var, step='t'):
        """One holds atom with a variable bound in the slot the modifier reads."""
        if modifier == Modifier.LANE:
            body = f"loc(_,{var}), dyn(_,_)"
        elif modifier == Modifier.POSITION:
            body = f"loc({var},_), dyn(_,_)"
        elif modifier == Modifier.SPEED:
            body = f"loc(_,_), dyn({var},_)"
        else:
            raise NotImplementedError(f"No state slot for modifier {modifier}.")
        return f"holds(state({actor}, {body}), {step})"

    # True when breaking the invariant can be seen at one step on its own. A stability keep
    # compares two consecutive steps, so it overrides this.
    checks_single_step = True

    def asp_violation_bodies(self):
        """Rule bodies for `#program check(t)` that hold exactly when the invariant is broken at t.

        A keep for the whole scenario turns each into an integrity constraint. A keep inside a
        behavior invocation turns each into keep_broken(i,t), see Planner._invocation_keep_rules.
        """
        c = self.constraint

        if isinstance(c, AbsoluteConstraint):
            value = c.value
            if isinstance(value, float) and value.is_integer():
                value = int(value)

            op = self.FORBIDDEN.get(c.relation)
            if op is None:
                raise NotImplementedError(f"Cannot negate relation {c.relation} for an invariant.")

            var = 'X'
            return [f"{self._holds(c.actor, c.modifier, var)}, {var} {op} {value}"]

        if isinstance(c, RelativeConstraint):
            op = self.FORBIDDEN.get(c.relation)
            if op is None:
                raise NotImplementedError(f"Cannot negate relation {c.relation} for an invariant.")
            offset = ''
            if c.c:
                offset_value = int(c.c) if isinstance(c.c, float) and float(c.c).is_integer() else c.c
                offset = f" + {offset_value}" if offset_value >= 0 else f" - {abs(offset_value)}"
            return [
                f"{self._holds(c.actor_1, c.modifier, 'X1')}, "
                f"{self._holds(c.actor_2, c.modifier, 'X2')}, X1 {op} X2{offset}"
            ]

        raise NotImplementedError(f"Cannot encode an invariant over {type(c).__name__}.")

    def asp_integrity_rules(self):
        """ASP integrity constraints forbidding any step that breaks this invariant.

        Only for a keep that holds for the whole scenario. Returned as rule strings for
        `#program check(t)`, so each is instantiated per step.
        """
        if self.scope is not None:
            raise NotImplementedError(
                f"{self} is scoped to the invocation {self.scope}. Such keeps are encoded through "
                "the goal rule by Planner._invocation_keep_rules, not as standalone constraints."
            )
        return [f":- {body}." for body in self.asp_violation_bodies()]

    def __str__(self):
        where = 'scenario' if self.scope is None else str(self.scope)
        qualifier = '' if self.strength == 'hard' else f'{self.strength} '
        return f"keep[{where}]({qualifier}{self.constraint})"

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return isinstance(other, Invariant) and str(self) == str(other)

    def __hash__(self):
        return hash(str(self))


class StabilityInvariant(Invariant):
    """`keep(actor.field == some_parameter)`: the quantity never changes, value unspecified.

    The parameter is a plain scenario parameter, not a keyword. Because a parameter holds one
    value for the lifetime of its instance, equating a quantity to it says the quantity is
    constant without saying what it equals. This is how the domain model defines `keep_lane()`,
    as `lane = actor.lane` plus `keep(actor.lane == lane)`.

    The parameter never reaches ASP. The meaning is compiled directly as a step-to-step
    stability constraint, which is why this cannot be expressed as an ordinary constraint with
    a value and needs its own type.
    """

    def __init__(self, actor: str, modifier: 'Modifier', parameter: str = None,
                 strength: str = 'hard', scope=None):
        self._actor = actor
        self._modifier = modifier
        self.parameter = parameter
        if strength not in ('hard', 'default'):
            raise ValueError(f"Unknown constraint strength '{strength}'.")
        self.constraint = None
        self.strength = strength
        self.scope = scope

    @property
    def actors(self):
        return {self._actor}

    @property
    def actor(self):
        return self._actor

    @property
    def modifier(self):
        return self._modifier

    def substitute_actor(self, original_name, new_name):
        if self._actor == original_name:
            self._actor = new_name

    checks_single_step = False

    def asp_violation_bodies(self):
        """Broken at t when the quantity differs from the step before.

        The parameter never reaches ASP. Equality to a parameter means the quantity holds one
        value for the lifetime of the instance, which is exactly step-to-step stability.
        """
        return [
            f"{Invariant._holds(self._actor, self._modifier, 'X1')}, "
            f"{Invariant._holds(self._actor, self._modifier, 'X2', 't-1')}, "
            f"time(t-1), X1 != X2"
        ]

    def asp_integrity_rules(self):
        """Forbid the quantity changing between consecutive steps, for a scenario-wide keep."""
        if self.scope is not None:
            raise NotImplementedError(
                f"{self} is scoped to the invocation {self.scope}. Such keeps are encoded through "
                "the goal rule by Planner._invocation_keep_rules, not as standalone constraints."
            )
        return [f":- {body}." for body in self.asp_violation_bodies()]

    def __str__(self):
        where = 'scenario' if self.scope is None else str(self.scope)
        param = self.parameter or '<free>'
        return f"keep[{where}]({self._actor}.{self._modifier} == {param}, constant)"
