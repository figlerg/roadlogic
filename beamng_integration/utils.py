import ctypes
import logging
import platform
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath, PurePosixPath
from typing import Callable, IO, List, Optional
import json
import os
import shutil
import uuid

# from concurrent.futures import ThreadPoolExecutor, wait
# from dataclasses import dataclass
from typing import Optional, Tuple

from beamngpy import BeamNGpy, Scenario, Vehicle
from beamngpy.sensors import Damage, Electrics
from beamngpy.logging import BNGError
from shapely import Point

# from dataclasses import dataclass
from pathlib import Path, PureWindowsPath, PurePosixPath


logger = logging.getLogger(__name__)


import numpy as np
from beamngpy import BeamNGpy
from shapely import Point, LineString

# Export to downstream users
from beamngpy import set_up_simple_logging

#### OUR IMPORTS
from beamngpy import Road, MeshRoad

from .data_structures import BeamNGConfigs

# def safe_add_nodes(road: Road|MeshRoad, roadnodes):
#     """
#     Ensure that the points defining the roads are distant enough. It's an heuristic
#     """
#     # See https://stackoverflow.com/questions/56164410/how-can-i-remove-points-that-are-too-close-to-each-other-using-shapely
#     # See https://shapely.readthedocs.io/en/latest/reference/shapely.remove_repeated_points.html
#     # The issue is that roadnodes have more attributes than points...
#     from shapely import remove_repeated_points, get_num_points, get_point
#     list_point_and_road_nodes = [(Point(r[0], r[1]), r) for r in roadnodes]
#     original_line = LineString([p[0] for p in list_point_and_road_nodes])
#     safe_line = remove_repeated_points(original_line, tolerance=2.0)
#     safe_list_points = [get_point(safe_line, i) for i in range(get_num_points(safe_line))]
#     safe_roadnodes = [p[1] for p in list_point_and_road_nodes if p[0] in safe_list_points ]
#     road.add_nodes(*safe_roadnodes)



# def reinterpolate(control_points: list, interpoint_distance_m: float) -> list[Point]:
#     # 2. Generate equidistant points along the arc's true length)
#     line = LineString(control_points)
#     num_points = int(line.length / interpoint_distance_m)
#     distances = np.linspace(0, line.length, num_points)
#     equidistant_points = [line.interpolate(dist) for dist in distances]
#     return equidistant_points

def ensure_materials(beamng_user: Path, level_name: str):
    """Install road materials using native paths on Windows/Linux and translated paths on WSL."""
    # Only Windows paths need translation; WSL callers may already supply /mnt/... paths.
    windows_user = PureWindowsPath(beamng_user)
    if (
        platform.system() == "Linux"
        and "wsl" in platform.uname().release.lower()
        and windows_user.is_absolute()
    ):
        beamng_user = str(to_local_posix(windows_user))

    source_folder = Path(__file__).parent / "materials" / "art" / "road"
    source_folder = source_folder.as_posix()

    # Level folder
    levels_folder =  (Path(beamng_user) / "current" / "levels" / f"{level_name}").as_posix()
    if not os.path.exists(levels_folder):
        os.makedirs(levels_folder, exist_ok=True)

    # Road folder - Must be recreated TODO Change the name to be unique! road is common...
    local_road_folder = (Path(levels_folder) / "art" / "road").as_posix()
    if os.path.exists(local_road_folder):
        shutil.rmtree(local_road_folder)
    shutil.copytree(source_folder, local_road_folder)

    # Road folder is local to BeamNG
    road_folder = f"levels/{level_name}/art/road" 

    #  update the materials.json if needed and then copy it over
    materials_json_template_file = (Path(__file__).parent / "materials" / "materials.json.template").as_posix()
    with open(materials_json_template_file, "r") as input_file:
        data = json.load(input_file)
        # levels/template/art/road/road-01_n.dds
        for material_name in ["line_yellow", "line_dashed_long", "line_dashed_short", "road_invisible"]:
            # Create the unique material id
            data[material_name]["persistentId"] = str(uuid.uuid4())

            # Update the paths
            for stage in data[material_name]["Stages"]:
                for s in ["baseColorMap", "colorMap", "normalMap", "opacityMap"]:
                    if s in stage:
                        stage[s] =  str(stage[s]).replace("${level_folder}", f"{road_folder}")

        # Target location of the file
        materials_json_file = (Path(local_road_folder) / "main.materials.json")
        with open(materials_json_file, "w") as output_file:
            json.dump(data, output_file)


