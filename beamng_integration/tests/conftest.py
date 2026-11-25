# Fixtures to setup and configure BeamNG.tech

# TODO Hardcoded WSL, need updates!

import pytest
import platform
import os
import uuid

from pathlib import Path, PurePosixPath, PureWindowsPath

from data_structures import BeamNGConfigs
from utils import ensure_materials, set_up_simple_logging, connect_or_start_beamng


@pytest.fixture
def system_is():
    return platform.uname().release.lower()


@pytest.fixture
def beamng_home_path(system_is) -> PureWindowsPath:
    assert "wsl" in system_is, "Cannot handle non WSL systems at the moment"
    return PureWindowsPath(os.environ.get("BEAMNG_TECH_HOME") or "C:\\BeamNG\\BeamNG.tech.v0.39.4.0")


@pytest.fixture
def beamng_base_user(system_is) -> PureWindowsPath:
    assert "wsl" in system_is, "Cannot handle non WSL systems at the moment"
    return PureWindowsPath(os.environ.get("BEAMNG_TECH_USER") or "C:\\BeamNG\\TempUserFolders")


@pytest.fixture
def beamng_temporary_user_folder(system_is, beamng_base_user: PureWindowsPath) -> PureWindowsPath:
    """
    Create a fresh temporary folder inside the beamng_base_user folder.
    """
    assert "wsl" in system_is, "Cannot handle non WSL systems at the moment"
    return beamng_base_user / str(uuid.uuid4())


@pytest.fixture
def beamng_port() -> int:
    return int(os.environ.get("BEAMNG_TECH_PORT") or 25252)


@pytest.fixture
def beamng_host() -> str:
    # TODO Prob some IP4 class should be used here
    return os.environ.get("BEAMNG_TECH_HOST") or "172.27.32.1"


@pytest.fixture
def beamng_configs(beamng_home_path: PureWindowsPath, beamng_temporary_user_folder: PureWindowsPath,
                   beamng_host: str, beamng_port: int):
                   # TODO Not sure what's this, probably a way to access pytest configuration and options
                #    request):
    beamng_configs = BeamNGConfigs(beamng_home_path=beamng_home_path, 
                                   beamng_user_path=beamng_temporary_user_folder,
                                   beamng_host=beamng_host, beamng_port=beamng_port,
                                   fps=30, step_seconds=30,
                                   headless=False, no_graphics=False)
                                #    headless=request.config.getoption("--headless"), no_graphics=request.config.getoption("--no-graphics"))

    return beamng_configs


@pytest.fixture
def running_beamng(beamng_configs):
    """
    Connect to a running BeamNG instance or start one if none is ready. Does not stop the running instance, but it will stop the scenario
    """
    set_up_simple_logging()
    ensure_materials(beamng_configs.beamng_user_path, beamng_configs.beamng_level_name)

    beamng = connect_or_start_beamng(beamng_configs)

    # Pass it to the tests
    yield beamng

    
    if beamng:
        # Do not stop the running simulator
        beamng.quit_on_close = False
        beamng.close()
