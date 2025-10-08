#  This whole file is only necessary because the clingo python api makes models not persistent
#  (iterating deletes old model).
#  So, I had to mimic the models and symbols with my own classes, so I can keep them in memory.

#

from clingo import Model, Function, Symbol, SymbolType
import json
from collections import defaultdict
import copy

from functools import cached_property

class MyModel:
    def __init__(self, clingo_model:Model):
        self.symbols = []

        for pred in clingo_model.symbols(shown=True):

            self.symbols.append(recursive_predicate(pred))

        self.orig_str = str(clingo_model)  # simply save original string

    def __iter__(self):
        return self.symbols.__iter__()

    def __str__(self):
        return self.orig_str


    def __eq__(self, other):
        return str(sorted(self.holds,key=str)) == str(sorted(other.holds, key=str))


    # TODO methods like this should replace all the weird helpers I created years ago (holds_helper, etc)
    @property
    def holds(self):
        # just returns the list of fluent predicates "holds"

        return [pred for pred in self if pred.name == 'holds']

    @property
    def crossed(self):
        # just returns the list of fluent predicates "crossed"

        return [pred for pred in self if pred.name == 'crossed']

    @property
    def goal(self):
        # just returns the list of fluent predicates "goal"

        return [pred for pred in self if pred.name == 'goal']

    @cached_property
    def max_t(self):
        return max([holds[-1] for holds in self.holds])



    def to_json(self, path):
        grouped = defaultdict(list)

        for pred in self.holds:
            actor = str(pred.actor)
            loc = str(pred.loc)
            dyn = str(pred.dyn)
            time = pred.time

            grouped[actor].append({
                'position': loc,
                'velocity': dyn,
                'time': time
            })

        for actor in grouped:
            grouped[actor].sort(key=lambda entry: entry['time'])

        with open(path, 'w') as f:
            json.dump(grouped, f, indent=2)


def recursive_predicate(clingo_pred:Symbol):
    # construct the tree recursively

    if clingo_pred.type == SymbolType.Number:
        return clingo_pred.number
    else:
        name = clingo_pred.name
        args = []

        for arg in clingo_pred.arguments:
            args.append(recursive_predicate(arg))

    str_rep = str(clingo_pred)

    return MyPred(name, args)


class MyPred:
    # explanation: it has a name and some inputs. as string i just save the original string.
    # Note: I never save the 'Number' symbols here, these get converted to numbers immediately

    def __init__(self, name, args = None):

        self.name = name

        self.arguments = list()
        if args:
            self.arguments = args


    def __str__(self):
        str_args = [str(arg) for arg in self.arguments]
        if self.arguments:
            return f"{self.name}({','.join(str_args)})"
        else:
            return self.name

    def __repr__(self):
        return str(self)

    def __getitem__(self, item):
        # this is helpful for tuples
        return self.arguments[item]

    def __deepcopy__(self, memodict={}):
        name = self.name
        args = copy.deepcopy(self.arguments)
        return MyPred(name, args)


    # The following two are for making serialization easier
    def to_dict(self):
        return {"name": self.name, "arguments": self.arguments}

    @classmethod
    def from_dict(cls, data):
        return cls(data["name"], data["arguments"])



    # Just a way to query easily by word. An exception is raised if any of these are used for the wrong predicate.
    @property
    def time(self):
        if self.name not in ['holds', 'occurs']:
            raise Exception("Wrong usage of this method. Can only be called if the predicate is holds or occurs.")

        return self.arguments[-1]
    @time.setter
    def time(self, t):
        if self.name not in ['holds', 'occurs']:
            raise Exception("Wrong usage of this method. Can only be called if the predicate is holds or occurs.")

        self.arguments[-1] = t


    @property
    def actor(self):
        if self.name not in ['holds']:
            raise Exception("Wrong usage of this method. Can only be called if the predicate is holds or occurs.")

        return self.arguments[0][0]

    @property
    def loc(self):
        if self.name not in ['holds']:
            raise Exception("Wrong usage of this method. Can only be called if the predicate is holds or occurs.")

        return self.arguments[0][1]

    @property
    def dyn(self):
        if self.name not in ['holds']:
            raise Exception("Wrong usage of this method. Can only be called if the predicate is holds or occurs.")

        return self.arguments[0][2]




# # Example usage:
# # Assuming you have a Clingo Model object called 'clingo_model'
# clingo_model = clingo_model_generator_function()  # Replace with your actual method to generate a Clingo Model
# custom_model = CustomModel(clingo_model)
#
# # Accessing attributes of the custom model
# print(custom_model.symbols)