def timeout(seconds_before_timeout):

    def decorate(f):

        def handler(signum, frame):
            raise TimeoutError()

        def new_f(*args, **kwargs):
            old = signal.signal(signal.SIGALRM, handler)
            signal.alarm(seconds_before_timeout)
            try:
                result = f(*args, **kwargs)
            finally:
                # reinstall the old signal handler
                signal.signal(signal.SIGALRM, old)
                # cancel the alarm
                # this line should be inside the "finally" block (per Sam Kortchmar)
                signal.alarm(0)
            return result

        return new_f

    return decorate


def connect_or_start_beamng(beamng_configs: BeamNGConfigs):
    
    if platform.system() == "Windows":
        import inspect
        # BeamNGpy connects to an existing instance or launches one when needed.
        # Older BeamNGpy releases do not expose a socket timeout option.
        connection_options = {}
        if "socket_timeout" in inspect.signature(BeamNGpy).parameters:
            connection_options["socket_timeout"] = 120
        beamng_client = BeamNGpy(
            host=beamng_configs.beamng_host,
            port=beamng_configs.beamng_port,
            home=str(beamng_configs.beamng_home_path),
            user=str(beamng_configs.beamng_user_path),
            **connection_options,
        )
        beamng_client.open(launch=True, debug=True)
        return beamng_client

    beamng_client = BeamNGpy(host=beamng_configs.beamng_host, port=beamng_configs.beamng_port, home=str(beamng_configs.beamng_home_path), user=str(beamng_configs.beamng_user_path))
    
    try:
        # If this is already running, no need to start a new one. However, we need to kill the simulator manually afterwards
        @timeout(3)
        def try_open_beamng():
            beamng_client.open(launch=True, debug=True)

        try_open_beamng()

    except Exception: #TimeoutError | BNGError:
        print("BeamNG is not running, start it")
        bng_wrapper = BeamNGWrapper(beamng_configs)
        beamng_client = bng_wrapper.setup_environment()

    return beamng_client


