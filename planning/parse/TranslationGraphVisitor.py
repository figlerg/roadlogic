import os.path
import re
import warnings

from planning.intermediate_structure.Actor import Actor
from planning.intermediate_structure.SamplingHint import SamplingHint
from planning.intermediate_structure.TranslationGraph import TranslationGraph
from planning.intermediate_structure.Constraint import (RelativeConstraint, AbsoluteConstraint,
                                                       Relation, Modifier, Invariant,
                                                       StabilityInvariant, Duration)
from planning.intermediate_structure.TranslationGraph import flatten_node
from planning.parse.generated.openscenario2Visitor import openscenario2Visitor
from planning.parse.generated.openscenario2Parser import openscenario2Parser


class TranslationGraphVisitor(openscenario2Visitor):

    # Field types that declare a plain scenario parameter rather than an actor. A parameter is
    # only a name: it carries no graph member, but a keep body may refer to it to say that a
    # quantity is constant without saying what it equals.
    PARAMETER_TYPES = {"int", "uint", "float", "bool", "string", "length", "speed", "time"}

    def __init__(self):
        self.__x = None
        self._parameters = set()

    # api
    def load(self, ctx):
        self.visit(ctx)

    def visitOsc_file(self, ctx: openscenario2Parser.Osc_fileContext):
        assert len(ctx.children) == 2, "Right now, only a block with a single scenario is supported."

        out = self.visit(ctx.osc_declaration(0))
        # out.edges_to_z3()
        # Switches the edges to z3 objects... In order to pickle this, I need to wait with this till later
        return out

    def visitOsc_declaration(self, ctx: openscenario2Parser.Osc_declarationContext):

        out = self.visitChildren(ctx)
        return out

    def visitScenario_declaration(self, ctx: openscenario2Parser.Scenario_declarationContext):
        behavior_name = ctx.qualified_behavior_name()

        out = TranslationGraph()
        scenario_invariants = []

        for child in ctx.children:
            # assert isinstance(child, (openscenario2Parser.Scenario_member_declContext, openscenario2Parser.Behavior_specificationContext, antlr4.tree.Tree.TerminalNodeImpl)), 'NotImplementedError: Only actor/variable definitions and composition of behaviors is supported right now. Problem rule is {}.'.format(type(child))

            if isinstance(child, openscenario2Parser.Scenario_member_declContext):
                members = self.visit(child)

                for member in members:
                    if isinstance(member, Actor):
                        out.actors.append(member)
                    if isinstance(member, SamplingHint):
                        out.sampling_hints.append(member)
                    if isinstance(member, Invariant):
                        # A keep declared as a scenario member holds for the whole scenario,
                        # so scope stays None. See 7.3.11.2.
                        scenario_invariants.append(member)

            if isinstance(child, openscenario2Parser.Behavior_specificationContext):
                behavior_graph: TranslationGraph = self.visit(child)
                out.graph = behavior_graph.graph
                out.initial = behavior_graph.initial
                out.final = behavior_graph.final
                out.invariants = list(behavior_graph.invariants)
                out.durations = list(behavior_graph.durations)

        out.invariants = list(out.invariants) + scenario_invariants
        return out

    def visitField_declaration(self, ctx: openscenario2Parser.Field_declarationContext):
        names = self.visit(ctx.parameter_declaration())
        field_type = self.visit(ctx.parameter_declaration().type_declarator())

        
        if field_type in ['car', ]:  # write an enumerator or set the various actor types somewhere globally?
            out = []
            for name in names:
                actor = Actor(id=name, type=field_type)
                out.append(actor)

        elif field_type in ['road', 'path']:
            raise Exception(f'Passed old syntax. {field_type} is deprecated.')  # removed the path modifier
            out = []
            for name in names:
                path = SamplingHint(type=field_type, properties={'name': name, 'type': field_type})
                out.append(path)

        elif field_type in self.PARAMETER_TYPES:
            # A plain parameter. Recorded by name so a keep body can refer to it, see
            # StabilityInvariant. Nothing reaches the graph or the encoding.
            self._parameters.update(names)
            out = []

        else:
            raise NotImplementedError(f'The {field_type} variable type translation is not implemented yet!')


        return out

    def visitType_declarator(self, ctx: openscenario2Parser.Type_declaratorContext):
        # primitive_type is a bare token, so the generic visitor returns None for 'int' and
        # friends while working for a declared type name like 'car'. Read the text either way.
        return ctx.getText()

    def visitParameter_declaration(self, ctx: openscenario2Parser.Parameter_declarationContext):
        names = []
        for x in ctx.field_name():
            names.append(self.visit(x))
        return names

    def visitField_name(self, ctx: openscenario2Parser.Field_nameContext):
        return self.visit(ctx.identifier())

    def visitIdentifier(self, ctx: openscenario2Parser.IdentifierContext):
        return ctx.getText()

    def visitScenario_member_decl(self, ctx: openscenario2Parser.Scenario_member_declContext):
        return self.visitChildren(ctx)

    def visitBehavior_specification(self, ctx: openscenario2Parser.Behavior_specificationContext):
        return self.visit(ctx.do_directive())

    # kind of the top level of the behavior
    def visitDo_directive(self, ctx: openscenario2Parser.Do_directiveContext):
        return self.visit(ctx.do_member())

    # this is a node in the serial/parallel composition
    def visitDo_member(self, ctx: openscenario2Parser.Do_memberContext):
        # either a composition node or a single behavior invocation

        comp_ctx = ctx.composition()
        if comp_ctx is not None:
            return self.visit(comp_ctx)

        beh_ctx = ctx.behavior_invocation()
        if beh_ctx is not None:
            return self.visit(beh_ctx)

        # If we ever end up here, the grammar / parse tree is not what we expect
        raise NotImplementedError(
            f"do_member without composition or behavior_invocation: {ctx.getText()}"
        )


    def visitBehavior_invocation(self, ctx: openscenario2Parser.Behavior_invocationContext):
        # Parse actor and behavior name
        actor_id = self.visit(ctx.actor_expression())
        atomic_behavior = self.visit(ctx.behavior_name())

        parent = ctx.parentCtx

        # Try to get an explicit label (for composed behaviors)
        member_name = None
        if hasattr(parent, "label_name"):
            label_ctx = parent.label_name()
            if label_ctx is not None:
                member_name = label_ctx.getText()

        atomic_graph = TranslationGraph()

        # Node naming:
        # - if we have a label, use "<label>.init", "<label>.<behavior>", "<label>.fin"
        # - if there is no label (top-level atomic behavior), use global "init" / "fin"
        if member_name:
            init_node = f"{member_name}.init"
            behavior_node = f"{member_name}.{atomic_behavior}"
            fin_node = f"{member_name}.fin"
        else:
            init_node = "init"
            behavior_node = atomic_behavior
            fin_node = "fin"

        atomic_graph.add_node(init_node, initial=True)
        atomic_graph.add_node(behavior_node)
        atomic_graph.add_node(fin_node, final=True)

        # Pre- and postconditions: only if the child exists,
        # otherwise use empty sets
        bwd_ctx = ctx.behavior_with_declaration()
        if bwd_ctx is None:
            precondition, postcondition, invariants = set(), set(), set()
        else:
            precondition, postcondition, invariants = self.visit(bwd_ctx)

        atomic_graph.add_transition(init_node, behavior_node, precondition)
        atomic_graph.add_transition(behavior_node, fin_node, postcondition)

        # A keep declared here holds for the lifetime of this invocation, so it is scoped to it
        # rather than to the scenario. See 7.3.11.2.
        for invariant in invariants:
            invariant.scope = behavior_node
        atomic_graph.invariants = sorted(invariants, key=str)

        # car1.drive(duration: [30s..60s]) bounds how long this one invocation lasts
        duration = self._duration_from_arguments(ctx.argument_list(), {behavior_node},
                                                 f"the invocation {behavior_node}")
        if duration is not None:
            atomic_graph.durations = [duration]

        # Replace 'self' by actual actor id in all constraints
        atomic_graph.substitute_actor("self", actor_id)

        return atomic_graph


    def visitBehavior_with_declaration(self, ctx: openscenario2Parser.Behavior_with_declarationContext):
        # This can appear in a composition, and in a behavior_invocation.
        precondition = set()
        postcondition = set()
        invariants = set()

        for child in ctx.behavior_with_member():
            result = self.visit(child)

            # A keep in a with block yields invariants rather than a boundary constraint. They
            # hold for the lifetime of the invocation instead of at one of its ends.
            if isinstance(result, set):
                invariants.update(result)
                continue

            pre_or_post, modifier_constraints = result

            if pre_or_post == 'start':
                precondition.update(modifier_constraints)
            elif pre_or_post == 'end':
                postcondition.update(modifier_constraints)
            elif pre_or_post == 'all':
                # at: all is the invariant form, holding over the whole window rather than at one
                # phase boundary. See docs/keep-spec.md section 3.
                raise NotImplementedError(
                    "A modifier with 'at: all' is the invariant form, which is not supported yet."
                )
            elif not pre_or_post:
                pass  # In this case it is an ignored modifier, and we do nothing.
            else:
                raise NotImplementedError(f"Unexpected modifier values in: {ctx.getText()}")

        return precondition, postcondition, invariants

    def visitBehavior_with_member(self, ctx: openscenario2Parser.Behavior_with_memberContext):
        if ctx.constraint_declaration() is not None:
            return self.visit(ctx.constraint_declaration())
        if ctx.until_directive() is not None:
            raise NotImplementedError(f"until directives are not supported yet: {ctx.getText()}")
        return self.visit(ctx.modifier_application())

    # Fields a keep body may constrain, and the modifier each maps to. There is no scalar
    # position field in the domain model, so position is deliberately absent: relational
    # distance goes through space_gap instead.
    KEEP_FIELDS = {
        "lane": Modifier.LANE,
        "speed": Modifier.SPEED,
    }

    KEEP_RELATIONS = {
        "==": Relation.EQ,
        "!=": Relation.INEQ,
        "<": Relation.L,
        "<=": Relation.LEQ,
        ">": Relation.G,
        ">=": Relation.GEQ,
    }

    def visitKeep_constraint_declaration(self, ctx: openscenario2Parser.Keep_constraint_declarationContext):
        qualifier_ctx = ctx.constraint_qualifier()
        strength = qualifier_ctx.getText() if qualifier_ctx is not None else "hard"

        if strength == "default":
            raise NotImplementedError(
                "keep(default ...) is not supported yet. The override rules of 7.3.11.3 are "
                "deferred, only hard constraints are implemented. An unqualified keep is "
                "already hard."
            )

        expr_ctx = ctx.constraint_expression()
        return {inv for inv in self._build_keep_invariants(expr_ctx, strength)}

    # ---------------- keep expression parsing ----------------

    def _find_relation(self, node):
        """Descend to the single comparison in a keep body.

        A supported body is one comparison. Boolean structure such as and, or or => parses but
        is not built, so this reports what it found rather than silently taking a branch.
        """
        found = []

        def walk(n):
            if isinstance(n, openscenario2Parser.RelationContext) and n.getChildCount() == 3:
                found.append(n)
                return
            for i in range(n.getChildCount()):
                child = n.getChild(i)
                if hasattr(child, "getChildCount"):
                    walk(child)

        walk(node)

        if not found:
            raise NotImplementedError(
                f"The keep body '{node.getText()}' has no comparison. The body must be a "
                "boolean expression, for example keep(car1.lane == 2). A modifier application "
                "such as keep(lane(0)) is not a valid body."
            )
        if len(found) > 1:
            raise NotImplementedError(
                f"The keep body '{node.getText()}' has more than one comparison. Combining "
                "them with and, or or => is not supported yet. Write one keep per comparison."
            )
        return found[0]

    def _resolve_field_access(self, node):
        """Read `<actor>.<field>` out of the left-hand side. Returns (actor, field)."""
        accesses = []

        def walk(n):
            if isinstance(n, openscenario2Parser.Field_access_peContext):
                accesses.append(n)
            for i in range(n.getChildCount()):
                child = n.getChild(i)
                if hasattr(child, "getChildCount"):
                    walk(child)

        walk(node)

        if len(accesses) != 1:
            raise NotImplementedError(
                f"Expected exactly one <actor>.<field> on the left of a keep comparison, found "
                f"{len(accesses)} in '{node.getText()}'."
            )

        access = accesses[0]
        actor = access.postfix_exp().getText()
        field = access.field_name().getText()
        return actor, field

    # Distance methods the domain model declares on physical_object (8.7). Only space_gap is
    # built: it is the one that maps onto our segment model without extra machinery.
    KEEP_DISTANCE_METHODS = {
        "space_gap", "time_gap", "space_headway", "time_headway",
        "object_distance", "road_distance", "time_to_collision",
    }

    def _build_relational_invariants(self, call, relation, op, strength):
        """Build invariants from keep(a.space_gap(b, longitudinal) <rel> ...).

        The gap is signed: positive means the receiver is ahead of the reference, which is the
        convention the standard uses in its keep_space_gap semantics (8.8). So
        keep(car1.space_gap(car2, longitudinal) in [5m..100m]) says car1 runs 5m to 100m ahead
        of car2, equivalently car2 stays that far behind car1.
        """
        receiver_ctx = call.postfix_exp()
        actor, method = self._resolve_field_access(receiver_ctx)

        if method not in self.KEEP_DISTANCE_METHODS:
            raise NotImplementedError(
                f"'{method}' is not a distance method of the domain model. Known ones are "
                f"{', '.join(sorted(self.KEEP_DISTANCE_METHODS))}."
            )
        if method != "space_gap":
            raise NotImplementedError(
                f"'{method}' is declared by the standard but not built. Only space_gap is "
                "implemented, since it is the one that maps onto the segment model directly."
            )

        args = self.visit(call.argument_list()) if call.argument_list() is not None else {}

        reference = args.get(0, args.get("reference"))
        if reference is None:
            raise AssertionError(
                f"{actor}.{method}(...) needs a reference actor as its first argument."
            )

        direction = args.get(1, args.get("direction", "longitudinal"))
        if direction != "longitudinal":
            raise NotImplementedError(
                f"Direction '{direction}' is not supported. Everything in this tool is "
                "longitudinal: distance is measured in segments along the road, and the lateral "
                "axis is lane indices rather than a distance, so a lateral gap has no meaning "
                "here."
            )

        rhs = self.visit(relation.sum_exp())

        if op == "in":
            if not isinstance(rhs, (list, tuple)) or len(rhs) != 2:
                raise NotImplementedError(
                    f"The right-hand side of 'in' must be a range, got "
                    f"'{relation.sum_exp().getText()}'."
                )
            low, high = sorted(rhs)
            return {
                Invariant(RelativeConstraint(actor, reference, Modifier.POSITION,
                                             Relation.GEQ, c=low), strength),
                Invariant(RelativeConstraint(actor, reference, Modifier.POSITION,
                                             Relation.LEQ, c=high), strength),
            }

        if isinstance(rhs, (list, tuple)):
            raise NotImplementedError(
                f"A range on the right of '{op}' is not meaningful. Use 'in' for ranges."
            )
        if op not in self.KEEP_RELATIONS:
            raise NotImplementedError(f"Unsupported relational operator '{op}' in a keep body.")

        return {Invariant(RelativeConstraint(actor, reference, Modifier.POSITION,
                                             self.KEEP_RELATIONS[op], c=rhs), strength)}

    def _build_keep_invariants(self, expr_ctx, strength):
        """Turn one keep body into a set of Invariant objects."""
        relation = self._find_relation(expr_ctx)
        op = relation.relational_op().getText()

        # A method call on the left is the relational form, keep(car2.space_gap(car1, ...) ...).
        # Report that rather than letting the field check below call space_gap an unknown field.
        calls = []

        def find_calls(n):
            if isinstance(n, openscenario2Parser.Function_application_peContext):
                calls.append(n)
            for i in range(n.getChildCount()):
                child = n.getChild(i)
                if hasattr(child, "getChildCount"):
                    find_calls(child)

        find_calls(relation.relation())
        if calls:
            return self._build_relational_invariants(calls[0], relation, op, strength)

        actor, field = self._resolve_field_access(relation.relation())
        rhs = self.visit(relation.sum_exp())

        if field not in self.KEEP_FIELDS:
            supported = ", ".join(sorted(self.KEEP_FIELDS))
            raise NotImplementedError(
                f"'{field}' cannot be constrained by keep. Supported fields are {supported}. "
                f"Relational quantities such as a distance go through a method, for example "
                f"keep(car2.space_gap(car1, longitudinal) in [5m..100m])."
            )
        modifier = self.KEEP_FIELDS[field]

        # ---- constant but value free: the right-hand side names a parameter ----
        if isinstance(rhs, str):
            if op != "==":
                raise NotImplementedError(
                    f"A keep against the parameter '{rhs}' must use ==, got '{op}'. Only "
                    "equality expresses that the quantity is constant."
                )
            if rhs not in self._parameters:
                raise NotImplementedError(
                    f"'{rhs}' on the right of a keep is not a declared parameter. Declare it as "
                    f"a scenario member, for example '{rhs}: int'. Known parameters: "
                    f"{sorted(self._parameters) or 'none'}."
                )
            return {StabilityInvariant(actor, modifier, parameter=rhs, strength=strength)}

        # ---- range: keep(x in [a..b]) ----
        if op == "in":
            if not isinstance(rhs, (list, tuple)) or len(rhs) != 2:
                raise NotImplementedError(
                    f"The right-hand side of 'in' must be a range such as [5mps..10mps], got "
                    f"'{relation.sum_exp().getText()}'."
                )
            low, high = sorted(rhs)
            return {
                Invariant(AbsoluteConstraint(actor, modifier, Relation.GEQ, low), strength),
                Invariant(AbsoluteConstraint(actor, modifier, Relation.LEQ, high), strength),
            }

        if isinstance(rhs, (list, tuple)):
            raise NotImplementedError(
                f"A range on the right of '{op}' is not meaningful. Use 'in' for ranges."
            )

        # ---- plain comparison ----
        if op not in self.KEEP_RELATIONS:
            raise NotImplementedError(f"Unsupported relational operator '{op}' in a keep body.")

        return {Invariant(AbsoluteConstraint(actor, modifier, self.KEEP_RELATIONS[op], rhs),
                          strength)}

    def visitRemove_default_declaration(self, ctx: openscenario2Parser.Remove_default_declarationContext):
        raise NotImplementedError(f"remove_default is not supported yet: {ctx.getText()}")

    # def visitModifier_application(self, ctx: openscenario2Parser.Modifier_applicationContext):
    #     modifier = self.visit(ctx.modifier_name())
    #     arg_list = self.visit(ctx.argument_list())

    #     if modifier in ['position', 'lane']:
    #         start_or_end, constraints = arg_list_helper(arg_list, modifier)

    #     elif modifier == 'path':
    #         start_or_end, constraints = None, set()
    #         warnings.warn(
    #             f"The modifier {modifier} is ignored in this version of the tool, since we assume in general that the two cars have the same path.")

    #     else:
    #         start_or_end, constraints = None, set()
    #         warnings.warn(f"The {modifier} modifier is not supported yet and will be ignored.")

    #     return start_or_end, constraints

    def visitModifier_application(self, ctx: openscenario2Parser.Modifier_applicationContext):
        modifier = self.visit(ctx.modifier_name())
        # A modifier with no arguments, such as keep_lane(), has no argument_list child.
        arg_list = self.visit(ctx.argument_list()) if ctx.argument_list() is not None else {}

        if modifier in self.STABILITY_MODIFIERS:
            return self._build_stability_invariants(modifier, arg_list)

        if modifier not in ("position", "lane", "speed"):
            # Report the unsupported modifier before the 'at' check, which would otherwise
            # mask it with a confusing assertion about a missing argument.
            raise NotImplementedError(
                f"Modifier '{modifier}' not supported. Currently the position, lane and speed "
                f"modifiers are part of our implementation."
            )

        # The standard-movement-parameters define 'at' as all (default), start or end. An omitted
        # 'at', or an explicit 'at: all', means the constraint holds over the whole window rather
        # than at one phase boundary, which is the invariant form. See docs/keep-spec.md
        # section 3, where the standard defines keep_space_gap as exactly this.
        start_or_end = arg_list.get("at", "all")
        is_invariant = start_or_end == "all"


        match modifier:
            case "position":
                constraints = self._build_position_constraints(arg_list)

            case "lane":
                constraints = self._build_lane_constraints(arg_list)

            case "speed":
                constraints = self._build_speed_constraints(arg_list)

            case _:
                # Unsupported according to DSL 2.1
                raise NotImplementedError(
                    f"Modifier '{modifier}' not supported. Currently the position, lane and speed "
                f"modifiers are part of our implementation."
                )

        if is_invariant:
            # Scope is filled in by visitBehavior_invocation, which knows the invocation this
            # with block belongs to. A modifier written as a scenario member would stay None.
            return {Invariant(con) for con in constraints}

        return start_or_end, constraints
    


    # Domain model modifiers that hold one quantity of the actor for the current period, 8.9.6 and
    # 8.9.16. The standard defines keep_lane() as lane = actor.lane plus keep(actor.lane == lane),
    # so each is the same invariant as a keep against a free parameter.
    STABILITY_MODIFIERS = {
        "keep_lane": Modifier.LANE,
        "keep_speed": Modifier.SPEED,
    }

    def _build_stability_invariants(self, modifier: str, arg_list: dict) -> set:
        if arg_list:
            raise ValueError(
                f"{modifier}() takes no arguments, got {arg_list}. To fix a value, write for "
                f"example lane(2) or keep(car1.lane == 2) instead."
            )
        # 'self' is replaced by the invoking actor in visitBehavior_invocation, which also sets
        # the scope to that invocation.
        return {StabilityInvariant("self", self.STABILITY_MODIFIERS[modifier])}

    def visitBehavior_name(self, ctx: openscenario2Parser.Behavior_nameContext):
        return self.visit(ctx.identifier())

    # This is the heart of the creation of the intermediate structure. The operations can be seen in the class.
    def visitComposition(self, ctx: openscenario2Parser.CompositionContext):
        node_type = self.visit(ctx.composition_operator())

        if node_type in ['serial', 'parallel', 'one_of']:
            # I first pick the first child...
            node = self.visit(ctx.do_member(0))

            # And then add all the others (according to the rules for serial, parallel, one_of
            for child in ctx.do_member()[1:]:
                current_serial_node = self.visit(child)

                # These cannot mix, so once we are here it is either one or the other and we need not carse about
                # operator precedence. The operations are (almost) associative (the node tuples have different order,
                # but this is isomorphic.)
                # TODO might need to check this formally, but a short handwavey argument is easy to come up with

                if node_type == 'serial':
                    node = node * current_serial_node
                elif node_type == 'parallel':
                    node = node + current_serial_node
                elif node_type == 'one_of':
                    node = node % current_serial_node



        else:
            raise NotImplementedError

        # serial(duration: [10s..30s]) and friends bound the time from the start of the first
        # member to the end of the last, so the duration covers every invocation in the result.
        label_ctx = ctx.parentCtx.label_name() if hasattr(ctx.parentCtx, "label_name") else None
        source = f"{label_ctx.getText()}: {node_type}" if label_ctx is not None else node_type
        members = {label for graph_node in node.graph.nodes
                   if graph_node not in (node.initial, node.final)
                   for label in flatten_node(graph_node)}
        duration = self._duration_from_arguments(ctx.argument_list(), members, source)
        if duration is not None:
            node.durations = list(node.durations) + [duration]

        # node.draw()
        return node

    def visitComposition_operator(self, ctx: openscenario2Parser.Composition_operatorContext):
        return ctx.getText()

    def visitArgument_list(self, ctx: openscenario2Parser.Argument_listContext):
        argument_values = {}

        for i, child in enumerate(ctx.positional_argument()):
            argument_values[i] = self.visit(child)

        for child in ctx.named_argument():
            child: openscenario2Parser.Named_argumentContext
            argument_name = self.visit(child.argument_name())
            argument_value = self.visit(child.expression())

            argument_values[argument_name] = argument_value

        return argument_values

    def visitPositional_argument(self, ctx: openscenario2Parser.Positional_argumentContext):
        return self.visit(ctx.expression())

    def visitExpression(self, ctx: openscenario2Parser.ExpressionContext):
        return self.visitChildren(ctx)
    
    def visitInteger_literal(self, ctx: openscenario2Parser.Integer_literalContext):
        # lane(0, ...) -> 0
        return int(ctx.getText())

    def visitRange_constructor(self, ctx: openscenario2Parser.Range_constructorContext):
        start, end = ctx.expression()
        return (self.visit(start), self.visit(end))

    # The ASP model is integer valued: segments are metres, steps are seconds, longitudinal
    # velocity is metres per second. We therefore accept only the matching SI units and refuse
    # to convert, so a literal in a spec is the number that reaches the encoding. See section 7
    # of docs/keep-spec.md.
    SUPPORTED_UNITS = {
        "m": "length, one segment",
        "s": "time, one step",
        "mps": "speed, one segment per step",
    }

    def visitPhysical_literal(self, ctx: openscenario2Parser.Physical_literalContext):
        text = ctx.getText()  # e.g. '3s', '10m', '5mps'

        match = re.fullmatch(r"(\d+(?:\.\d+)?)([A-Za-z_][A-Za-z_0-9]*)", text)
        if match is None:
            raise ValueError(f"Could not read the physical literal '{text}'.")

        number, unit = match.group(1), match.group(2)

        if unit not in self.SUPPORTED_UNITS:
            supported = ", ".join(sorted(self.SUPPORTED_UNITS))
            raise NotImplementedError(
                f"Unit '{unit}' in the literal '{text}' is not supported. The encoding is "
                f"integer valued and does no unit conversion, so only {supported} are accepted. "
                f"Rewrite the value in those units."
            )

        value = float(number)
        if not value.is_integer():
            raise NotImplementedError(
                f"The literal '{text}' is not a whole number. The encoding is integer valued, "
                "so fractional quantities cannot be represented exactly."
            )

        return value

    # Arguments a composition or invocation may carry. The standard also gives parallel the
    # overlap, start_to_start and end_to_end parameters, which are not supported.
    TIMING_ARGUMENTS = {"duration"}

    def _physical_units(self, ctx):
        """Units of every physical literal inside an expression, for example {"s"} for [3s..20s]."""
        units = set()

        def walk(node):
            if isinstance(node, openscenario2Parser.Physical_literalContext):
                match = re.fullmatch(r"\d+(?:\.\d+)?([A-Za-z_][A-Za-z_0-9]*)", node.getText())
                units.add(match.group(1) if match else node.getText())
            for i in range(node.getChildCount()):
                child = node.getChild(i)
                if hasattr(child, "getChildCount"):
                    walk(child)

        walk(ctx)
        return units

    def _duration_from_arguments(self, arg_ctx, labels, source):
        """Read the duration argument of a composition or invocation, if it has one.

        Returns a Duration or None. Any other argument is rejected rather than ignored.
        """
        if arg_ctx is None:
            return None
        if arg_ctx.positional_argument():
            raise NotImplementedError(
                f"Positional arguments are not supported on {source}: '{arg_ctx.getText()}'. "
                "Write duration: [3s..20s]."
            )

        named = {self.visit(arg.argument_name()): arg.expression() for arg in arg_ctx.named_argument()}
        unsupported = sorted(set(named) - self.TIMING_ARGUMENTS)
        if unsupported:
            raise NotImplementedError(
                f"The argument(s) {', '.join(unsupported)} of {source} are not supported. "
                "Only duration is."
            )
        if "duration" not in named:
            return None

        expr = named["duration"]
        if self._physical_units(expr) != {"s"}:
            raise ValueError(
                f"The duration of {source} is '{expr.getText()}'. A duration is a time and has to "
                "be given in s, for example duration: [3s..20s]."
            )
        value = self.visit(expr)
        low, high = sorted(value) if isinstance(value, (list, tuple)) else (value, value)
        return Duration(labels, int(low), int(high), source)

    # helpers for constraints
    def _build_lane_constraints(self, arg_list: dict) -> set:
        """
        Build constraints for the 'lane' modifier.

        Supports:
        - Relative:
            lane(same_as: other, at: ...)
            lane(left_of: other, at: ...)
            lane(right_of: other, at: ...)
            lane(side_of: other, side: left/right, at: ...)   # mapped to left_of/right_of
        - Absolute:
            lane(1, at: ...)
            lane(lane: 1, at: ...)
        """
        # --- compatibility shim for new OSC DSL syntax: lane(side_of: X, side: left/right) ---
        if "side_of" in arg_list and "side" in arg_list:
            target = arg_list["side_of"]
            side = str(arg_list["side"]).lower()

            if side == "left":
                arg_list["left_of"] = target
            elif side == "right":
                arg_list["right_of"] = target
            else:
                raise NotImplementedError(
                    f"Unsupported side value '{arg_list['side']}' in lane(side_of:..., side:...)."
                )

        relative_keys = {"same_as", "left_of", "right_of"}
        present_rel = relative_keys.intersection(arg_list.keys())

        if len(present_rel) > 1:
            raise AssertionError(
                f"'lane' modifier may have at most one of {relative_keys}, got {present_rel}."
            )

        # ---------- RELATIVE CASE ----------
        if present_rel:
            key = next(iter(present_rel))
            relative_actor = arg_list[key]

            match key:
                case "same_as":
                    con = RelativeConstraint("self", relative_actor, Modifier.LANE, Relation.EQ)
                case "left_of":
                    con = RelativeConstraint("self", relative_actor, Modifier.LANE, Relation.L)
                case "right_of":
                    con = RelativeConstraint("self", relative_actor, Modifier.LANE, Relation.G)
                case _:
                    raise NotImplementedError(f"Unexpected lane relation key: {key}")

            return {con}

        # ---------- ABSOLUTE CASE ----------
        if 0 in arg_list:
            lane_value = arg_list[0]
        elif "lane" in arg_list:
            lane_value = arg_list["lane"]
        else:
            raise AssertionError(
                "Absolute 'lane' requires a positional argument (index 0) "
                "or a named 'lane' argument."
            )

        # basic sanity check – helps catch parsing issues
        if lane_value is None:
            raise AssertionError(
                "Lane value for absolute 'lane' parsed as None. "
                "Check literal visitors / argument_list parsing."
            )

        con = AbsoluteConstraint("self", Modifier.LANE, Relation.EQ, lane_value)
        return {con}



    def _build_speed_constraints(self, arg_list: dict) -> set:
        """
        Build constraints for the 'speed' modifier.

        Supports the absolute forms, where the value is a longitudinal velocity in mps,
        which is one segment per step in the encoding:

            speed(5mps, at: ...)
            speed(speed: 5mps, at: ...)
            speed([5mps..10mps], at: ...)
            speed(speed_range: [5mps..10mps], at: ...)

        And the relative forms, which compare Vel_lon of two actors at the same step:

            speed(faster_than: car2, at: ...)
            speed(slower_than: car2, at: ...)
            speed(same_as: car2, at: ...)
        """
        relative_keys = {"faster_than", "slower_than", "same_as"}
        present_rel = relative_keys.intersection(arg_list.keys())

        if len(present_rel) > 1:
            raise AssertionError(
                f"'speed' modifier may have at most one of {relative_keys}, got {present_rel}."
            )

        if present_rel:
            key = next(iter(present_rel))
            other = arg_list[key]

            match key:
                case "faster_than":
                    con = RelativeConstraint("self", other, Modifier.SPEED, Relation.G)
                case "slower_than":
                    con = RelativeConstraint("self", other, Modifier.SPEED, Relation.L)
                case "same_as":
                    con = RelativeConstraint("self", other, Modifier.SPEED, Relation.EQ)
                case _:
                    raise NotImplementedError(f"Unexpected speed relation key: {key}")

            return {con}

        for unsupported in ("direction", "factor"):
            if unsupported in arg_list:
                raise NotImplementedError(
                    f"The '{unsupported}' argument of the speed modifier is not supported yet."
                )

        if 0 in arg_list:
            value = arg_list[0]
        elif "speed" in arg_list:
            value = arg_list["speed"]
        elif "speed_range" in arg_list:
            value = arg_list["speed_range"]
        else:
            raise AssertionError(
                "The 'speed' modifier requires a positional argument (index 0) or a named "
                "'speed' or 'speed_range' argument."
            )

        if value is None:
            raise AssertionError(
                "Speed value parsed as None. Check literal visitors / argument_list parsing."
            )

        # Interval [low, high]
        if isinstance(value, (list, tuple)) and len(value) == 2:
            low, high = value
            con1 = AbsoluteConstraint("self", Modifier.SPEED, Relation.GEQ, low)
            con2 = AbsoluteConstraint("self", Modifier.SPEED, Relation.LEQ, high)
            return {con1, con2}

        con = AbsoluteConstraint("self", Modifier.SPEED, Relation.EQ, value)
        return {con}


    def _build_position_constraints(self, arg_list: dict) -> set:
        """
        Build constraints for the 'position' modifier.

        Supports:
        - Relative:
            position([a,b], ahead_of: actor, at: ...)
            position([a,b], behind: actor, at: ...)
        - Absolute:
            position([a,b], at: ...)
            position(12, at: ...)
        """
        relative_keys = {"ahead_of", "behind"}
        present_rel = relative_keys.intersection(arg_list.keys())

        if len(present_rel) > 1:
            raise AssertionError(
                f"'position' modifier may have at most one of {relative_keys}, got {present_rel}."
            )

        # ---------- RELATIVE CASE ----------
        if present_rel:
            key = next(iter(present_rel))

            if 0 not in arg_list:
                raise AssertionError(
                    "Relative 'position' requires an interval as positional argument (index 0)."
                )

            interval = arg_list[0]
            if not (isinstance(interval, (list, tuple)) and len(interval) == 2):
                raise AssertionError(
                    "Relative 'position' interval must be a 2-element list/tuple [low, high]."
                )

            low, high = interval
            relative_actor = arg_list[key]

            if key == "ahead_of":
                # self ∈ [other + low, other + high]
                con1 = RelativeConstraint(
                    "self", relative_actor, Modifier.POSITION, Relation.LEQ, c=high
                )
                con2 = RelativeConstraint(
                    "self", relative_actor, Modifier.POSITION, Relation.GEQ, c=low
                )
            elif key == "behind":
                # self ∈ [other - high, other - low]
                con1 = RelativeConstraint(
                    "self", relative_actor, Modifier.POSITION, Relation.LEQ, c=-low
                )
                con2 = RelativeConstraint(
                    "self", relative_actor, Modifier.POSITION, Relation.GEQ, c=-high
                )
            else:
                raise NotImplementedError(f"Unexpected relative position key: {key}")

            con1.match(con2)
            return {con1, con2}

        # ---------- ABSOLUTE CASE ----------
        if 0 in arg_list:
            value = arg_list[0]
        elif "position" in arg_list:
            value = arg_list["position"]
        else:
            raise AssertionError(
                "Absolute 'position' requires a positional argument (index 0) "
                "or a named 'position' argument."
            )

        # Interval [low, high]
        if isinstance(value, (list, tuple)) and len(value) == 2:
            low, high = value
            con1 = AbsoluteConstraint("self", Modifier.POSITION, Relation.GEQ, low)
            con2 = AbsoluteConstraint("self", Modifier.POSITION, Relation.LEQ, high)
            return {con1, con2}

        # Single value
        con = AbsoluteConstraint("self", Modifier.POSITION, Relation.EQ, value)
        return {con}


