import pytest
import platform
import os

from pathlib import PurePosixPath, PureWindowsPath
from beamngpy import BeamNGpy, MeshRoad, Road, Scenario, Vehicle, set_up_simple_logging
from beamngpy.sensors import Timer

def test_start_beamng_and_do_nothing(running_beamng):
    """
    This is a smoke test to check whether we can run BeamNG.tech
    """
    pass