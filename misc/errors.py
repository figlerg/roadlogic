class Error(Exception):
    """Base class for exceptions in this module."""
    pass


# TODO these should be looked at

class CmdInputError(Error):
    """Exception raised for errors because of cmd inputs.

    Attributes:
        _expression -- input _expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message


class InputError(Error):
    """Exception raised for errors in the input.

    Attributes:
        _expression -- input _expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message


class IllegalSpecError(Error):
    """Exception raised for user input that is not valid (similar to a parsing error, but might include other things as well.

    Attributes:
        _expression -- input _expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression=None, message=None):
        if not expression:
            self.expression = 'Invalid input'
        if not message:
            self.message = 'Check input file'


class IllegalParameterError(Error):
    """Exception raised for invalid user input in the shapex parameters

    Attributes:
        parameter -- parameter key word
        value -- specified parameter value that is invalid
        message -- explanation of the error
    """

    def __init__(self, parameter=None, value=None, message=None):

        if not (message or value or parameter):
            self.message = 'Check parameter input of ShapEx constructor.'
        else:
            message = message + "...parameter {} with value {} might be the problem."
            self.message = message.format(parameter, value)


from antlr4 import *
from antlr4.error.ErrorStrategy import BailErrorStrategy


# this actually throws if parser encounters invalid syntax and gives some error message.
# inspired by https://stackoverflow.com/questions/60263601/how-can-i-fail-on-first-syntax-error-in-a-python-antlr-generated-parser-while-ke
class HardSyntaxErrorStrategy(BailErrorStrategy):
    def recover(self, recognizer: Parser, e: RecognitionException):
        recognizer._errHandler.reportError(recognizer, e)
        super().recover(recognizer, e)