# def arg_list_helper(arg_list: dict, modifier):
#     # I assume there is both an 'at' and some positional argument in there
#     # ('ahead_of', 'behind', same_as, left_of, right_of).

#     assert 'at' in arg_list.keys(), "Please specify an 'at' argument for position and lane modifiers."
#     start_or_end = arg_list['at']

#     allowed_positional_keywords = {'ahead_of', 'behind', 'same_as', 'left_of', 'right_of'}
#     assert (len(allowed_positional_keywords.intersection(set(arg_list.keys()))) == 1), \
#         f"Positional modifiers such as '{modifier}' need exactly one of {allowed_positional_keywords} in the argument list."

#     keys = arg_list.keys()

#     if modifier == 'position':
#         assert 0 in arg_list.keys(), "Need an interval as positional argument in modifier declaration."
#         interval = arg_list[0]

#         if 'ahead_of' in keys:
#             relative_actor = arg_list['ahead_of']

#             con1 = RelativeConstraint('self', relative_actor, Modifier.POSITION, Relation.LEQ, c=interval[1])
#             con2 = RelativeConstraint('self', relative_actor, Modifier.POSITION, Relation.GEQ, c=interval[0])

#             con1.match(con2) # saves pointer for partner in both constraints

#             constraints = {con1, con2}

