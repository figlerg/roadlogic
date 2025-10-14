import itertools
from planning.intermediate_structure.Constraint import Constraint, Relation, Modifier
import networkx as nx
import matplotlib.pyplot as plt
import z3


class TranslationGraph(object):
    """An intermediate structure for the translation of openSCENARIO to Scenic.
    It is a directed Graph, it's edges have Constraint objects as labels.
    This structure is directly parsed from the OSC2 specification using ANTLR.

    Note for the reader: This class defines a wrapper for a networkx graph.
    This means there are two levels of the 'graph', some methods are implemented for both.
    Generally, I use the methods of the wrapper wherever possible (since they also keep the structure intact),
    but sometimes need to use the networkx functionality, in which case I use the self.__graph object methods.
    """

    def __init__(self):
        """
        Constructor for TranslationGraph. I use networkx for handling the graph.
        For now, it only creates the empty networkx graph.
        """
        self.__graph = nx.DiGraph()
        self.__actors = []
        self.__sampling_hints = []

        self.__initial = None
        self.__final = None

    @property
    def graph(self):
        return self.__graph

    @graph.setter
    def graph(self, value):
        self.__graph = value

    @property
    def actors(self):
        return self.__actors

    @actors.setter
    def actors(self, value):
        self.__actors = value

    @property
    def sampling_hints(self):
        return self.__sampling_hints

    @sampling_hints.setter
    def sampling_hints(self, value):
        self.__sampling_hints = value

    @property
    def initial(self):
        return self.__initial

    @initial.setter
    def initial(self, value):
        self.__initial = value

    @property
    def final(self):
        return self.__final

    @final.setter
    def final(self, value):
        self.__final = value

    # Utilities to expose some functionalities from the internal graph. Looks better when using the object in Scenic
    @property
    def edges(self):
        return self.__graph.edges

    @property
    def nodes(self):
        return self.__graph.nodes

    def __getitem__(self, item):
        v, w = item

        return self.__graph.edges[(v, w)]['object']

    def out_edges(self, v):
        return self.__graph.out_edges(v)

    def in_edges(self, v):
        return self.__graph.in_edges(v)

    def __add__(self, other):
        """
        I overload plus with the parallel composition.
        1) The set of states is the cartesian product of all states of the two operands.
        2) The transitions are inherited from the operands: If (a1,a2) is in one of the operands,
        connect all locations (a1,.) and (a2,.).
        """

        g1 = self.__graph
        g2: nx.DiGraph = other.__graph

        # I need the full information of the in and out edges of both graphs: Save them in a dict.
        # Keys are the non-dummy nodes of the edges, values are their constraints.
        # I don't need the full edge, since the dummy variables are deleted.
        g1_in = {edge[1]: g1.edges[edge]['object'] for edge in g1.out_edges(self.initial)}
        g1_out = {edge[0]: g1.edges[edge]['object'] for edge in g1.in_edges(self.final)}
        g2_in = {edge[1]: g2.edges[edge]['object'] for edge in g2.out_edges(other.initial)}
        g2_out = {edge[0]: g2.edges[edge]['object'] for edge in g2.in_edges(other.final)}

        # The dummy nodes shall not be used in the cartesian product. Instead, new dummy nodes are created later.
        self.remove_node(self.initial)
        self.remove_node(self.final)
        other.remove_node(other.initial)
        other.remove_node(other.final)

        locations_1 = g1.nodes
        locations_2 = g2.nodes

        assert not (len(locations_1) == 0 or len(locations_2) == 0), \
            "You are trying to parallelize an empty graph. Logically, this would result in another empty graph, but it " \
            "is more likely that this is a wrong usage of the plus operator."

        assert not set(locations_1).intersection(set(locations_2)), "Names of the locations (segment identifiers in " \
                                                                    "OSC spec) must be unique!"

        locations = list(itertools.product(locations_1, locations_2))

        out = TranslationGraph()
        out.add_node('init', initial=True)
        out.add_node('fin', final=True)

        for loc in locations:
            out.add_node(loc)

        # Now I need to do some special connections for the new dummy init/fin nodes:
        for loc in locations:  # These are the non-dummies
            if loc[0] in g1_in.keys() and loc[1] in g2_in.keys():
                constraints = g1_in[loc[0]].union(g2_in[loc[1]])
                out.add_transition('init', loc, constraints)

            if loc[0] in g1_out.keys() and loc[1] in g2_out.keys():
                constraints = g1_out[loc[0]].union(g2_out[loc[1]])
                out.add_transition(loc, 'fin', constraints)

        for loc in locations:
            for loc2 in locations:

                edge1 = (loc[0], loc2[0])  # First component of loc are states originally in g1.
                edge2 = (loc[1], loc2[1])  # Vice versa for g2.

                # 3 cases: (a,b) -> (c,d) iff there is either a->c in g1 or b->d in g2.
                # We distinguish also whether both edges exist!
                if edge1 in g1.edges and edge2 in g2.edges:
                    constraints = g1.edges[edge1]['object'].union(g2.edges[edge2]['object'])
                    out.add_transition(loc, loc2, constraints)

                if edge1 in g1.edges and (not edge2 in g2.edges):
                    constraints = g1.edges[edge1]['object']
                    out.add_transition(loc, loc2, constraints)

                if (not edge1 in g1.edges) and edge2 in g2.edges:
                    constraints = g2.edges[edge2]['object']
                    out.add_transition(loc, loc2, constraints)

        out.prune()
        return out

    def __mul__(self, other):
        """
        I overload the times operator with the serial composition.
        1) States are the union of both sets of states.
        2) Transitions are all transitions from the operands.
        """
        other: TranslationGraph

        locations_1 = self.__graph.nodes
        locations_2 = other.__graph.nodes

        # Combinations with empty graphs are simple:
        if len(locations_1) == 0 and len(locations_2) == 0:
            return self.__graph.nodes
        elif len(locations_1) == 0:
            return other
        elif len(locations_2) == 0:
            return self

        # I am pretty sure the nx compose operation will lead to something nasty if the names intersect.
        # I exclude the dummy states, I will deal with these before doing the compose.
        all_nodes = set(locations_1).intersection(set(locations_2))
        assert not all_nodes.difference({self.initial, self.final, other.initial, other.final}), \
            "Names of the locations (segment identifiers in OSC spec) must be unique!"

        g1 = self.__graph
        g2: nx.DiGraph = other.__graph

        g1_out = list(g1.in_edges(self.final))
        g2_in = list(g2.out_edges(other.initial))

        edge_constraints = dict()
        for edge1, edge2 in itertools.product(g1_out, g2_in):
            constraint = g1.edges[edge1]['object'].union(g2.edges[edge2]['object'])
            edge_constraints[(edge1[0], edge2[1])] = constraint
            # This has (v1, v2) as keys and the set of combined constraints as values.
            # I need to do this before deleting the nodes, so I can delete the dummys and nx.compose the two graphs.

        self.remove_node(self.final)
        other.remove_node(other.initial)

        serial_graph: nx.DiGraph = nx.compose(g1, g2)
        out = TranslationGraph()
        out.graph = serial_graph

        for v1, v2 in edge_constraints.keys():
            out.add_transition(v1, v2, edge_constraints[(v1, v2)])

        out.initial = self.initial
        out.final = other.final

        return out

    """Interesting algebraic structure. A monoid in both plus and times? With the right factorization, plus might even be (somewhat) commutative.
    I think for this strategy to make sense, it should be associative at least.
    Otherwise I would get weird results for some nestings.
    But given that the names are unique, this should be doable if I define the state labels correctly?
    This is only a problem for the order of the location tuples, not the structure of the graph.
    """

    def __mod__(self, other):
        # Maybe this is a bad operator, but there are only so many in Python and I did not want to use -, / for obvious
        # reasons (to not imply any relation with +. *)

        g1 = self.__graph
        g2: nx.DiGraph = other.__graph

        g1_in = {edge[1]: g1.edges[edge]['object'] for edge in g1.out_edges(self.initial)}
        g1_out = {edge[0]: g1.edges[edge]['object'] for edge in g1.in_edges(self.final)}
        g2_in = {edge[1]: g2.edges[edge]['object'] for edge in g2.out_edges(other.initial)}
        g2_out = {edge[0]: g2.edges[edge]['object'] for edge in g2.in_edges(other.final)}

        g1.remove_node(self.initial)
        g2.remove_node(other.initial)
        g1.remove_node(self.final)
        g2.remove_node(other.final)

        out = TranslationGraph()
        out.graph = nx.compose(g1, g2)  # This is only the real nodes, not the dummies

        out.add_node('init', initial=True)
        out.add_node('fin', final=True)

        for node in g1_in.keys():
            constraints = g1_in[node]
            out.add_transition('init', node, constraints)
        for node in g2_in.keys():
            constraints = g2_in[node]
            out.add_transition('init', node, constraints)

        for node in g1_out.keys():
            constraints = g1_out[node]
            out.add_transition(node, 'fin', constraints)
        for node in g2_out.keys():
            constraints = g2_out[node]
            out.add_transition(node, 'fin', constraints)

        return out

    def __str__(self):
        out = ''

        # out += f'Nodes: {self.aut.nodes}' \
        #        f' \n {self.aut.edges}' \
        #        f"{nx.get_edge_attributes(self.__aut, 'object')}"

        out += f'Nodes: {self.graph.nodes} \n' \
               f"Edges: {nx.get_edge_attributes(self.__graph, 'object')}"

        return out

    def draw(self, show=True):
        ax = plt.axes()

        # pos = nx.kamada_kawai_layout(self.__graph)
        # pos = nx.spring_layout(self.__graph)
        pos = nx.circular_layout(self.__graph)

        colormap = []
        for node in self.__graph.nodes:
            if node == self.initial:
                colormap.append('green')
            elif node == self.final:
                colormap.append('red')
            else:
                colormap.append('blue')

        nx.draw(self.__graph, node_color=colormap, pos=pos, with_labels=True)
        edge_labels = nx.get_edge_attributes(self.__graph, 'object')
        nx.draw_networkx_edge_labels(self.__graph, pos, edge_labels=edge_labels, font_size=7, ax=ax, rotate=False,
                                     alpha=0.5, bbox=dict(alpha=0))

        manager = plt.get_current_fig_manager()
        # manager.full_screen_toggle()
        # manager.window.state('zoomed')
        plt.show()

    def add_node(self, node, initial=False, final=False):
        # In the parser, this method should only be called for atomics.
        # The rest is combined recursively with +, * operators.
        self.__graph.add_node(node_for_adding=node)

        # Refactoring: Only one initial, one final node from now on.
        if initial:
            self.initial = node
        if final:
            self.final = node

    def remove_node(self, node):
        # Keep track of the pointers to the initial and final state.
        if self.initial == node:
            self.initial = None
        if self.final == node:
            self.final = None

        self.__graph.remove_node(node)

    def add_transition(self, v1, v2, constraints=None):
        assert v1 in self.__graph.nodes and v2 in self.__graph.nodes, 'You tried to connect nodes which are not yet in the ' \
                                                                      'automaton.'

        try:
            transition_constraints = set(constraints)
        except:
            transition_constraints = set()

            # Just some syntactic sugar in case I only add one constraint. This way I can drop the list brackets.
            if type(constraints) == Constraint:
                transition_constraints.add(constraints)

        self.__graph.add_edge(v1, v2, object=transition_constraints)

    def substitute_actor(self, original_name, new_name):
        # Sometimes I need to use an anonymous name in the visitor.
        # This is for inserting the 'self' name higher up in the call stack.

        for edge in self.graph.edges:
            for con in self.graph.edges[edge]['object']:
                con: Constraint

                if con.actor_1 == original_name:
                    con.actor_1 = new_name
                if con.actor_2 == original_name:
                    con.actor_2 = new_name

    def prune(self):
        # The parallel composition gives us unreachable nodes. These can be safely removed.

        g = self.__graph

        reachable = set()
        can_reach_finals = set()

        reachable.add(self.initial)
        can_reach_finals.add(self.final)

        reachable.update(nx.descendants(g, self.initial))
        can_reach_finals.update(nx.ancestors(g, self.final))

        # We only want nodes which are somewhere between initials and finals.
        relevant = reachable.intersection(can_reach_finals)

        # Delete the unreachable nodes:
        nodes = list(g.nodes)  # Otherwise the iterator changes.
        for node in nodes:
            if node not in relevant:
                g.remove_node(node)

    def edges_to_z3(self):
        # This casts the sets of constraint objects to a single z3 constraint
        for edge in self.__graph.edges:
            tmp = self.__graph.edges[edge]['object']

            z3_constraints = []
            for con in tmp:
                z3_constraints.append(con.to_z3())

            if len(z3_constraints) == 0:
                self.__graph.edges[edge]['object'] = True  # Apparently z3 can handle the original python True Bool.
            if len(z3_constraints) == 1:
                self.__graph.edges[edge]['object'] = z3_constraints[0]
            else:
                self.__graph.edges[edge]['object'] = z3.And(*z3_constraints)

    def paths(self):
        return list(nx.all_simple_paths(self.__graph, 'init', 'fin'))

    @property
    def variables(self):
        out = list()

        for actor in self.__actors:
            out.append(f"p_{actor}")
            out.append(f"l_{actor}")

        return out


