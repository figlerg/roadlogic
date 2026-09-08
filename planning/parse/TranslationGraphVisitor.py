import os.path
import re
import warnings

from planning.intermediate_structure.Actor import Actor
from planning.intermediate_structure.SamplingHint import SamplingHint
from planning.intermediate_structure.TranslationGraph import TranslationGraph
from planning.intermediate_structure.Constraint import RelativeConstraint, AbsoluteConstraint, Relation, Modifier
from planning.parse.generated.openscenario2Visitor import openscenario2Visitor
from planning.parse.generated.openscenario2Parser import openscenario2Parser


class TranslationGraphVisitor(openscenario2Visitor):

    def __init__(self):
        self.__x = None

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

        for child in ctx.children:
            # assert isinstance(child, (openscenario2Parser.Scenario_member_declContext, openscenario2Parser.Behavior_specificationContext, antlr4.tree.Tree.TerminalNodeImpl)), 'NotImplementedError: Only actor/variable definitions and composition of behaviors is supported right now. Problem rule is {}.'.format(type(child))

            if isinstance(child, openscenario2Parser.Scenario_member_declContext):
                members = self.visit(child)

                for member in members:
                    if isinstance(member, Actor):
                        out.actors.append(member)
                    if isinstance(member, SamplingHint):
                        out.sampling_hints.append(member)

            if isinstance(child, openscenario2Parser.Behavior_specificationContext):
                behavior_graph: TranslationGraph = self.visit(child)
                out.graph = behavior_graph.graph
                out.initial = behavior_graph.initial
                out.final = behavior_graph.final

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

        else:
            raise NotImplementedError(f'The {field_type} variable type translation is not implemented yet!')


        return out

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
            precondition, postcondition = set(), set()
        else:
            precondition, postcondition = self.visit(bwd_ctx)

        atomic_graph.add_transition(init_node, behavior_node, precondition)
        atomic_graph.add_transition(behavior_node, fin_node, postcondition)

        # Replace 'self' by actual actor id in all constraints
        atomic_graph.substitute_actor("self", actor_id)

        return atomic_graph


    def visitBehavior_with_declaration(self, ctx: openscenario2Parser.Behavior_with_declarationContext):
        # This can appear in a composition, and in a behavior_invocation.
        precondition = set()
        postcondition = set()

        for child in ctx.behavior_with_member():
            pre_or_post, modifier_constraints = self.visit(child)

            if pre_or_post == 'start':
                precondition.update(modifier_constraints)
            elif pre_or_post == 'end':
                postcondition.update(modifier_constraints)
            elif not pre_or_post:
                pass  # In this case it is an ignored modifier, and we do nothing.
            else:
                raise NotImplementedError(f"Unexpected modifier values in: {ctx.getText()}")

        return precondition, postcondition

    def visitBehavior_with_member(self, ctx: openscenario2Parser.Behavior_with_memberContext):
        return self.visit(ctx.modifier_application())

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

        if modifier not in ("position", "lane"):
            # Report the unsupported modifier before the 'at' check, which would otherwise
            # mask it with a confusing assertion about a missing argument.
            raise NotImplementedError(
                f"Modifier '{modifier}' not supported. Currently the position and lane modifiers are part of our implementation."
            )

        # All modifiers in the DSL support 'at'
        assert "at" in arg_list, f"Modifier '{modifier}' requires an 'at' argument."
        start_or_end = arg_list["at"]


        match modifier:
            case "position":
                constraints = self._build_position_constraints(arg_list)

            case "lane":
                constraints = self._build_lane_constraints(arg_list)

            case _:
                # Unsupported according to DSL 2.1
                raise NotImplementedError(
                    f"Modifier '{modifier}' not supported. Currently the position and lane modifiers are part of our implementation."
                )

        return start_or_end, constraints
    


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


