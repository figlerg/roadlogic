# just crteates the syntax tree for my test file... useful for debugging the parser

import os

from antlr4 import FileStream, CommonTokenStream
from antlr4.error.Errors import ParseCancellationException
from antlr4.tree.Trees import Trees

from planning.misc.errors import HardSyntaxErrorStrategy
from planning.parse.generated.openscenario2Visitor import openscenario2Visitor
from planning.parse.generated.openscenario2Parser import openscenario2Parser
from planning.parse.generated.openscenario2Lexer import openscenario2Lexer

input_stream = FileStream(r'C:\Users\giglerf\PycharmProjects\osc2scenic\examples\osc\my_smoke_0.osc')
# input_stream = FileStream(r'C:\Users\giglerf\PycharmProjects\osc2scenic\examples_parser\demo.osc')


# this throws an error if the syntax is bad
lexer = openscenario2Lexer(input_stream)
stream = CommonTokenStream(lexer)
parser = openscenario2Parser(stream)
parser._errHandler = HardSyntaxErrorStrategy()
tree = parser.osc_file()

lisp_repr = Trees.toStringTree(tree, None, parser)

with open('tree.txt', 'w') as f:
    f.write(lisp_repr)
