# Common Data Structures

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath, PurePosixPath

@dataclass(frozen=True)
class BeamNGConfigs():
    """
    Configuration objects encapsulating the main configurations related to BeamNG.tech simulation
    """
    beamng_home_path: Path
    beamng_user_path: Path
    beamng_host: str
    beamng_port: int
    fps: int
    step_seconds: int
    headless: bool = False
    beamng_level_name: str = "tech_ground"
    no_graphics: bool = False

    def __str__(self) -> str:
        from dataclasses import fields
        string_rep = ""
        for field in fields(BeamNGConfigs):
            string_rep = string_rep + f"{field.name}" + ": " f"{getattr(self, field.name)}" + "\n"
        return string_rep