class BeamNGWrapper():
    #
    # Wrap the startup logic of BeamNG. Based on ScenarioBridge code.
    # Inspired by ScenarioBridge
    #
    _BOOT_ATTEMPTS = 5
    _PER_BOOT_TIMEOUT_S = 300.0

    def __init__(
        self,
        beamng_configs: BeamNGConfigs
    ):
        """
        Initializes the BeamNG environment.

        Args:
            beamng_configs: Configuration object containing the BeamNG environment settings.
        """
        self.configs: BeamNGConfigs = beamng_configs
        self.fps = beamng_configs.fps
        self.step_length = max(1, int(round(beamng_configs.step_seconds * self.fps)))

        # Handle to the BeamNG process so close() can terminate it. BeamNGpy only stops processes it
        # launched itself, but ScenarioBridge starts BeamNG out-of-band (see _launch_and_connect).
        self._beamng_process: Optional[subprocess.Popen] = None
        self._closed = False

    def setup_environment(self) -> BeamNGpy:
        last_error: Optional[BaseException] = None
        for boot_attempt in range(1, self._BOOT_ATTEMPTS + 1):
            try:
                self.bng = self._launch_and_connect()
                return self.bng
                # scenario = self._build_scenario()
                # vehicles = self._add_vehicles(scenario)
                # self._load_scenario(bng, scenario)
                # return bng, vehicles
            except Exception as e:
                last_error = e
                logger.warning(
                    "BeamNG boot attempt %d/%d failed: %s. Restarting BeamNG.",
                    boot_attempt,
                    self._BOOT_ATTEMPTS,
                    e,
                )
                terminate_beamng_process(self._beamng_process)
                self._beamng_process = None

        raise RuntimeError(f"❌ BeamNG failed to come up after {self._BOOT_ATTEMPTS} boot attempts: {last_error}")

    def _launch_and_connect(self) -> BeamNGpy:
        """
        Launches the BeamNG simulator process and establishes a single connection to it.

        Depending on the host OS, BeamNG is started from Linux, WSL, or via SSH from macOS. The handshake
        itself is retried internally by open_beamng_with_retry, which bails as soon as the BeamNG process
        dies so a failed boot is detected in seconds rather than after the full handshake timeout. Restarting
        the process on failure is handled one level up by setup_environment's boot-attempt loop.

        Returns:
            The connected BeamNG simulation environment.

        Raises:
            NotImplementedError: If the operating system is not supported or recognized by the method.
        """

        if "wsl" in platform.uname().release.lower():
            host_address, self._beamng_process = start_beamng_wsl(
                runnable_path= PureWindowsPath(self.configs.beamng_home_path) / "Bin64" / "BeamNG.tech.x64.exe",
                user_path=PureWindowsPath(self.configs.beamng_user_path),
                port=self.configs.beamng_port,
                headless=self.configs.headless,
                no_graphics=self.configs.no_graphics,
            )
            home = PureWindowsPath(self.configs.beamng_home_path).as_posix()
            user = PureWindowsPath(self.configs.beamng_user_path).as_posix()
        elif platform.system() == "Linux":
            host_address, self._beamng_process = start_beamng_linux(
                runnable_path=PurePosixPath(self.configs.beamng_home_path) / "BinLinux" / "BeamNG.tech.x64",
                user_path=PurePosixPath(self.configs.beamng_user_path),
                port=self.configs.beamng_port,
                headless=self.configs.headless,
                no_graphics=self.configs.no_graphics,
            )
            home = PurePosixPath(self.configs.beamng_home_path).as_posix()
            user = PurePosixPath(self.configs.beamng_user_path).as_posix()
        else:
            raise NotImplementedError(f"ScenarioBridge does not support running BeamNG on {platform.system()}.")

        return open_beamng_with_retry(
            host=host_address,
            port=self.configs.beamng_port,
            home=home, 
            user=user, 
            process=self._beamng_process,
            timeout=self._PER_BOOT_TIMEOUT_S,
        )
    
    def close(self) -> None:
        """
        Cleans up the BeamNG environment, closing the connection and terminating the simulator process.

        Idempotent: a second call is a no-op.
        """

        if self._closed:
            return
        self._closed = True

        self._stop_simulator()

    def _stop_simulator(self) -> None:
        """
        Closes the BeamNG connection and terminates the simulator process.

        Shared by close() and recycle(). Unlike close(), this neither shuts down the thread-pool executor
        nor marks the environment closed, so recycle() can boot a fresh simulator afterwards.
        """

        try:
            self.bng.close()
        except Exception:
            logger.exception("Error closing the BeamNG connection; terminating the process anyway.")
        terminate_beamng_process(self._beamng_process)
        self._beamng_process = None

    def __str__(self):
        return "BeamNG"





@dataclass
class RoadSegment:
    spine: LineString
    left_edge: LineString
    right_edge: LineString

def to_local_posix(path: PureWindowsPath) -> Path:
    """
    Translates the given path to a path usable by the local filesystem.

    On WSL, drive-lettered Windows paths (e.g., C:\\Users\\...) must be translated to their
    WSL mount equivalent (/mnt/c/Users/...) before being handed to local tools, such as rsync.

    Args:
        path: The path to translate.

    Returns:
        The translated path.
    """

    if "wsl" in platform.uname().release.lower():
        result = subprocess.run(
            ["wslpath", "-u", path.as_posix()],
            capture_output=True, text=True, check=True,
        )
        return Path(result.stdout.strip())
    return Path(path.as_posix())


# def get_road_segments(bng: BeamNGpy) -> List[RoadSegment]:
#     """
#     Computes the road segments of the current scenario, which consist of the centerline, left and right
#     edges of the road, and the width of each segment. The road segment information is used to compute how far off
#     the vehicle is from the centerline and to determine whether the vehicle is offroad.

#     Args:
#         bng: The BeamNG environment.

#     Returns:
#         A list of RoadSegment objects, specifying the road network of the loaded scenario.
#     """

#     road_network = bng.scenario.get_road_network(include_edges=True, drivable_only=True)
#     segments: List[RoadSegment] = []

