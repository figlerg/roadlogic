import os.path
import warnings

from planning.intermediate_structure.Actor import Actor
from planning.intermediate_structure.SamplingHint import SamplingHint
from planning.intermediate_structure.TranslationGraph import TranslationGraph
from planning.intermediate_structure.Constraint import Constraint, Relation, Modifier
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
        return names_to_objects(names, field_type)

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

        try:
            return self.visit(ctx.composition())
        except AttributeError:
            return self.visit(ctx.behavior_invocation())

    def visitBehavior_invocation(self, ctx: openscenario2Parser.Behavior_invocationContext):
        # This is essentially the parsing of the atomic behavior.

        actor_id = self.visit(ctx.actor_expression())
        atomic_behavior = self.visit(ctx.behavior_name())

        parent = ctx.parentCtx

        try:
            member_name = parent.label_name().getText()
        except AttributeError:
            member_name = 'x'  # maybe use a global variable to keep track of an enumerator for subgraphs?

        atomic_graph = TranslationGraph()

        init_node = f'{member_name}.init'
        behavior_node = f'{member_name}.{atomic_behavior}'
        fin_node = f'{member_name}.fin'

        atomic_graph.add_node(init_node, initial=True)
        atomic_graph.add_node(behavior_node)
        atomic_graph.add_node(fin_node, final=True)

        try:
            precondition, postcondition = self.visit(ctx.behavior_with_declaration())


        except AttributeError:
            # print(ctx.getText())
            precondition, postcondition = set(), set()

        atomic_graph.add_transition(init_node, behavior_node, precondition)
        atomic_graph.add_transition(behavior_node, fin_node, postcondition)
        atomic_graph.substitute_actor('self', actor_id)

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

    def visitModifier_application(self, ctx: openscenario2Parser.Modifier_applicationContext):
        modifier = self.visit(ctx.modifier_name())
        arg_list = self.visit(ctx.argument_list())

        if modifier in ['position', 'lane']:
            start_or_end, constraints = arg_list_helper(arg_list, modifier)

        elif modifier == 'path':
            start_or_end, constraints = None, set()
            warnings.warn(
                f"The modifier {modifier} is ignored in this version of the tool, since we assume in general that the two cars have the same path.")

        else:
            start_or_end, constraints = None, set()
            warnings.warn(f"The {modifier} modifier is not supported yet and will be ignored.")

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

        pos_num = 0
        for child in ctx.positional_argument():
            argument_values[pos_num] = self.visit(child)

        for child in ctx.named_argument():
            child: openscenario2Parser.Named_argumentContext
            argument_name = self.visit(child.argument_name())
            argument_value = self.visit(child.expression())

            argument_values[argument_name] = argument_value

        return argument_values

    def visitExpression(self, ctx: openscenario2Parser.ExpressionContext):
        return self.visitChildren(ctx)

    def visitRange_constructor(self, ctx: openscenario2Parser.Range_constructorContext):
        start, end = ctx.expression()
        return (self.visit(start), self.visit(end))

    def visitPhysical_literal(self, ctx: openscenario2Parser.Physical_literalContext):
        nr = ctx.getText()
        # this returns a string like '3s', need to transform it to number

        nr = float(''.join(filter(str.isdigit, nr)))

        return nr


# helpers
def names_to_objects(names: list, member_type: str):
    # ego = Actor(type = 'car', position={RelativePosition.ON:r1}, id = 'ego')
    # r1 = SamplingConstraint(type = 'path',properties= {'name':'r1', 'type':'road'})

    if member_type in ['car', ]:  # write an enumerator or set the various actor types somewhere globally?
        out = []
        for name in names:
            actor = Actor(id=name, type=member_type)
            out.append(actor)

    elif member_type in ['road', 'path']:
        out = []
        for name in names:
            path = SamplingHint(type=member_type, properties={'name': name, 'type': member_type})
            out.append(path)

    else:
        raise NotImplementedError('The {} variable type translation is not implemented yet!'.format(member_type))

    return out


def arg_list_helper(arg_list: dict, modifier):
    # I assume there is both an 'at' and some positional argument in there
    # ('ahead_of', 'behind', same_as, left_of, right_of).

    assert 'at' in arg_list.keys(), "Please specify an 'at' argument for position and lane modifiers."
    start_or_end = arg_list['at']

    allowed_positional_keywords = {'ahead_of', 'behind', 'same_as', 'left_of', 'right_of'}
    assert (len(allowed_positional_keywords.intersection(set(arg_list.keys()))) == 1), \
        f"Positional modifiers such as '{modifier}' need exactly one of {allowed_positional_keywords} in the argument list."

    keys = arg_list.keys()

    if modifier == 'position':
        assert 0 in arg_list.keys(), "Need an interval as positional argument in modifier declaration."
        interval = arg_list[0]

        if 'ahead_of' in keys:
            relative_actor = arg_list['ahead_of']

            con1 = Constraint('self', relative_actor, Modifier.POSITION, Relation.LEQ, c=interval[1])
            con2 = Constraint('self', relative_actor, Modifier.POSITION, Relation.GEQ, c=interval[0])

            con1.match(con2) # saves pointer for partner in both constraints

            constraints = {con1, con2}

        elif 'behind' in keys:
            relative_actor = arg_list['behind']

            con1 = Constraint('self', relative_actor, Modifier.POSITION, Relation.LEQ, c=-interval[0])
            con2 = Constraint('self', relative_actor, Modifier.POSITION, Relation.GEQ, c=-interval[1])

            con1.match(con2) # saves pointer for partner in both constraints

            constraints = {con1, con2}

        else:
            raise NotImplementedError(f"Modifier {modifier} needs an argument 'behind' or 'ahead_of' another actor.")

    if modifier == 'lane':

        if 'same_as' in keys:
            relative_actor = arg_list['same_as']

            con1 = Constraint('self', relative_actor, Modifier.LANE, Relation.EQ)

            constraints = {con1}

        elif 'left_of' in keys:
            relative_actor = arg_list['left_of']

            con1 = Constraint('self', relative_actor, Modifier.LANE, Relation.L)

            constraints = {con1}

        elif 'right_of' in keys:
            relative_actor = arg_list['right_of']

            con1 = Constraint('self', relative_actor, Modifier.LANE, Relation.G)

            constraints = {con1}

        else:
            raise NotImplementedError(
                f"Modifier {modifier} needs an argument 'same_as', 'left_of', 'right_of' another actor.")

    return start_or_end, constraints


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


