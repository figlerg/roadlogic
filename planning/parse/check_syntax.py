# this script checks the syntax of all files in examples_translation/osc
# could be easily made into a function, but this is what it was written for


import os

from antlr4 import FileStream, CommonTokenStream
from antlr4.error.Errors import ParseCancellationException

from misc.errors import HardSyntaxErrorStrategy
from parse.generated.openscenario2Parser import openscenario2Parser
from parse.generated.openscenario2Lexer import openscenario2Lexer

# dir_path = r"C:\Users\giglerf\PycharmProjects\osc2scenic\examples\osc"
dir_path = r"/home/giglerf/PycharmProjects/osc2scenic/examples/osc"

# check all files in example directory for syntax
for file_name in os.listdir(dir_path):
    if file_name == '__pycache__':
        continue

    try:
        input_stream = FileStream(os.path.join(dir_path, file_name))
        # input_stream = FileStream(r'C:\Users\giglerf\PycharmProjects\osc2scenic\examples_parser\demo.osc')

        # this throws an error if the syntax is bad
        lexer = openscenario2Lexer(input_stream)
        stream = CommonTokenStream(lexer)
        parser = openscenario2Parser(stream)
        parser._errHandler = HardSyntaxErrorStrategy()
        ctx = parser.osc_file()




    except ParseCancellationException:
        print("Syntax error detected in file:{}".format(file_name))
        break

    # check if visitor works for all examples

    # visitor = SceneCreatorVisitor()

    # visitor.visit(ctx)
