# CAREFUL: this class is copied modified from internal_scene (which is obsolete and part of very old code)
#  Do not mistake the two and TODO delete internal_scene once we are done.

class Actor(object):
    """Defines an actor such as cars, bicycles, etc. """

    def __init__(self, type=None, id=None):
        """Constructor for Actor class. Has little information, just the type (car, bicycle) and a position for now.
        """

        self._type = type
        self._id = id

    def __str__(self):
        return self._id

    @property
    def type(self):
        if self._type == 'car':
            return 'Car'  # This is the difference between osc and scenic syntax

        return self._type

    @type.setter
    def type(self, value):
        self._type = value

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value
