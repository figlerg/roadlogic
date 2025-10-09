# Was part of internal_scene (sampling_constraint), is used here under a different name.

class SamplingHint(object):
    """Anything that is sampled explicitely goes here (mostly float parameters, roads, etc)"""

    def __init__(self, type, properties: dict):
        """Constructor for SamplingConstraint"""

        self._type = type  # interval range? specific road/lane/etc?
        self._properties = properties