#         elif 'behind' in keys:
#             relative_actor = arg_list['behind']

#             con1 = RelativeConstraint('self', relative_actor, Modifier.POSITION, Relation.LEQ, c=-interval[0])
#             con2 = RelativeConstraint('self', relative_actor, Modifier.POSITION, Relation.GEQ, c=-interval[1])

#             con1.match(con2) # saves pointer for partner in both constraints

#             constraints = {con1, con2}

#         else:
#             raise NotImplementedError(f"Modifier {modifier} needs an argument 'behind' or 'ahead_of' another actor.")

#     if modifier == 'lane':

#         if 'same_as' in keys:
#             relative_actor = arg_list['same_as']

#             con1 = RelativeConstraint('self', relative_actor, Modifier.LANE, Relation.EQ)

#             constraints = {con1}

#         elif 'left_of' in keys:
#             relative_actor = arg_list['left_of']

#             con1 = RelativeConstraint('self', relative_actor, Modifier.LANE, Relation.L)

#             constraints = {con1}

#         elif 'right_of' in keys:
#             relative_actor = arg_list['right_of']

#             con1 = RelativeConstraint('self', relative_actor, Modifier.LANE, Relation.G)

#             constraints = {con1}

#         else:
#             raise NotImplementedError(
#                 f"Modifier {modifier} needs an argument 'same_as', 'left_of', 'right_of' another actor.")

#     return start_or_end, constraints


if __name__ == '__main__':
    # Some tests. Refer to parse_script.py in top directory for example usage.

    from antlr4 import *
    from planning.parse.generated.openscenario2Lexer import openscenario2Lexer
    from planning.parse.generated.openscenario2Parser import openscenario2Parser

    # from shapex.parse import HardSyntaxErrorStrategy # TODO is the syntax error already 'hard'? otherwise copy code from shapex

    testin_file = os.path.join(os.curdir, 'experiments_src/exp_003_b/in/spec.osc')
    testout_file = os.path.join(os.curdir, 'testout.scenic')

    input_stream = FileStream(testin_file)
    lexer = openscenario2Lexer(input_stream)
    stream = CommonTokenStream(lexer)
    parser = openscenario2Parser(stream)
    # parser._errHandler = HardSyntaxErrorStrategy()
    ctx = parser.osc_file()

    visitor = TranslationGraphVisitor()
    translation_graph: TranslationGraph = visitor.visit(ctx)

    print(input_stream)
    print('\n TRANSLATES TO: \n')
    print(translation_graph)

    translation_graph.draw()