#     for key, road_data in road_network.items():
#         edges = road_data["edges"]
#         centers = [(edge["middle"][0], edge["middle"][1]) for edge in edges]
#         lefts = [(edge["left"][0], edge["left"][1]) for edge in edges]
#         rights = [(edge["right"][0], edge["right"][1]) for edge in edges]

#         spine = LineString(centers)
#         left_edge = LineString(lefts)
#         right_edge = LineString(rights)

#         segments.append(RoadSegment(spine, left_edge, right_edge))

#     return segments


# def signed_dist_to_closest_point(pos: Point, closest_point: Point, tangent: np.ndarray) -> float:
#     """
#     Computes the signed distance between the given position and the closest point on the centerline of the
#     closest road segment relative to the supplied position. Positive values indicate the vehicle is to the left
#     of the centerline, negative values indicate the vehicle is to the right of the centerline.

#     Args:
#         pos: The position to compute the signed distance from.
#         closest_point: The closest point on the centerline of the closest road segment.
#         tangent: The tangent representing the direction of the centerline.

#     Returns:
#         The signed distance between the given position and the closest point on the centerline of the
#         closest road segment.
#     """

#     # Z-Component of cross-product between tangent and vehicle vector,
#     # indicates whether the vehicle is to the left or right of the lane centerline.
#     # Positive -> vehicle is to the left of lane centerline.
#     # Negative -> vehicle is to the right of lane centerline.
#     # Multiplied by -1 to invert the alignment direction to match the intuitive coordinate system.
#     p0 = np.array(closest_point.coords[0])
#     vector_spine_vehicle = np.array([pos.x, pos.y]) - p0
#     cross = (tangent[0] * vector_spine_vehicle[1] - tangent[1] * vector_spine_vehicle[0]) * -1

#     # Compute how far off the vehicle is to the right/left of the lane centerline.
#     car_dist = closest_point.distance(pos)
#     signed_distance = float(np.sign(cross) * car_dist)
#     return signed_distance


# def get_closest_centerline_tangent(
#     road_segments: list[RoadSegment], pos: Point
# ) -> tuple[Point, RoadSegment, np.ndarray]:
#     """
#     Infers the closest point on the centerline of the closest road segment and its tangent to the given position.

#     Args:
#         road_segments: The list of road segments as given by the scenario.
#         pos: The position to compute the closest point on the centerline and tangent from.

#     Returns:
#         A triple containing the closest point on the centerline of the closest road segment, the closest road segment,
#         and the tangent of the centerline defining the direction of the centerline.
#     """

#     closest_segment, closest_point = min(
#         ((seg, seg.spine.interpolate(seg.spine.project(pos))) for seg in road_segments),
#         key=lambda sp: sp[1].distance(pos),
#     )
#     closest_spine = closest_segment.spine
#     closest_index = min(
#         range(len(closest_spine.coords)), key=lambda i: Point(closest_spine.coords[i]).distance(closest_point)
#     )

#     # Compute the tangent of the centerline to get the direction of the lane
#     # based on the two nearest points on the centerline.
#     if closest_index < len(closest_spine.coords) - 1:
#         reference = np.array(closest_segment.spine.coords[closest_index])
#         next_point = np.array(closest_segment.spine.coords[closest_index + 1])
#     else:
#         reference = np.array(closest_segment.spine.coords[closest_index - 1])
#         next_point = np.array(closest_segment.spine.coords[closest_index])

#     tangent = next_point - reference
#     tangent /= np.linalg.norm(tangent)
#     return closest_point, closest_segment, tangent


# def is_offroad(road_segments: list[RoadSegment], pos: Point, threshold: float) -> bool:
#     """
#     Indicates whether the given position is offroad based on the closest lane edges.

#     Args:
#         road_segments: The list of road segments as given by the scenario.
#         pos: The position to be offroad-checked.
#         threshold: The threshold for determining whether the position is offroad.

#     Returns:
#         True if the position is offroad, False otherwise.
#     """

#     closest_point, closest_segment, tangent = get_closest_centerline_tangent(road_segments, pos)
#     signed_distance = signed_dist_to_closest_point(pos, closest_point, tangent)
#     half_width = closest_segment.left_edge.distance(closest_segment.right_edge) / 2
#     offroad = abs(signed_distance) > half_width + threshold
#     return offroad


