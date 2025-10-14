import z3

class Alphabet(object):
    def __init__(self):
        self.vars = set()                               # finite set of variables
        self.vars_domain = dict()                       # dictionary key=var_name value=domain

    def add_var(self, var_name, domain):
        self.vars.add(var_name)
        self.vars_domain[var_name] = domain