if __name__ == '__main__':
    case = 1

    if case == 1:  # here I build the graph from the standard example

        test_graph = TranslationGraph()

        test_graph.add_node('init_node', initial=True)
        test_graph.add_node(1)
        test_graph.add_node(2)
        test_graph.add_node(3)
        test_graph.add_node('fin_node', final=True)

        a = 'ego'
        b = 'car1'
        l = Modifier.LANE
        p = Modifier.POSITION

        # 1st transition
        c1 = Constraint(a, b, l, Relation.EQ)
        c2 = Constraint(a, b, p, Relation.L, -20)
        c3 = Constraint(a, b, p, Relation.G, -10)

        constraints1 = {c1, c2, c3}
        print(constraints1)

        # 2nd transition
        c4 = Constraint(a, b, l, Relation.L)

        constraints2 = {c4}
        print(constraints2)

        # 3rd transition
        c5 = Constraint(a, b, p, Relation.G, 1)
        c6 = Constraint(a, b, p, Relation.L, 10)

        constraints3 = {c5, c6}
        print(constraints2)

        # 4th transition
        c7 = Constraint(a, b, p, Relation.G, 5)
        c8 = Constraint(a, b, p, Relation.L, 10)
        c9 = Constraint(a, b, l, Relation.EQ)

        constraints4 = {c7, c8}
        print(constraints3)

        # add them to the graph
        test_graph.add_transition('init_node', 1, constraints1)
        test_graph.add_transition(1, 2, constraints2)
        test_graph.add_transition(2, 3, constraints3)
        test_graph.add_transition(3, 'fin_node', constraints4)

        # g.draw(True)

        # g.draw(True)
        # print(g)

        # now I create some play graph to test the operators.
        # This 3-graph structure is what an atomic looks like in the intermediate structure.
        constraints5 = Constraint('a', 'b', Modifier.POSITION, Relation.GEQ)
        constraints6 = Constraint('a2', 'b2', Modifier.POSITION, Relation.LEQ)

        test_graph_2 = TranslationGraph()
        test_graph_2.add_node('x', initial=True)
        test_graph_2.add_node('y')
        test_graph_2.add_transition('x', 'y', constraints5)
        test_graph_2.add_node('z', final=True)
        test_graph_2.add_transition('y', 'z', constraints6)

        # g_prod = g * g2
        g_prod = test_graph + test_graph_2

        print(paths := g_prod.paths())

        print(g_prod[paths[0][0], paths[0][1]])

        g_prod.draw()

    if case == 2:  # two small graphs
        constraints5 = None
        constraints6 = None

        test_graph = TranslationGraph()
        test_graph.add_node('x', initial=True)
        test_graph.add_node('y')
        test_graph.add_transition('x', 'y', constraints5)
        test_graph.add_node('z', final=True)
        test_graph.add_transition('y', 'z', constraints6)

        test_graph_2 = TranslationGraph()
        test_graph_2.add_node('x2', initial=True)
        test_graph_2.add_node('y2')
        test_graph_2.add_transition('x2', 'y2', constraints5)
        test_graph_2.add_node('z2', final=True)
        test_graph_2.add_transition('y2', 'z2', constraints6)

        # g_prod = g * g2
        g_prod = test_graph + test_graph_2

        print(g_prod)

        g_prod.draw()