# def compute_spine_alignment(road_segments: list[RoadSegment], vehicle_pos: Point) -> float:
#     """
#     Determines the alignment of a vehicle with respect to the center of the closest road lane
#     normalized to a range of [-1, 1].

#     Args:
#         road_segments: The list of road segments as given by the scenario.
#         vehicle_pos: The current position of the vehicle.

#     Returns:
#         The normalized road alignment in the range [-1, 1]. Positive values indicate the vehicle is to the left
#         of the centerline, negative values indicate the vehicle is to the right of the centerline.
#     """

#     closest_point, closest_segment, tangent = get_closest_centerline_tangent(road_segments, vehicle_pos)
#     signed_distance = signed_dist_to_closest_point(vehicle_pos, closest_point, tangent)

#     # Normalize alignment to [-1, 1].
#     half_width = closest_segment.left_edge.distance(closest_segment.right_edge) / 2
#     norm_alignment = signed_distance / half_width
#     capped_alignment = min(max(norm_alignment, -1), 1)
#     return capped_alignment


# TODO WHy not insider BeamNGWrapper?
def open_beamng_with_retry(
    host: str,
    port: int,
    home: str,
    user: str,
    process: Optional[subprocess.Popen] = None,
    timeout: float = 600.0,
    probe_interval: float = 5.0,
) -> BeamNGpy:
    """
    Connects a BeamNGpy client to a running BeamNG instance, retrying the full handshake until it
    succeeds or `timeout` elapses. Exits early if the supplied BeamNG process dies, so callers
    can restart BeamNG instead of waiting the full timeout on a dead port.

    Args:
        host: Host where BeamNG is listening.
        port: Port where BeamNG is listening.
        home: BeamNG installation directory, forwarded to BeamNGpy.
        user: BeamNG per-worker user directory, forwarded to BeamNGpy.
        process: BeamNG process handle from the local launcher, used to detect crashes during
            startup. Pass None when BeamNG runs on a remote host (no local handle).
        timeout: Maximum total seconds to wait before giving up.
        probe_interval: Seconds to wait between handshake attempts.

    Returns:
        An open BeamNGpy instance ready for use.

    Raises:
        RuntimeError: If the handshake does not complete within `timeout` seconds, or if the BeamNG
            process exits before the handshake completes.
    """

    logger.debug(f"⏳ Connecting to BeamNG at {host}:{port} (handshake timeout {timeout:.0f}s)...")
    deadline = time.monotonic() + timeout
    attempts = 0
    last_error: Optional[BaseException] = None
    while True:
        if process is not None and process.poll() is not None:
            raise RuntimeError(
                f"❌ BeamNG process (pid {process.pid}) exited with code {process.returncode} "
                f"before handshake on {host}:{port}; see the per-worker beamng_stderr.log."
            )

        attempts += 1
        bng = BeamNGpy(host=host, port=port, home=home, user=user)
        try:
            bng.open(launch=False)
        except Exception as e:
            last_error = e
            try:
                bng.close()
            except Exception:
                pass
        else:
            elapsed = timeout - (deadline - time.monotonic())
            logger.debug(f"✅ BeamNG handshake completed after {elapsed:.1f}s ({attempts} attempt(s)).")
            return bng

        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"❌ Failed to connect to BeamNG at {host}:{port} after {attempts} attempts within "
                f"{timeout:.0f}s (last error: {last_error})"
            )
        time.sleep(probe_interval)


def start_beamng_linux(
    runnable_path: PurePosixPath, user_path: PurePosixPath, port: int, headless=False, no_graphics=False
) -> tuple[str, subprocess.Popen]:
    """
    Starts BeamNG on Linux.
    Args:
        runnable_path: The path to the BeamNG executable.
        port: The port to use for communication with BeamNG.
        user_path: The path to the BeamNG user directory.

    Returns:
        The IP address the BeamNG process listens to and a handle to the started process.
    """

    logger.debug("🚀 Starting BeamNG on Linux.")
    beamng_path_as_posix = runnable_path.as_posix()

    cli_args = [
        "-nosteam",
        "-userpath",
        str(user_path.as_posix()),
        "-tcom",
        "-tport",
        str(port),
        "-batch",
    ]
    if headless or no_graphics:
        cli_args.append("-headless")
    if no_graphics:
        cli_args.extend(["-gfx", "null"])

    process = _start_beamng([beamng_path_as_posix] + cli_args, log_path=_beamng_log_path(user_path))
    logger.debug("✅ Started BeamNG successfully.")
    return "localhost", process


def start_beamng_wsl(
    runnable_path: PureWindowsPath, port: int, user_path: PureWindowsPath, headless=False, no_graphics=False
) -> tuple[str, subprocess.Popen]:
    """
    Starts BeamNG on Windows from within the WSL environment.
    Args:
        runnable_path: The path to the BeamNG executable on Windows.
        port: The port to use for communication with BeamNG.
        user_path: The path to the BeamNG executable on Windows.
        headless: Whether to run BeamNG in headless mode.

    Returns:
        The IP address the BeamNG process listens to (within WSL) and a handle to the started process.
    """

    logger.debug("🚀 Starting BeamNG from WSL.")
    # Convert the WindowsPath to a PosixPath, move it to the partition following the WSL standard
    beamng_path_as_posix = runnable_path.as_posix()
    drive_on_wsl = f"/mnt/{beamng_path_as_posix.split(':')[0].lower()}"
    beamng_path_on_wsl = f"{drive_on_wsl}" + "".join(beamng_path_as_posix.split(":")[1:])

    # Note the 0.0.0.0 is hardcoded and means that this connection will listen on all the ports on wsl
    cli_args = [
        "-nosteam",
        "-userpath",
        str(user_path.as_posix()),
        "-console",
        "-tcom-listen-ip",
        "0.0.0.0",
        "-batch",
        "-lua",
        f"extensions.load('tech/techCore');tech_techCore.openServer({port})",
    ]

    if headless or no_graphics:
        cli_args.append("-headless")
    if no_graphics:
        cli_args.extend(["-gfx", "null"])

    process = _start_beamng([beamng_path_on_wsl] + cli_args, log_path=_beamng_log_path(user_path))

    # Search for windows host ip so the BeamNG instance can be set up to listen on that port.
    wsl_ip_on_win = get_windows_host_ip()
    logger.debug(f"✅ Detected WSL IP on the Windows host: {wsl_ip_on_win}")

    logger.debug("✅ Started BeamNG successfully.")
    return wsl_ip_on_win, process


def get_windows_host_ip() -> str:
    """
    Detect the Windows host IP from inside WSL as this is the IP where BeamNG will listen to.

    In WSL2 mirrored networking mode, WSL shares the Windows host's interfaces and BeamNG is reachable on 127.0.0.1. In NAT mode, the host is
    reached via the WSL default gateway.

    Returns:
        The Windows host IP from WSL.
    """

    try:
        with open("/proc/net/dev") as proc_net_dev:
            if "loopback0:" in proc_net_dev.read():
                return "127.0.0.1"
    except OSError:
        pass

    try:
        result = subprocess.run(
            ["bash", "-c", "ip route | grep default | awk '{print $3}'"], capture_output=True, text=True, check=True
        )
        ip = result.stdout.strip().split()[0]
        return ip
    except Exception as e:
        raise RuntimeError(f"❌ Could not determine Windows host IP: {e}")


def _beamng_log_path(user_path: PureWindowsPath) -> Path:
    """Resolves the per-worker BeamNG stderr log path next to the user dir."""
    local_user = to_local_posix(user_path)
    return local_user.parent / f"{local_user.name}_beamng_stderr.log"


def _start_beamng(cli_command: list[str], log_path: Optional[Path] = None) -> subprocess.Popen:
    """
    Starts beamng with the given CLI command.

    Args:
        cli_command: The CLI command to start beamng with.
        log_path: Optional file path where BeamNG's stdout/stderr are appended. When None the
            output is discarded. Capturing the stream is essential for diagnosing silent crashes
            that happen after the process-poll check below.

    Returns:
        A handle to the started BeamNG process.
    """

    log_handle: Optional[IO[bytes]] = None
    stdout_target: int | IO[bytes]
    stderr_target: int

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = open(log_path, "ab")
        stdout_target = log_handle
        stderr_target = subprocess.STDOUT
    else:
        stdout_target = subprocess.DEVNULL
        stderr_target = subprocess.DEVNULL

    try:
        for retry in range(10):
            time.sleep(10)
            process = subprocess.Popen(
                cli_command, stdout=stdout_target, stderr=stderr_target, preexec_fn=_pdeathsig_preexec()
            )
            if process.poll() is None:
                return process
            logger.warning(f"⚠️ Attempt {retry + 1} failed with exit code {process.returncode}")
        raise RuntimeError("❌ BeamNG failed to start after 10 retries")
    finally:
        if log_handle is not None:
            log_handle.close()

# TODO Woa!
def _pdeathsig_preexec() -> Optional["Callable[[], None]"]:
    """
    Builds a Popen preexec_fn that ties the launched BeamNG process's lifetime to its parent worker
    process on Linux. Without this, a worker that is force-killed while wedged inside the simulator
    (e.g. reaped on the per-episode deadline) never runs its cleanup, orphaning the BeamNG process and
    leaking its memory — the exact leak the periodic recycle exists to prevent.

    Uses prctl(PR_SET_PDEATHSIG, SIGKILL) so the kernel kills BeamNG when the worker dies. Returns None
    on non-Linux platforms (macOS/WSL host paths), where the feature is unavailable and the parent worker
    cleans BeamNG up explicitly anyway.
    """

    if platform.system() != "Linux":
        return None

    PR_SET_PDEATHSIG = 1

    def _preexec() -> None:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL)

    return _preexec


def terminate_beamng_process(process: Optional[subprocess.Popen], timeout: float = 30.0) -> None:
    """
    Terminates a BeamNG simulator process previously started by ScenarioBridge.

    ScenarioBridge launches BeamNG out-of-band and BeamNGpy connects with launch=False, so BeamNGpy's
    own shutdown does not stop the process, and it must be terminated explicitly, otherwise the orphaned
    process keeps holding (and leaking) memory. No-op when `process` is None (e.g. the macOS path,
    where BeamNG runs on a remote Windows host) or when the process has already exited.

    Args:
        process: The BeamNG process handle, or None if BeamNG was not started locally.
        timeout: Seconds to wait for a graceful shutdown before killing the process.
    """

    if process is None or process.poll() is not None:
        return

    logger.debug("🛑 Terminating BeamNG process (pid %s).", process.pid)
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning("BeamNG process %s ignored SIGTERM; killing it.", process.pid)
        process.kill()
        process.wait(timeout=5)


def create_worker_user_dir(base: PureWindowsPath, worker_index: int) -> PureWindowsPath:
    """Derives a writable per-worker BeamNG user dir from the configured base.

    Every worker (including worker 0) gets its own sibling worker_<i+1> directory next to the base directory.
    To avoid costly downloads of assets, the worker directories get seeded by copying the base directories contents.
    Thus, the base directory must be a read-only template that is never mutated.

    Args:
        base: The base directory containing the BeamNG user dir template.
        worker_index: The index of the worker.

    Returns:
        The path to the BeamNG user dir for the worker.
    """

    # macOS only allows one BeamNG process, so no need to spawn workers.
    if platform.system() == "Darwin":
        return base

    worker_path = base.parent / f"worker_{worker_index + 1}"

    src = to_local_posix(base)
    dst = to_local_posix(worker_path)
    dst.mkdir(parents=True, exist_ok=True)

    # Copy the contents of the base directory to the worker directory to avoid download of assets.
    if src.exists() and src.resolve() != dst.resolve():
        subprocess.run(
            ["rsync", "-a", "--exclude=beamng.log", f"{src}/", f"{dst}/"],
            check=True,
        )
    return worker_path


# TODO Move into BeamNGWrapper
def beamng_reset_map(beamng_client: BeamNGpy) -> None:
    """
    To be called after scenario.start() to reset the map and avoid issues with the navigation map.

    BeamNG builds the navigation graph too early, and its ray casting fails to detect the road mesh,
    resulting in a navigation graph with the wrong elevation (projected onto the terrain instead of the mesh roads).
    """
    beamng_client.queue_lua_command(
        "map.reset()",
        response=False,
    )


def beamng_assure_load_map(beamng_client: BeamNGpy) -> None:
    beamng_client.queue_lua_command(
        "extensions.map.assureLoad()",
        response=False,
    )


